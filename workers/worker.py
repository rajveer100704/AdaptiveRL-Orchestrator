import asyncio
import random
import time
import signal
import sys
from datetime import datetime, timezone
from collections import OrderedDict
from shared.config import settings
from shared.schemas import WorkerResult, WorkerHeartbeat, RequestState
from broker.redis_manager import redis_manager
from shared.metrics import WORKER_TASKS_PROCESSED, WORKER_PROCESSING_TIME, WORKER_ACTIVE_TASKS, WORKER_QUEUE_WAIT_TIME
from shared.logging import setup_logging
from prometheus_client import start_http_server

logger = setup_logging()
shutdown_event = asyncio.Event()

MODEL_SPECS = {
    "model_tiny": {"size_mb": 500, "load_time_s": 0.05},
    "model_medium": {"size_mb": 3000, "load_time_s": 0.5},
    "model_large": {"size_mb": 7000, "load_time_s": 3.0},
    "default": {"size_mb": 1000, "load_time_s": 0.2}
}

class ModelCache:
    def __init__(self, capacity_mb: int):
        self.capacity_mb = capacity_mb
        self.current_mb = 0
        self.cache = OrderedDict()
        self.lock = asyncio.Lock()

    async def get_or_load(self, model_name: str) -> float:
        async with self.lock:
            if model_name in self.cache:
                self.cache.move_to_end(model_name)
                return 0.0
                
            spec = MODEL_SPECS.get(model_name, MODEL_SPECS["default"])
            size = spec["size_mb"]
            load_time = spec["load_time_s"]
            
            while self.current_mb + size > self.capacity_mb and self.cache:
                evicted_name, evicted_size = self.cache.popitem(last=False)
                self.current_mb -= evicted_size
                logger.info("model_evicted", model=evicted_name, freed_mb=evicted_size)
                
            self.cache[model_name] = size
            self.current_mb += size
            
            await asyncio.sleep(load_time)
            logger.info("model_loaded", model=model_name, size_mb=size, load_time_s=load_time)
            return load_time

    def get_loaded_models(self):
        return list(self.cache.keys())

model_cache = ModelCache(settings.worker_memory_budget_mb)

