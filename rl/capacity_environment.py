import gymnasium as gym
from gymnasium import spaces
import numpy as np
import random
from collections import deque

class CapacitySimulationEnv(gym.Env):
    def __init__(self, max_steps=600): # 10 minutes simulation
        super().__init__()
        self.max_steps = max_steps
        
        # 3 pools: CPU, GPU, Quantized. Each has 3 actions: [0=Terminate, 1=No-Op, 2=Spawn]
        self.action_space = spaces.MultiDiscrete([3, 3, 3])
        
        # Observation space matching capacity_feature_extractor (15 dims)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(15,), dtype=np.float32)
        
        self.pool_names = ["cpu", "gpu", "quantized"]
        
        self.spawn_cost = 1.0
        self.timeout_penalty = 5.0
        self.idle_cost = {0: 0.01, 1: 0.10, 2: 0.02} # per sec cost of ACTIVE workers
        self.max_workers = 10
        
        self.provisioning_time = 30 # seconds
        self.warming_time = 15 # seconds
        self.cooldown_time = 30 # seconds
        
        self.reset()
        
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        
        self.workers = {0: [], 1: [], 2: []} # 0: CPU, 1: GPU, 2: Quantized
        # Start with 1 CPU worker active
        self.workers[0].append({"state": "ACTIVE", "timer": 0, "cooldown": 0})
        
        self.queues = {0: 0, 1: 0, 2: 0} # Simplified queue depth
        
        self.traffic_rate = 10 # req/sec
        
        return self._get_obs(), {}
        
    def _get_obs(self):
        obs = []
        for p_idx in [0, 1, 2]:
            active_count = 0
            pending_count = 0
            for w in self.workers[p_idx]:
                if w["state"] == "ACTIVE":
                    active_count += 1
                elif w["state"] in ["PROVISIONING", "WARMING"]:
                    pending_count += 1
                    
            q_depth = min(1.0, self.queues[p_idx] / 1000.0)
            avg_utilization = min(1.0, self.queues[p_idx] / max(1, active_count * 50.0))
            
            obs.extend([
                min(1.0, active_count / 10.0),
                min(1.0, avg_utilization),
                1.0 if active_count > 0 else 0.0,
                min(1.0, pending_count / 10.0),
                q_depth
            ])
        return np.array(obs, dtype=np.float32)

    def step(self, action):
        self.current_step += 1
        reward = 0.0
        
        # Traffic variation (simulate a burst halfway)
        if 250 < self.current_step < 350:
            self.traffic_rate = 50 # massive burst
        else:
            self.traffic_rate = 10
            
        # Distribute incoming traffic
        self.queues[0] += int(self.traffic_rate * 0.7)
        self.queues[1] += int(self.traffic_rate * 0.2)
        self.queues[2] += int(self.traffic_rate * 0.1)
        
        for p_idx in [0, 1, 2]:
            act = action[p_idx]
            
            # Action execution
            if act == 2: # SPAWN
                if len(self.workers[p_idx]) < self.max_workers:
                    # check if allowed by cooldown
                    can_spawn = all(w["cooldown"] == 0 for w in self.workers[p_idx])
                    if can_spawn:
                        self.workers[p_idx].append({"state": "PROVISIONING", "timer": self.provisioning_time, "cooldown": self.cooldown_time})
                        reward -= self.spawn_cost
            elif act == 0: # TERMINATE
                active_workers = [w for w in self.workers[p_idx] if w["state"] == "ACTIVE"]
                if active_workers:
                    self.workers[p_idx].remove(active_workers[0])
            
            # Update workers
            active_count = 0
            for w in self.workers[p_idx]:
                if w["cooldown"] > 0:
                    w["cooldown"] -= 1
                    
                if w["state"] == "PROVISIONING":
                    w["timer"] -= 1
                    if w["timer"] <= 0:
                        w["state"] = "WARMING"
                        w["timer"] = self.warming_time
                elif w["state"] == "WARMING":
                    w["timer"] -= 1
                    if w["timer"] <= 0:
                        w["state"] = "ACTIVE"
                        
                if w["state"] == "ACTIVE":
                    active_count += 1
                    reward -= self.idle_cost[p_idx] # idle/running cost
            
            # Process queue
            throughput = active_count * 20 # 20 req/sec per worker
            processed = min(self.queues[p_idx], throughput)
            self.queues[p_idx] -= processed
            
            # Penalize timeouts
            if self.queues[p_idx] > 500:
                timeouts = self.queues[p_idx] - 500
                reward -= (timeouts * self.timeout_penalty)
                self.queues[p_idx] = 500 # drop
                
        terminated = self.current_step >= self.max_steps
        
        return self._get_obs(), float(reward), terminated, False, {}
