import os
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from rl.environment import InferenceSimulationEnv

def train():
    os.makedirs("models", exist_ok=True)
    
    env = make_vec_env(lambda: InferenceSimulationEnv(max_steps=2000), n_envs=4)
    
    print("Starting offline PPO training on Synthetic Simulation Environment...")
    model = PPO("MlpPolicy", env, verbose=1)
    
    model.learn(total_timesteps=50000)
    
    model.save("models/ppo_v2.zip")
    print("Training complete. Model saved to models/ppo_v2.zip")

if __name__ == "__main__":
    train()
