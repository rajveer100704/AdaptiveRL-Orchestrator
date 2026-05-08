# Platform Demo: Adaptive RL Orchestrator Comparison

This demo showcases the **causal legitimacy** of the platform by comparing the PPO-based adaptive control plane against traditional systems heuristics.

## 1. The Performance Gap (Visual Comparison)
![Project Comparison](images/project_comparison_infographic.png)

## 2. Live Platform Demo
![Live Platform Demo](images/platform_demo.webp)

## 3. Hard Proof: PPO vs. Heuristics

Derived directly from our [**`verification_report.md`**](../benchmarks/results/verification_report.md), these metrics represent identical stress-test conditions.

| Strategy | p95 Latency | Warm Hit Ratio | Scaling Stability | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Traditional Heuristic** | 1513.1ms | 28.1% | Oscillating | ❌ Fail |
| **Adaptive RL (PPO)** | **353.9ms** | **84.7%** | **Proactive** | ✅ Pass |

## 4. Demo Flow: The Failure Story

1.  **Phase 1 (Heuristic Failure)**: Standard routers (LeastLoaded) ignore model locality. This triggers a "Cold Start Storm," where p95 latency spikes to 1.5s as every request forces a cache reload.
2.  **Phase 2 (PPO Stabilization)**: The PPO agent learns to **sacrifice queue balance for cache affinity**. It routes requests to busy workers that are "warm," reducing latency by **76%**.
3.  **Phase 3 (Scaling Hysteresis)**: While standard autoscalers are reactive and laggy, the PPO Capacity Agent performs **Anticipatory Pre-warming**, spawning workers 30s before the burst hits.

## 4. Verification & Observability
- **Distributed Traces**: Every decision is visible in Jaeger (OTEL).
- **Hard Artifacts**: Reproduce these results anytime with `make eval`.
