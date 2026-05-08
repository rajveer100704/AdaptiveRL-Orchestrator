import asyncio
import httpx
import time
import json
import numpy as np
import random
import os
from datetime import datetime
from broker.redis_manager import redis_manager

GATEWAY_URL = "http://localhost:8000"
MODELS = ["model_tiny", "model_medium", "model_large", "default"]
ZIPF_PROBS = [0.5, 0.3, 0.1, 0.1]

# Deterministic seed for reproducibility
random.seed(42)
np.random.seed(42)

async def send_request(client: httpx.AsyncClient, policy: str):
    payload = {
        "text": f"Benchmark {random.randint(1000, 9999)}",
        "complexity": random.uniform(0.1, 0.9),
        "model_name": np.random.choice(MODELS, p=ZIPF_PROBS)
    }
    try:
        start = time.time()
        response = await client.post(f"{GATEWAY_URL}/infer", json=payload, headers={"x-routing-policy": policy}, timeout=15.0)
        if response.status_code == 200:
            data = response.json()
            return 200, time.time() - start, data.get("worker_result", {})
        return response.status_code, time.time() - start, {}
    except Exception as e:
        return 500, 0, {"error": str(e)}

async def run_temporal_benchmark(policy: str, duration_sec: int = 180):
    print(f"Starting rigorous temporal benchmark for {policy}...")
    temporal_data = []
    results_dir = "benchmarks/results"
    os.makedirs(results_dir, exist_ok=True)
    
    async with httpx.AsyncClient() as client:
        start_time = time.time()
        last_log_time = start_time
        accumulated_cost = 0.0
        
        while time.time() - start_time < duration_sec:
            current_elapsed = time.time() - start_time
            
            # Dynamic traffic pattern: 
            # 0-40s: Low load (5 req/s)
            # 40-80s: Flash Burst (40 req/s)
            # 80-120s: Recovery (10 req/s)
            # 120-160s: Sustained (25 req/s)
            # 160+: Cool down
            
            if current_elapsed < 40: rate = 5
            elif current_elapsed < 80: rate = 40
            elif current_elapsed < 120: rate = 10
            elif current_elapsed < 160: rate = 25
            else: rate = 5
            
            tasks = [send_request(client, policy) for _ in range(rate)]
            results = await asyncio.gather(*tasks)
            
            # Log metrics every 5 seconds
            if time.time() - last_log_time >= 5:
                latencies = [r[1] for r in results if r[0] == 200 and r[1] > 0]
                p95 = np.percentile(latencies, 95) * 1000 if latencies else 0
                successes = [r for r in results if r[0] == 200]
                warm_hits = sum(1 for r in successes if not r[2].get("is_cold_start", True))
                warm_hit_ratio = warm_hits / len(successes) if successes else 0
                
                # Real Infrastructure Telemetry from Redis
                registry = await redis_manager.get_worker_registry()
                active_workers = len([w for w in registry.values() if w["state"] == "ACTIVE"])
                provisioning = len([w for w in registry.values() if w["state"] == "PROVISIONING"])
                
                # Mock cost calculation based on active workers (real-world simulation)
                # In a real system, we'd query Prometheus for the cost gauge
                step_cost = (active_workers * 0.05) + (provisioning * 0.1) 
                accumulated_cost += step_cost
                
                queue_depth = sum([await redis_manager.get_queue_depth(q) for q in ["queue_cpu", "queue_gpu", "queue_quantized"]])
                
                entry = {
                    "elapsed": int(current_elapsed),
                    "p95_latency_ms": round(max(p95, 0.1), 2), # Never negative
                    "warm_hit_ratio": round(warm_hit_ratio, 3),
                    "queue_depth": queue_depth,
                    "active_workers": active_workers,
                    "provisioning_workers": provisioning,
                    "accumulated_cost": round(accumulated_cost, 2),
                    "throughput": rate,
                    "success_rate": round(len(successes) / len(results) if results else 0, 2)
                }
                temporal_data.append(entry)
                last_log_time = time.time()
                print(f"[{int(current_elapsed)}s] p95: {p95:.1f}ms | WarmHit: {warm_hit_ratio*100:.1f}% | Active: {active_workers} | Q: {queue_depth}")
                
            await asyncio.sleep(1.0)
            
    output_file = f"{results_dir}/{policy}_run.json"
    with open(output_file, "w") as f:
        json.dump(temporal_data, f, indent=2)
    print(f"Benchmark telemetry saved to {output_file}")

if __name__ == "__main__":
    import sys
    policy = sys.argv[1] if len(sys.argv) > 1 else "ppo_v2"
    asyncio.run(run_temporal_benchmark(policy))
