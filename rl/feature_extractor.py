import numpy as np
from typing import Dict, Any

class FeatureExtractor:
    def __init__(self):
        self.models = ["model_tiny", "model_medium", "model_large", "default"]
        
    def extract(self, complexity: float, requested_model: str, queue_depths: Dict[str, int], heartbeats: Dict[str, Any]) -> np.ndarray:
        # 1. Request Features (1 + 4 = 5)
        model_one_hot = [0.0] * 4
        if requested_model in self.models:
            model_one_hot[self.models.index(requested_model)] = 1.0
        else:
            model_one_hot[3] = 1.0 # default
            
        request_features = [complexity] + model_one_hot
        
        # 2. Queue Features (3)
        # Assuming queues: queue_cpu, queue_gpu, queue_quantized
        q_cpu = min(1.0, queue_depths.get("queue_cpu", 0) / 1000.0)
        q_gpu = min(1.0, queue_depths.get("queue_gpu", 0) / 1000.0)
        q_quant = min(1.0, queue_depths.get("queue_quantized", 0) / 1000.0)
        queue_features = [q_cpu, q_gpu, q_quant]
        
        # 3. Worker Features (3)
        hb_cpu = heartbeats.get("worker-cpu-1", {})
        hb_gpu = heartbeats.get("worker-gpu-1", {})
        hb_quant = heartbeats.get("worker-quantized-1", {})
        
        w_cpu = min(1.0, hb_cpu.get("active_requests", 0) / max(1, hb_cpu.get("max_concurrency", 50)))
        w_gpu = min(1.0, hb_gpu.get("active_requests", 0) / max(1, hb_gpu.get("max_concurrency", 10)))
        w_quant = min(1.0, hb_quant.get("active_requests", 0) / max(1, hb_quant.get("max_concurrency", 30)))
        worker_features = [w_cpu, w_gpu, w_quant]
        
        # 4. Cache Features (3)
        c_cpu = 1.0 if requested_model in hb_cpu.get("loaded_models", []) else 0.0
        c_gpu = 1.0 if requested_model in hb_gpu.get("loaded_models", []) else 0.0
        c_quant = 1.0 if requested_model in hb_quant.get("loaded_models", []) else 0.0
        cache_features = [c_cpu, c_gpu, c_quant]
        
        # Concatenate
        state = request_features + queue_features + worker_features + cache_features
        return np.array(state, dtype=np.float32).reshape(1, -1)

feature_extractor = FeatureExtractor()
