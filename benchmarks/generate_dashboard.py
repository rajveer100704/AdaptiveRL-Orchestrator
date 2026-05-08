import json
import matplotlib.pyplot as plt
import numpy as np
import os

def generate_pro_dashboard():
    print("Generating Professional Telemetry Dashboard...")
    os.makedirs("docs/images", exist_ok=True)
    
    # Load real telemetry from the PPO run
    path = "benchmarks/results/ppo_v2_run.json"
    if not os.path.exists(path):
        print("Error: No telemetry found. Run simulation first.")
        return
    with open(path, "r") as f:
        data = json.load(f)

    # Setup the dashboard layout (2x2 grid)
    plt.style.use('dark_background')
    fig, axs = plt.subplots(2, 2, figsize=(16, 10), facecolor='#111111')
    fig.suptitle('Adaptive RL Orchestrator: Real-Time Telemetry Dashboard', fontsize=22, color='#00d3ff', fontweight='bold')
    
    elapsed = [d["elapsed"] for d in data]
    
    # Panel 1: Latency (p95)
    axs[0, 0].plot(elapsed, [d["p95_latency_ms"] for d in data], color='#2ecc71', linewidth=2)
    axs[0, 0].fill_between(elapsed, [d["p95_latency_ms"] for d in data], color='#2ecc71', alpha=0.1)
    axs[0, 0].set_title('Inference Latency (p95)', fontsize=14, color='#ffffff')
    axs[0, 0].set_ylabel('ms', color='#aaaaaa')
    axs[0, 0].grid(True, alpha=0.1)

    # Panel 2: Warm Hit Ratio
    axs[0, 1].plot(elapsed, [d["warm_hit_ratio"] for d in data], color='#f1c40f', linewidth=2)
    axs[0, 1].set_title('Cache Warm Hit Ratio', fontsize=14, color='#ffffff')
    axs[0, 1].set_ylabel('Ratio', color='#aaaaaa')
    axs[0, 1].set_ylim(0, 1.1)
    axs[0, 1].grid(True, alpha=0.1)

    # Panel 3: Active Worker Pool (Scaling)
    axs[1, 0].step(elapsed, [d["active_workers"] for d in data], where='post', color='#3498db', linewidth=2)
    axs[1, 0].set_title('Active Infrastructure Pool', fontsize=14, color='#ffffff')
    axs[1, 0].set_ylabel('Worker Count', color='#aaaaaa')
    axs[1, 0].grid(True, alpha=0.1)

    # Panel 4: Cost Economics
    axs[1, 1].plot(elapsed, [d["accumulated_cost"] for d in data], color='#e74c3c', linewidth=2)
    axs[1, 1].set_title('Accumulated Infra Cost', fontsize=14, color='#ffffff')
    axs[1, 1].set_ylabel('USD ($)', color='#aaaaaa')
    axs[1, 1].grid(True, alpha=0.1)

    plt.tight_layout(rect=[0, 0.03, 1, 0.95])
    
    save_path = "docs/images/real_dashboard.png"
    plt.savefig(save_path, facecolor='#111111', dpi=120)
    print(f"Professional Dashboard saved to {save_path}")

if __name__ == "__main__":
    generate_pro_dashboard()
