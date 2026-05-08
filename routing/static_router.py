import time
from shared.schemas import InferenceRequest, RoutingDecision
from broker.redis_manager import redis_manager
from shared.config import settings
from shared.logging import setup_logging
from datetime import datetime, timezone

logger = setup_logging()

class StaticRouter:
    def __init__(self):
        self.policy_version = "static_v1"

    async def get_healthy_queues(self):
        heartbeats = await redis_manager.get_worker_heartbeats()
        healthy_queues = set()
        now = datetime.now(timezone.utc)
        
        for worker_id, hb in heartbeats.items():
            hb_time = datetime.fromisoformat(hb["timestamp"].replace("Z", "+00:00")) if isinstance(hb["timestamp"], str) else hb["timestamp"]
            age_s = (now - hb_time).total_seconds()
            
            if age_s < settings.worker_heartbeat_timeout_s and hb["status"] == "active":
                if "small" in worker_id:
                    healthy_queues.add("queue_small")
                elif "large" in worker_id:
                    healthy_queues.add("queue_large")
                    
        return healthy_queues

    async def route(self, request: InferenceRequest) -> RoutingDecision:
        healthy_queues = await self.get_healthy_queues()
        
        complexity = request.payload.get("complexity", 0.0)
        
        if complexity > 0.5:
            target = "queue_large"
            worker_prefix = "worker-large"
            reason = "High complexity"
        else:
            target = "queue_small"
            worker_prefix = "worker-small"
            reason = "Low complexity"
            
        if target not in healthy_queues:
            logger.warning("circuit_breaker_triggered", target_queue=target, healthy=list(healthy_queues))
            if healthy_queues:
                target = list(healthy_queues)[0]
                worker_prefix = f"fallback-{target}"
                reason = f"Fallback due to unhealthy original target"
            else:
                reason = "No healthy workers, routing blind"
                
        return RoutingDecision(
            selected_worker=worker_prefix,
            routing_reason=reason,
            queue_name=target,
            policy_version=self.policy_version
        )

static_router = StaticRouter()
