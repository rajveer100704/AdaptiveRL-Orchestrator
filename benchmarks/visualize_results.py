import json
import matplotlib.pyplot as plt
import numpy as np
import os

def load_data(policy):
    path = f"benchmarks/results/{policy}_run.json"
    if not os.path.exists(path):
        print(f"Warning: Data for {policy} missing at {path}. Using zero-filled series.")
        return []
    with open(path, "r") as f:
        return json.load(f)

def generate_comparison_plots():
    print("Generating telemetry-driven benchmark visualizations...")
    os.makedirs("docs/images", exist_ok=True)
    
    ppo_data = load_data("ppo_v2")
    heuristic_data = load_data("least_loaded_v1")
    random_data = load_data("random_v1")
    
    if not ppo_data and not heuristic_data:
        print("Error: No benchmark data found. Run 'make eval' first.")
        return

    # 1. p95 Latency Comparison
    plt.figure(figsize=(10, 6))
    if heuristic_data:
        plt.plot([d["elapsed"] for d in heuristic_data], [d["p95_latency_ms"] for d in heuristic_data], 
                 label="Least Loaded (Heuristic)", color="#e74c3c", linewidth=2, alpha=0.8)
    if ppo_data:
        plt.plot([d["elapsed"] for d in ppo_data], [d["p95_latency_ms"] for d in ppo_data], 
                 label="PPO Routing (Locality Aware)", color="#2ecc71", linewidth=2)
    
    plt.axvspan(40, 80, color='gray', alpha=0.1, label="Flash Burst")
    plt.title("p95 Latency Over Time: Heuristic vs. Learned Routing", fontsize=14)
    plt.xlabel("Time (seconds)", fontsize=12)
    plt.ylabel("Latency (ms)", fontsize=12)
    plt.legend()
    plt.grid(True, alpha=0.2)
    plt.savefig("docs/images/p95_latency_comparison.png")

    # 2. Warm Hit Ratio (The Locality Preservation Proof)
    plt.figure(figsize=(10, 6))
    if heuristic_data:
        plt.plot([d["elapsed"] for d in heuristic_data], [d["warm_hit_ratio"] for d in heuristic_data], 
                 label="Least Loaded", color="#e74c3c", linestyle="--")
    if ppo_data:
        plt.plot([d["elapsed"] for d in ppo_data], [d["warm_hit_ratio"] for d in ppo_data], 
                 label="PPO Routing", color="#2ecc71")
    
    plt.title("Warm Hit Ratio: Emergent Locality Preservation", fontsize=14)
    plt.xlabel("Time (seconds)", fontsize=12)
    plt.ylabel("Cache Hit Ratio", fontsize=12)
    plt.ylim(0, 1.1)
    plt.legend()
    plt.grid(True, alpha=0.2)
    plt.savefig("docs/images/warm_hit_ratio.png")

    # 3. Infrastructure Elasticity (Scaling Timeline)
    if ppo_data:
        plt.figure(figsize=(10, 6))
        plt.step([d["elapsed"] for d in ppo_data], [d["active_workers"] for d in ppo_data], 
                 where="post", label="Active Workers", color="#3498db", linewidth=2)
        plt.step([d["elapsed"] for d in ppo_data], [d["provisioning_workers"] for d in ppo_data], 
                 where="post", label="Provisioning", color="#9b59b6", alpha=0.5)
        
        plt.title("Proactive Infrastructure Elasticity (PPO Capacity)", fontsize=14)
        plt.xlabel("Time (seconds)", fontsize=12)
        plt.ylabel("Worker Count", fontsize=12)
        plt.legend()
        plt.grid(True, alpha=0.2)
        plt.savefig("docs/images/scaling_timeline.png")

    # 4. Accumulated Infrastructure Cost
    plt.figure(figsize=(10, 6))
    if heuristic_data:
        plt.plot([d["elapsed"] for d in heuristic_data], [d["accumulated_cost"] for d in heuristic_data], 
                 label="Static/Reactive Scaling", color="#95a5a6", linewidth=2)
    if ppo_data:
        plt.plot([d["elapsed"] for d in ppo_data], [d["accumulated_cost"] for d in ppo_data], 
                 label="PPO Adaptive Scaling", color="#3498db", linewidth=2)
                 
    plt.title("Total Infrastructure Cost Comparison", fontsize=14)
    plt.xlabel("Time (seconds)", fontsize=12)
    plt.ylabel("Cost ($)", fontsize=12)
    plt.legend()
    plt.grid(True, alpha=0.2)
    plt.savefig("docs/images/infra_cost_comparison.png")

    print("Authentic telemetry-driven plots saved to docs/images/")

if __name__ == "__main__":
    generate_comparison_plots()
