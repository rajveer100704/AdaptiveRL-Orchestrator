import os
from stable_baselines3 import PPO
from rl.capacity_environment import CapacitySimulationEnv
from shared.logging import setup_logging

logger = setup_logging()

def train_capacity_model():
    logger.info("starting_capacity_training")
    
    env = CapacitySimulationEnv(max_steps=600)
    
    model = PPO(
        "MlpPolicy",
        env,
        verbose=1,
        learning_rate=0.0003,
        n_steps=2048,
        batch_size=64,
        n_epochs=10,
        gamma=0.99, # High gamma for delayed rewards
        gae_lambda=0.95,
        clip_range=0.2,
        ent_coef=0.01
    )
    
    logger.info("training_capacity_model", total_timesteps=30000)
    model.learn(total_timesteps=30000)
    
    os.makedirs("models", exist_ok=True)
    save_path = "models/ppo_capacity_v1.zip"
    model.save(save_path)
    logger.info("training_complete", path=save_path)

if __name__ == "__main__":
    train_capacity_model()
