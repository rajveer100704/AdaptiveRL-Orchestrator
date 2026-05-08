import asyncio
import time
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Request, Depends, Header
from prometheus_client import make_asgi_app
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from shared.schemas import InferenceRequest, InferenceResponse, WorkerResult, RequestState
from shared.config import settings
from shared.metrics import REQUEST_COUNT, ROUTING_DECISIONS, REQUEST_LATENCY, ACTIVE_REQUESTS, REQUEST_FAILURES

from routing.static_router import static_router
from routing.rl_router import rl_router
from routing.baselines import round_robin_router, least_loaded_router, random_router

from broker.redis_manager import redis_manager
from shared.logging import setup_logging
from shared.database import get_db, init_db
from shared.models import RoutingDecisionRecord

logger = setup_logging()

from shared.tracing import get_tracer
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

app = FastAPI(title="Adaptive RL-Based AI Inference Orchestrator")
get_tracer("gateway")
FastAPIInstrumentor.instrument_app(app)

metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

COST_MAP = {
    "queue_cpu": 0.01,
    "queue_gpu": 0.10,
    "queue_quantized": 0.02
}

@app.on_event("startup")
async def startup_event():
    await init_db()
    await redis_manager.ensure_consumer_group("queue_cpu", "group_cpu")
    await redis_manager.ensure_consumer_group("queue_gpu", "group_gpu")
    await redis_manager.ensure_consumer_group("queue_quantized", "group_quantized")
    logger.info("gateway_started", port=settings.gateway_port)

@app.get("/health")
async def health():
    try:
        await redis_manager.ping()
        return {"status": "ok", "redis": "connected"}
    except Exception as e:
        logger.error("healthcheck_failed", error=str(e))
        return {"status": "degraded", "error": str(e)}

@app.post("/infer", response_model=InferenceResponse)
async def infer(
    request: InferenceRequest, 
    x_routing_policy: Optional[str] = Header(default="ppo_v2"),
    db: AsyncSession = Depends(get_db)
):
    start_time = time.time()
    ACTIVE_REQUESTS.inc()
    REQUEST_COUNT.inc()
    
    log = logger.bind(request_id=str(request.request_id))
    log.info("request_received", payload=request.payload, model=request.model_name, routing_policy=x_routing_policy)
    
    try:
        if x_routing_policy == "static_v1":
            router = static_router
        elif x_routing_policy == "round_robin_v1":
            router = round_robin_router
        elif x_routing_policy == "least_loaded_v1":
            router = least_loaded_router
        elif x_routing_policy == "random_v1":
            router = random_router
        else:
            router = rl_router
            
        decision = await router.route(request)
        ROUTING_DECISIONS.labels(target_queue=decision.queue_name, policy_version=decision.policy_version).inc()
        
        queue_depth = await redis_manager.get_queue_depth(decision.queue_name)
        if queue_depth >= settings.max_queue_depth:
            log.warning("backpressure_rejected", queue=decision.queue_name, depth=queue_depth)
            raise HTTPException(status_code=503, detail="Queue overload, try again later")
            
        record = RoutingDecisionRecord(
            request_id=request.request_id,
            policy_version=decision.policy_version,
            selected_worker=decision.selected_worker,
            queue_name=decision.queue_name,
            request_type=request.model_name or "default",
            received_at=request.enqueue_timestamp,
            enqueued_at=datetime.now(timezone.utc),
            queue_depth=queue_depth,
            outcome=RequestState.PENDING.value,
            exploration_used=decision.exploration_used,
            epsilon_value=decision.epsilon_value,
            policy_confidence=decision.policy_confidence,
            action_probability=decision.action_probability,
            shadow_action=decision.shadow_action,
            routing_cost=COST_MAP.get(decision.queue_name, 0.05)
        )
        db.add(record)
        await db.commit()
        
        await redis_manager.enqueue(decision.queue_name, {
            "request_id": str(request.request_id),
            "payload": request.payload,
            "enqueued_at": record.enqueued_at.isoformat()
        })
        log.info("request_enqueued", queue=decision.queue_name)
        
        worker_result = await wait_for_result(str(request.request_id), timeout_ms=settings.gateway_timeout_ms)
        
        latency_ms = (time.time() - start_time) * 1000
        REQUEST_LATENCY.labels(outcome=worker_result.status.value).observe(latency_ms / 1000.0)
        
        record.outcome = worker_result.status.value
        record.total_latency_ms = latency_ms
        record.queue_wait_ms = worker_result.queue_wait_ms
        record.processing_ms = worker_result.processing_time_ms
        record.completed_at = datetime.now(timezone.utc)
        record.failure_reason = worker_result.failure_reason
        record.is_cold_start = worker_result.is_cold_start
        record.quality_degradation = worker_result.result.get("degradation", 0.0)
        
        await db.commit()
        
        if decision.shadow_action and decision.shadow_action != decision.queue_name:
            log.info("policy_divergence", active=decision.queue_name, shadow=decision.shadow_action)
            
        log.info("request_completed", latency_ms=latency_ms, outcome=record.outcome, cold_start=record.is_cold_start)
        
        return InferenceResponse(
            request_id=request.request_id,
            routing=decision,
            worker_result=worker_result,
            status=record.outcome,
            total_latency_ms=latency_ms
        )
    except HTTPException:
        REQUEST_FAILURES.labels(reason="overload").inc()
        raise
    except TimeoutError:
        REQUEST_FAILURES.labels(reason="timeout").inc()
        log.error("request_timeout")
        raise HTTPException(status_code=504, detail="Inference request timed out")
    except Exception as e:
        REQUEST_FAILURES.labels(reason="internal_error").inc()
        log.error("request_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        ACTIVE_REQUESTS.dec()

async def wait_for_result(request_id: str, timeout_ms: int) -> WorkerResult:
    start = time.time()
    timeout_s = timeout_ms / 1000.0
    while time.time() - start < timeout_s:
        res = await redis_manager.redis.hget("inference_results", request_id)
        if res:
            await redis_manager.redis.hdel("inference_results", request_id)
            import json
            return WorkerResult(**json.loads(res))
        await asyncio.sleep(0.05)
    raise TimeoutError("Timeout waiting for worker result")
