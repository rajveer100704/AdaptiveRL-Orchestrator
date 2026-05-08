import gymnasium as gym
from gymnasium import spaces
import numpy as np
import random
from collections import deque, OrderedDict

MODEL_SPECS = {
    "model_tiny": {"size_mb": 500, "load_time_s": 0.05},
    "model_medium": {"size_mb": 3000, "load_time_s": 0.5},
    "model_large": {"size_mb": 7000, "load_time_s": 3.0},
    "default": {"size_mb": 1000, "load_time_s": 0.2}
}
MODELS = list(MODEL_SPECS.keys())
ZIPF_PROBS = [0.5, 0.3, 0.1, 0.1] 

class LRUCacheSim:
    def __init__(self, capacity_mb):
        self.capacity_mb = capacity_mb
        self.current_mb = 0
        self.cache = OrderedDict()
        
    def get_or_load(self, model_name):
        if model_name in self.cache:
            self.cache.move_to_end(model_name)
            return 0.0 
            
        spec = MODEL_SPECS.get(model_name, MODEL_SPECS["default"])
        size = spec["size_mb"]
        
        while self.current_mb + size > self.capacity_mb and self.cache:
            _, evicted_size = self.cache.popitem(last=False)
            self.current_mb -= evicted_size
            
        self.cache[model_name] = size
        self.current_mb += size
        return spec["load_time_s"] 

class InferenceSimulationEnv(gym.Env):
    def __init__(self, max_steps=1000):
        super().__init__()
        self.max_steps = max_steps
        self.current_step = 0
        
        self.action_space = spaces.Discrete(3)
        self.observation_space = spaces.Box(low=0.0, high=1.0, shape=(14,), dtype=np.float32)
        
        self.alpha = 1.0   
        self.beta = 0.5    
        self.gamma = 20.0  
        self.delta = 50.0  
        self.zeta = 2.0    
        self.eta = 5.0     
        self.theta = 10.0  
        self.epsilon = 0.2 
        
        self.reset()
        
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        self.current_step = 0
        
        self.queues = {0: deque(), 1: deque(), 2: deque()}
        self.worker_active = {0: 0, 1: 0, 2: 0}
        
        self.w_cap = {0: 50, 1: 10, 2: 30}
        self.w_speed = {0: 0.30, 1: 0.05, 2: 0.10}
        self.w_cost = {0: 0.01, 1: 0.10, 2: 0.02}
        self.w_degrad = {0: 0.0, 1: 0.0, 2: 0.05}
        
        self.caches = {
            0: LRUCacheSim(8000),
            1: LRUCacheSim(16000),
            2: LRUCacheSim(8000)
        }
        
        self.failure_storm_active = random.random() < 0.2
        self._generate_next_request()
        
        return self._get_obs(), {}
        
    def _generate_next_request(self):
        self.next_complexity = random.uniform(0.1, 0.9)
        self.next_model = np.random.choice(MODELS, p=ZIPF_PROBS)
        
    def _get_obs(self):
        model_one_hot = [0.0] * 4
        model_one_hot[MODELS.index(self.next_model)] = 1.0
        
        q_cpu = min(1.0, len(self.queues[0]) / 1000.0)
        q_gpu = min(1.0, len(self.queues[1]) / 1000.0)
        q_quant = min(1.0, len(self.queues[2]) / 1000.0)
        
        w_cpu = min(1.0, self.worker_active[0] / self.w_cap[0])
        w_gpu = min(1.0, self.worker_active[1] / self.w_cap[1])
        w_quant = min(1.0, self.worker_active[2] / self.w_cap[2])
        
        c_cpu = 1.0 if self.next_model in self.caches[0].cache else 0.0
        c_gpu = 1.0 if self.next_model in self.caches[1].cache else 0.0
        c_quant = 1.0 if self.next_model in self.caches[2].cache else 0.0
        
        obs = [self.next_complexity] + model_one_hot + [q_cpu, q_gpu, q_quant] + [w_cpu, w_gpu, w_quant] + [c_cpu, c_gpu, c_quant]
        return np.array(obs, dtype=np.float32)

    def step(self, action):
        self.current_step += 1
        
        action_penalty = 0.0
        if len(self.queues[action]) >= 1000:
            action_penalty = -self.delta
        else:
            self.queues[action].append((self.next_complexity, self.next_model))
            
        failures = 0
        timeouts = 0
        processed = 0
        latency_sum = 0
        cost_sum = 0
        cold_starts = 0
        degradation_sum = 0
        
        for w_idx in [0, 1, 2]:
            process_count = min(len(self.queues[w_idx]), self.w_cap[w_idx])
            self.worker_active[w_idx] = process_count
            
            fail_prob = 0.01
            if self.failure_storm_active and w_idx == 0:
                fail_prob = 0.8
                
            for _ in range(process_count):
                c, m = self.queues[w_idx].popleft()
                
                load_time = self.caches[w_idx].get_or_load(m)
                if load_time > 0:
                    cold_starts += 1
                    
                if random.random() < fail_prob:
                    failures += 1
                else:
                    latency_sum += self.w_speed[w_idx] + load_time
                    cost_sum += self.w_cost[w_idx]
                    degradation_sum += self.w_degrad[w_idx]
                    processed += 1
                    
        avg_latency = latency_sum / max(1, processed)
        avg_cost = cost_sum / max(1, processed)
        avg_degrad = degradation_sum / max(1, processed)
        imbalance = max(len(self.queues[0]), len(self.queues[1]), len(self.queues[2])) / 1000.0
        
        reward = (
            -self.alpha * avg_latency 
            - self.beta * imbalance 
            - self.gamma * failures 
            - self.delta * timeouts 
            - self.zeta * avg_cost
            - self.eta * cold_starts
            - self.theta * avg_degrad
            + self.epsilon * processed
            + action_penalty
        )
        
        self._generate_next_request()
        terminated = self.current_step >= self.max_steps
        
        return self._get_obs(), float(reward), terminated, False, {}
