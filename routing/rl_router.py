import os
import time
import random
import asyncio
import threading
from stable_baselines3 import PPO
from shared.schemas import InferenceRequest, RoutingDecision
from shared.logging import setup_logging
from broker.redis_manager import redis_manager
from routing.static_router import static_router
from rl.feature_extractor import feature_extractor

logger = setup_logging()

class RLRouter:
    def __init__(self, model_path: str = "models/ppo_v2.zip"):
        self.policy_version = "ppo_v2"
        self.model_path = model_path
        self.model = None
        self.last_mtime = 0
        self.epsilon = 0.10 # 10% controlled exploration
        
        self._load_model_if_updated()
        
        self.reload_thread = threading.Thread(target=self._hot_reload_loop, daemon=True)
        self.reload_thread.start()
        
        from routing.baselines import LeastLoadedRouter
        self.shadow_router = LeastLoadedRouter()

    def _load_model_if_updated(self):
        if not os.path.exists(self.model_path):
            return
            
        mtime = os.path.getmtime(self.model_path)
        if mtime > self.last_mtime:
            try:
                new_model = PPO.load(self.model_path)
                self.model = new_model
                self.last_mtime = mtime
                logger.info("rl_model_reloaded", path=self.model_path, mtime=mtime)
            except Exception as e:
                logger.error("rl_model_reload_failed", error=str(e))

    def _hot_reload_loop(self):
        while True:
            self._load_model_if_updated()
            time.sleep(10)

    async def route(self, request: InferenceRequest) -> RoutingDecision:
        healthy_queues = await static_router.get_healthy_queues()
        
        if not healthy_queues:
            return RoutingDecision(
                selected_worker="fallback-worker",
                routing_reason="No healthy queues",
                queue_name="queue_cpu",
                policy_version=self.policy_version
            )
            
        complexity = request.payload.get("complexity", 0.5)
        requested_model = request.model_name or "default"
        
        queue_depths = {}
        for q in ["queue_cpu", "queue_gpu", "queue_quantized"]:
            queue_depths[q] = await redis_manager.get_queue_depth(q)
            
        heartbeats = await redis_manager.get_worker_heartbeats()
        state = feature_extractor.extract(complexity, requested_model, queue_depths, heartbeats)
        
        exploration_used = False
        action_prob = None
        
        # Mapping 0: cpu, 1: gpu, 2: quantized
        q_map = {0: "queue_cpu", 1: "queue_gpu", 2: "queue_quantized"}
        
        if random.random() < self.epsilon:
            target_queue = random.choice(list(healthy_queues))
            exploration_used = True
            routing_reason = "Controlled Exploration"
        else:
            if self.model is not None:
                action, _ = self.model.predict(state, deterministic=True)
                action = int(action)
                target_queue = q_map.get(action, "queue_cpu")
                
                if target_queue not in healthy_queues:
                    target_queue = random.choice(list(healthy_queues))
                    routing_reason = "PPO overridden (safety fallback)"
                    action_prob = 0.0 
                else:
                    routing_reason = "PPO Inference"
            else:
                target_queue = random.choice(list(healthy_queues))
                routing_reason = "Model not found, safe fallback"

        # Shadow Routing
        shadow_decision = await self.shadow_router.route(request)
        shadow_action = shadow_decision.queue_name

        return RoutingDecision(
            selected_worker=f"worker-{target_queue.split('_')[-1]}-1",
            routing_reason=routing_reason,
            queue_name=target_queue,
            policy_version=self.policy_version,
            exploration_used=exploration_used,
            epsilon_value=self.epsilon,
            action_probability=action_prob,
            shadow_action=shadow_action
        )

rl_router = RLRouter()