async def process_task_with_retries(task_data: dict, group_name: str, message_id: str):
    request_id = task_data.get("request_id")
    payload = task_data.get("payload", {})
    model_name = payload.get("model_name", "default")
    
    if not request_id:
        await redis_manager.acknowledge(settings.worker_queue, group_name, message_id)
        return
        
    log = logger.bind(request_id=request_id, worker_id=settings.worker_id)
    
    is_new = await redis_manager.check_idempotency(request_id)
    if not is_new:
        log.warning("duplicate_request_ignored")
        await redis_manager.acknowledge(settings.worker_queue, group_name, message_id)
        return

    enqueued_at_str = task_data.get("enqueued_at")
    queue_wait_ms = 0
    if enqueued_at_str:
        enqueued_at = datetime.fromisoformat(enqueued_at_str)
        queue_wait_ms = (datetime.now(timezone.utc) - enqueued_at).total_seconds() * 1000
        WORKER_QUEUE_WAIT_TIME.labels(worker_id=settings.worker_id, queue_name=settings.worker_queue).observe(queue_wait_ms / 1000.0)

    retry_count = 0
    success = False
    failure_reason = None
    
    while retry_count <= settings.max_retries and not success and not shutdown_event.is_set():
        start_time = time.time()
        WORKER_ACTIVE_TASKS.labels(worker_id=settings.worker_id).inc()
        try:
            # Load model if cold
            load_time_s = await model_cache.get_or_load(model_name)
            
            # Simulated Processing
            base_latency = settings.worker_base_latency_ms / 1000.0
            latency = base_latency * random.uniform(0.8, 1.2)
            await asyncio.sleep(latency)
            
            if random.random() < settings.worker_failure_probability:
                raise RuntimeError("Simulated worker random failure")
                
            processing_time_ms = (time.time() - start_time) * 1000
            
            # Add quantization degradation info to result
            degradation = settings.worker_quantization_degradation
            
            worker_result = WorkerResult(
                request_id=request_id,
                worker_id=settings.worker_id,
                result={"output": f"Processed by {settings.worker_id}", "degradation": degradation},
                status=RequestState.SUCCESS,
                processing_time_ms=processing_time_ms,
                queue_wait_ms=queue_wait_ms,
                is_cold_start=(load_time_s > 0)
            )
            await redis_manager.redis.hset("inference_results", request_id, worker_result.model_dump_json())
            WORKER_TASKS_PROCESSED.labels(worker_id=settings.worker_id, status="success").inc()
            await redis_manager.acknowledge(settings.worker_queue, group_name, message_id)
            success = True
            log.info("task_success", processing_time_ms=processing_time_ms, load_time_s=load_time_s)
            
        except Exception as e:
            failure_reason = str(e)
            retry_count += 1
            log.warning("task_failed_retrying", error=failure_reason, retry=retry_count)
            WORKER_TASKS_PROCESSED.labels(worker_id=settings.worker_id, status="retry").inc()
            if retry_count <= settings.max_retries:
                await asyncio.sleep((settings.retry_backoff_base_ms / 1000.0) * (2 ** (retry_count - 1)))
        finally:
            WORKER_ACTIVE_TASKS.labels(worker_id=settings.worker_id).dec()
            WORKER_PROCESSING_TIME.labels(worker_id=settings.worker_id).observe(time.time() - start_time)

    if not success:
        log.error("task_failed_dlq", error=failure_reason)
        await redis_manager.move_to_dlq(settings.worker_queue, task_data, failure_reason)
        await redis_manager.acknowledge(settings.worker_queue, group_name, message_id)
        
        worker_result = WorkerResult(
            request_id=request_id,
            worker_id=settings.worker_id,
            result={"error": failure_reason},
            status=RequestState.FAILED,
            processing_time_ms=(time.time() - start_time) * 1000,
            queue_wait_ms=queue_wait_ms,
            failure_reason=failure_reason,
            is_cold_start=False
        )
        await redis_manager.redis.hset("inference_results", request_id, worker_result.model_dump_json())
        WORKER_TASKS_PROCESSED.labels(worker_id=settings.worker_id, status="failed").inc()


async def heartbeat_loop():
    while not shutdown_event.is_set():
        try:
            hb = WorkerHeartbeat(
                worker_id=settings.worker_id,
                status="active",
                active_requests=int(WORKER_ACTIVE_TASKS.labels(worker_id=settings.worker_id)._value.get()),
                max_concurrency=settings.worker_max_concurrency,
                avg_latency_ms=settings.worker_base_latency_ms,
                loaded_models=model_cache.get_loaded_models()
            )
            await redis_manager.publish_heartbeat(settings.worker_id, hb.model_dump())
        except Exception as e:
            logger.error("heartbeat_failed", error=str(e))
        await asyncio.sleep(settings.worker_heartbeat_interval_s)

async def worker_loop():
    logger.info("worker_started", worker_id=settings.worker_id, queue=settings.worker_queue)
    group_name = f"group_{settings.worker_queue.split('_')[-1]}" 
    await redis_manager.ensure_consumer_group(settings.worker_queue, group_name)
    
    asyncio.create_task(heartbeat_loop())
    
    while not shutdown_event.is_set():
        try:
            messages = await redis_manager.consume(
                stream_name=settings.worker_queue, 
                group_name=group_name, 
                consumer_name=settings.worker_id,
                count=1,
                block=1000
            )
            for message_id, data in messages:
                active = int(WORKER_ACTIVE_TASKS.labels(worker_id=settings.worker_id)._value.get())
                if active < settings.worker_max_concurrency:
                    asyncio.create_task(process_task_with_retries(data, group_name, message_id))
                else:
                    await process_task_with_retries(data, group_name, message_id)
        except Exception as e:
            if not shutdown_event.is_set():
                logger.error("worker_loop_error", error=str(e))
                await asyncio.sleep(1)

def handle_sigterm(signum, frame):
    logger.info("shutdown_signal_received", signum=signum)
    shutdown_event.set()

if __name__ == "__main__":
    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)
    
    start_http_server(8001)
    asyncio.run(worker_loop())
    logger.info("worker_shutdown_complete")
