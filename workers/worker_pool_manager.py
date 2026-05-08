import asyncio
import time
import uuid
import json
import random
from typing import Dict, Any

from shared.schemas import WorkerState, WorkerHeartbeat, WorkerResult, RequestState
from shared.config import settings
from shared.logging import setup_logging
from broker.redis_manager import redis_manager

logger = setup_logging()

class WorkerInstance:
    def __init__(self, pool_type: str, max_concurrency: int, base_latency_ms: int, cost: float, degrad: float, memory_mb: int):
        self.worker_id = f"worker-{pool_type}-{str(uuid.uuid4())[:8]}"
        self.pool_type = pool_type
        self.state = WorkerState.PROVISIONING
        self.queue_name = f"queue_{pool_type}"
        self.max_concurrency = max_concurrency
        self.base_latency_ms = base_latency_ms
        self.cost = cost
        self.degrad = degrad
        self.memory_budget_mb = memory_mb
        
        self.active_requests = 0
        self.loaded_models = []
        self.cache_usage = 0
        self.terminate_flag = False
        self.task = None

    async def start(self):
        self.task = asyncio.create_task(self._run_lifecycle())

    async def _run_lifecycle(self):
        try:
            logger.info("worker_provisioning", worker_id=self.worker_id, pool=self.pool_type)
            await redis_manager.register_worker(self.pool_type, self.worker_id, self.state.value)
            
            # Provisioning Delay
            await asyncio.sleep(settings.provisioning_delay_s)
            
            self.state = WorkerState.WARMING
            await redis_manager.register_worker(self.pool_type, self.worker_id, self.state.value)
            logger.info("worker_warming", worker_id=self.worker_id)
            
            # Warmup Delay
            await asyncio.sleep(settings.warmup_delay_s)
            
            self.state = WorkerState.ACTIVE
            await redis_manager.register_worker(self.pool_type, self.worker_id, self.state.value)
            logger.info("worker_active", worker_id=self.worker_id)
            
            heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            consume_task = asyncio.create_task(self._consume_loop())
            
            while not self.terminate_flag:
                await asyncio.sleep(1)
                
            self.state = WorkerState.DRAINING
            await redis_manager.register_worker(self.pool_type, self.worker_id, self.state.value)
            logger.info("worker_draining", worker_id=self.worker_id)
            
            # Wait for active requests to finish
            while self.active_requests > 0:
                await asyncio.sleep(0.5)
                
            heartbeat_task.cancel()
            consume_task.cancel()
            
            self.state = WorkerState.TERMINATED
            await redis_manager.deregister_worker(self.worker_id)
            logger.info("worker_terminated", worker_id=self.worker_id)
            
        except asyncio.CancelledError:
            await redis_manager.deregister_worker(self.worker_id)

    async def _heartbeat_loop(self):
        try:
            while True:
                hb = WorkerHeartbeat(
                    worker_id=self.worker_id,
                    status="healthy",
                    state=self.state,
                    active_requests=self.active_requests,
                    max_concurrency=self.max_concurrency,
                    avg_latency_ms=self.base_latency_ms,
                    loaded_models=self.loaded_models
                )
                await redis_manager.publish_heartbeat(self.worker_id, hb.model_dump())
                await asyncio.sleep(settings.worker_heartbeat_interval_s)
        except asyncio.CancelledError:
            pass

    async def _consume_loop(self):
        try:
            group_name = f"group_{self.pool_type}"
            while True:
                if self.active_requests >= self.max_concurrency:
                    await asyncio.sleep(0.1)
                    continue
                    
                messages = await redis_manager.consume(self.queue_name, group_name, self.worker_id, count=1, block=1000)
                if not messages:
                    continue
                    
                for message_id, payload in messages:
                    self.active_requests += 1
                    asyncio.create_task(self._process_message(message_id, payload, group_name))
        except asyncio.CancelledError:
            pass

    async def _process_message(self, message_id: str, payload: Dict[str, Any], group_name: str):
        from opentelemetry import propagate
        from shared.tracing import get_tracer
        tracer = get_tracer("worker-manager")
        
        # Extract trace context from payload for span continuity
        context = propagate.extract(payload)
        with tracer.start_as_current_span("worker.process_task", context=context) as span:
            try:
                span.set_attribute("worker_id", self.worker_id)
                span.set_attribute("pool_type", self.pool_type)
                span.set_attribute("request_id", payload.get("request_id", "unknown"))
                
                req_payload = payload.get("payload", {})
                complexity = req_payload.get("complexity", 0.5)
                model_name = req_payload.get("model_name", "default")
                
                is_cold_start = False
                load_time_ms = 0
                if model_name not in self.loaded_models:
                    is_cold_start = True
                    load_time_ms = 500 # Simulate load time
                    self.loaded_models.append(model_name)
                    if len(self.loaded_models) > 3: # Simple LRU
                        self.loaded_models.pop(0)
                        
                processing_time = (self.base_latency_ms + (complexity * 100) + load_time_ms) / 1000.0
                await asyncio.sleep(processing_time)
                
                result = WorkerResult(
                    request_id=payload["request_id"],
                    worker_id=self.worker_id,
                    result={"status": "success", "degradation": self.degrad},
                    status=RequestState.SUCCESS,
                    processing_time_ms=processing_time * 1000,
                    queue_wait_ms=0, # Simplified
                    is_cold_start=is_cold_start,
                    degradation=self.degrad
                )
                
                await redis_manager.redis.hset("inference_results", payload["request_id"], result.model_dump_json())
                await redis_manager.acknowledge(self.queue_name, group_name, message_id)
            
            except Exception as e:
                logger.error("worker_process_error", error=str(e))
            finally:
                self.active_requests -= 1

class WorkerPoolManager:
    def __init__(self):
        self.workers: Dict[str, WorkerInstance] = {}
        
    async def spawn_worker(self, pool_type: str):
        configs = {
            "cpu": {"cap": 50, "lat": 300, "cost": 0.01, "deg": 0.0, "mem": 8000},
            "gpu": {"cap": 10, "lat": 50, "cost": 0.10, "deg": 0.0, "mem": 16000},
            "quantized": {"cap": 30, "lat": 100, "cost": 0.02, "deg": 0.05, "mem": 8000}
        }
        cfg = configs.get(pool_type, configs["cpu"])
        worker = WorkerInstance(pool_type, cfg["cap"], cfg["lat"], cfg["cost"], cfg["deg"], cfg["mem"])
        self.workers[worker.worker_id] = worker
        await worker.start()
        return worker.worker_id
        
    async def terminate_worker(self, pool_type: str):
        # Terminate one active worker from the pool
        for w_id, w in self.workers.items():
            if w.pool_type == pool_type and w.state == WorkerState.ACTIVE and not w.terminate_flag:
                w.terminate_flag = True
                return w_id
        return None

    async def run(self):
        logger.info("worker_pool_manager_started")
        # Listen for scaling commands
        while True:
            cmd = await redis_manager.redis.lpop("scaling_commands")
            if cmd:
                command = json.loads(cmd)
                action = command.get("action")
                pool = command.get("pool")
                if action == "SPAWN":
                    await self.spawn_worker(pool)
                elif action == "TERMINATE":
                    await self.terminate_worker(pool)
            await asyncio.sleep(1)

if __name__ == "__main__":
    manager = WorkerPoolManager()
    asyncio.run(manager.run())
