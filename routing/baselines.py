import random
from shared.schemas import InferenceRequest, RoutingDecision
from shared.logging import setup_logging
from routing.static_router import static_router
from broker.redis_manager import redis_manager

logger = setup_logging()

class RoundRobinRouter:
    def __init__(self):
        self.policy_version = "round_robin_v1"
        self._index = 0
        
    async def route(self, request: InferenceRequest) -> RoutingDecision:
        healthy_queues = await static_router.get_healthy_queues()
        if not healthy_queues:
            target = "queue_small"
        else:
            sorted_queues = sorted(list(healthy_queues))
            target = sorted_queues[self._index % len(sorted_queues)]
            self._index += 1
            
        return RoutingDecision(
            selected_worker=f"worker-{target.split('_')[-1]}",
            routing_reason="Round Robin",
            queue_name=target,
            policy_version=self.policy_version
        )

class LeastLoadedRouter:
    def __init__(self):
        self.policy_version = "least_loaded_v1"
        
    async def route(self, request: InferenceRequest) -> RoutingDecision:
        healthy_queues = await static_router.get_healthy_queues()
        if not healthy_queues:
            return RoutingDecision(
                selected_worker="worker-small", 
                routing_reason="Fallback", 
                queue_name="queue_small", 
                policy_version=self.policy_version
            )
            
        depths = {}
        for q in healthy_queues:
            depths[q] = await redis_manager.get_queue_depth(q)
            
        target = min(depths, key=depths.get)
        
        return RoutingDecision(
            selected_worker=f"worker-{target.split('_')[-1]}",
            routing_reason=f"Least Loaded (depth: {depths[target]})",
            queue_name=target,
            policy_version=self.policy_version
        )

class RandomRouter:
    def __init__(self):
        self.policy_version = "random_v1"
        
    async def route(self, request: InferenceRequest) -> RoutingDecision:
        healthy_queues = await static_router.get_healthy_queues()
        if not healthy_queues:
            target = "queue_small"
        else:
            target = random.choice(list(healthy_queues))
            
        return RoutingDecision(
            selected_worker=f"worker-{target.split('_')[-1]}",
            routing_reason="Random",
            queue_name=target,
            policy_version=self.policy_version
        )

round_robin_router = RoundRobinRouter()
least_loaded_router = LeastLoadedRouter()
random_router = RandomRouter()
