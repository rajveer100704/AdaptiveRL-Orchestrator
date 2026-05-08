import numpy as np
from typing import Dict, Any

class CapacityFeatureExtractor:
    def __init__(self):
        self.pools = ["cpu", "gpu", "quantized"]
        
    def extract(self, queue_depths: Dict[str, int], registry: Dict[str, Any], heartbeats: Dict[str, Any]) -> np.ndarray:
        # Expected dim = 15 (5 per pool)
        state = []
        
        pool_workers = {p: [] for p in self.pools}
        for w_id, w_info in registry.items():
            pool = w_info.get("pool")
            if pool in pool_workers:
                pool_workers[pool].append((w_id, w_info))
                
        for pool in self.pools:
            q_depth = queue_depths.get(f"queue_{pool}", 0) / 1000.0
            
            workers = pool_workers[pool]
            active_count = 0
            pending_count = 0
            total_utilization = 0.0
            
            for w_id, w_info in workers:
                st = w_info.get("state")
                if st in ["PROVISIONING", "WARMING"]:
                    pending_count += 1
                elif st == "ACTIVE":
                    active_count += 1
                    hb = heartbeats.get(w_id, {})
                    active_req = hb.get("active_requests", 0)
                    max_cap = hb.get("max_concurrency", 1)
                    total_utilization += (active_req / max(1, max_cap))
                    
            avg_utilization = (total_utilization / active_count) if active_count > 0 else 0.0
            
            # avg_cache_hit approximation: 
            # In actual implementation we might track this in metrics, but for state
            # we can approximate by seeing if workers are fully saturated (if they are, they are probably churning)
            # Or we just pass 1.0 if there are active workers.
            avg_cache_hit = 1.0 if active_count > 0 else 0.0
            
            # Normalize counts
            active_norm = active_count / 10.0 # Assuming max 10 workers per pool for capacity
            pending_norm = pending_count / 10.0
            
            state.extend([
                min(1.0, active_norm),
                min(1.0, avg_utilization),
                avg_cache_hit,
                min(1.0, pending_norm),
                min(1.0, q_depth)
            ])
            
        return np.array(state, dtype=np.float32).reshape(1, -1)

capacity_feature_extractor = CapacityFeatureExtractor()
