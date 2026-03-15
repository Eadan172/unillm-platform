from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import yaml
from pathlib import Path


class AppConfig(BaseSettings):
    name: str = "UniLLM Platform"
    version: str = "0.1.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000


class DatabaseConfig(BaseSettings):
    type: str = "sqlite"
    path: str = "./data/unillm.db"


class StorageConfig(BaseSettings):
    datasets_path: str = "./data/datasets"
    annotations_path: str = "./data/annotations"
    models_path: str = "./data/models"
    logs_path: str = "./logs"


class ModelConfig(BaseSettings):
    default_model: str = "Qwen/Qwen2.5-7B-Instruct"
    max_model_len: int = 4096
    gpu_memory_utilization: float = 0.9
    tensor_parallel_size: int = 1


class LoRAConfig(BaseSettings):
    r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    target_modules: list[str] = Field(default=["q_proj", "k_proj", "v_proj", "o_proj"])


class TrainingConfig(BaseSettings):
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    logging_steps: int = 10
    save_steps: int = 100


class EvaluationConfig(BaseSettings):
    metrics: list[str] = Field(default=["perplexity", "accuracy", "latency"])


class Settings(BaseSettings):
    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    storage: StorageConfig = StorageConfig()
    model: ModelConfig = ModelConfig()
    lora: LoRAConfig = LoRAConfig()
    training: TrainingConfig = TrainingConfig()
    evaluation: EvaluationConfig = EvaluationConfig()

    @classmethod
    def from_yaml(cls, path: str = "config.yaml") -> "Settings":
        config_path = Path(path)
        if config_path.exists():
            with open(config_path, "r", encoding="utf-8") as f:
                config_data = yaml.safe_load(f)
            return cls(**config_data)
        return cls()


settings = Settings.from_yaml()
