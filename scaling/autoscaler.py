import asyncio
import os
import json
from stable_baselines3 import PPO
from broker.redis_manager import redis_manager
from rl.capacity_feature_extractor import capacity_feature_extractor
from shared.logging import setup_logging

logger = setup_logging()

class AutoscalerDaemon:
    def __init__(self, model_path="models/ppo_capacity_v1.zip"):
        self.model_path = model_path
        self.model = None
        self.pools = ["cpu", "gpu", "quantized"]
        
        if os.path.exists(self.model_path):
            self.model = PPO.load(self.model_path)
            logger.info("capacity_model_loaded", path=self.model_path)
        else:
            logger.warning("capacity_model_missing", path=self.model_path)

    async def run(self):
        from shared.tracing import get_tracer
        tracer = get_tracer("autoscaler")
        logger.info("autoscaler_daemon_started")
        
        while True:
            with tracer.start_as_current_span("autoscaler.cycle") as span:
                try:
                    queue_depths = {}
                for pool in self.pools:
                    queue_depths[f"queue_{pool}"] = await redis_manager.get_queue_depth(f"queue_{pool}")
                    
                registry = await redis_manager.get_worker_registry()
                heartbeats = await redis_manager.get_worker_heartbeats()
                
                state = capacity_feature_extractor.extract(queue_depths, registry, heartbeats)
                
                if self.model:
                    action, _ = self.model.predict(state, deterministic=True)
                    action = action[0] # Because it returns a batch
                    
                    for idx, p_action in enumerate(action):
                        pool = self.pools[idx]
                        if p_action == 2: # SPAWN
                            logger.info("scaling_decision", pool=pool, action="SPAWN")
                            await redis_manager.redis.rpush("scaling_commands", json.dumps({"pool": pool, "action": "SPAWN"}))
                        elif p_action == 0: # TERMINATE
                            logger.info("scaling_decision", pool=pool, action="TERMINATE")
                            await redis_manager.redis.rpush("scaling_commands", json.dumps({"pool": pool, "action": "TERMINATE"}))
                
            except Exception as e:
                logger.error("autoscaler_error", error=str(e))
                
            await asyncio.sleep(5) # Evaluate every 5 seconds for simulation stability

if __name__ == "__main__":
    daemon = AutoscalerDaemon()
    asyncio.run(daemon.run())
