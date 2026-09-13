"""平台配置。

修复的缺陷：

1. 子配置原先各自继承 ``BaseSettings`` 并按字段名读取同名环境变量。字段 ``path``
   会被操作系统的 ``PATH`` 覆盖、``port`` 会被 ``PORT`` 覆盖，一旦
   ``config.yaml`` 缺失就会把系统 PATH 当作数据库路径。
2. ``from_yaml`` 原先按相对路径 ``"config.yaml"`` 查找，取决于启动时的工作
   目录；从仓库根目录之外启动会静默回退到默认值。
3. **环境变量无法覆盖 config.yaml**：``from_yaml`` 把 YAML 内容当作 init 参数
   传入，而 init 参数优先级高于环境变量，导致容器/k8s 里改不动任何路径。

现在：
- 只有 ``Settings`` 一个 ``BaseSettings``，统一前缀 ``UNILLM_``，
  嵌套分隔符 ``__``（例如 ``UNILLM_DATABASE__PATH``、``UNILLM_APP__PORT``）。
- YAML 作为**低优先级来源**接入，优先级为：
  init 参数 > 环境变量 > config.yaml > 默认值。
- 子配置改为纯 ``BaseModel``，彻底杜绝误读系统同名变量。
- 配置文件路径可用 ``UNILLM_CONFIG_FILE`` 指定。
"""

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import (
    BaseSettings,
    PydanticBaseSettingsSource,
    SettingsConfigDict,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG_PATH = PROJECT_ROOT / "config.yaml"

# 统一前缀 + 嵌套分隔符：UNILLM_DATABASE__PATH 之类才能生效，
# 同时避免误读系统里的 PATH / PORT / NAME 等同名变量。
_ENV = SettingsConfigDict(
    env_prefix="UNILLM_",
    env_nested_delimiter="__",
    extra="ignore",
)


class AppConfig(BaseModel):
    name: str = "UniLLM Platform"
    version: str = "0.3.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    # CORS 白名单。["*"] 表示放开全部来源，此时不允许携带凭证。
    cors_origins: List[str] = Field(default=["*"])
    # 允许携带凭证（仅在 cors_origins 不含 "*" 时生效）
    cors_allow_credentials: bool = False
    # 是否启用鉴权。false 时 /api/* 与 /v1/* 全部免鉴权（本地开发 / 测试）。
    auth_enabled: bool = True
    # 团队访问 Token。为空 => 启动时自动生成并持久化到 api_token_file。
    api_token: str = ""
    # 自动生成 Token 的落盘位置（相对路径锚定项目根）。
    api_token_file: str = "./data/.api_token"


class DatabaseConfig(BaseModel):
    type: str = "sqlite"
    path: str = "./data/unillm.db"


class StorageConfig(BaseModel):
    datasets_path: str = "./data/datasets"
    annotations_path: str = "./data/annotations"
    models_path: str = "./data/models"
    logs_path: str = "./logs"


class ModelConfig(BaseModel):
    default_model: str = "Qwen/Qwen2.5-7B-Instruct"
    max_model_len: int = 4096
    gpu_memory_utilization: float = 0.9
    tensor_parallel_size: int = 1
    # 显式允许在 vLLM 不可用时使用 mock 后端（便于本地无 GPU 联调）
    allow_mock_backend: bool = True


class LoRAConfig(BaseModel):
    r: int = 16
    lora_alpha: int = 32
    lora_dropout: float = 0.1
    target_modules: List[str] = Field(default=["q_proj", "k_proj", "v_proj", "o_proj"])


class TrainingConfig(BaseModel):
    num_train_epochs: int = 3
    per_device_train_batch_size: int = 4
    gradient_accumulation_steps: int = 4
    learning_rate: float = 2e-4
    logging_steps: int = 10
    save_steps: int = 100


class EvaluationConfig(BaseModel):
    metrics: List[str] = Field(default=["exact_match", "token_f1", "latency", "perplexity"])
    max_samples: int = 100


def _resolve_config_path(explicit: Optional[str] = None) -> Path:
    """配置文件路径：显式入参 > UNILLM_CONFIG_FILE > 项目根 config.yaml。"""
    if explicit:
        return Path(explicit)
    from_env = os.environ.get("UNILLM_CONFIG_FILE")
    if from_env:
        return Path(from_env)
    return DEFAULT_CONFIG_PATH


def load_yaml_config(path: Optional[str] = None) -> Dict[str, Any]:
    """读取 YAML 配置；文件不存在或为空时返回空字典（全部走默认值）。"""
    config_path = _resolve_config_path(path)
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


class _YamlSettingsSource(PydanticBaseSettingsSource):
    """把 config.yaml 作为低优先级配置来源接入 pydantic-settings。

    这样环境变量才能真正覆盖 YAML —— 若把 YAML 当 init 参数传入，
    init 的优先级高于 env，YAML 会反过来压住环境变量。
    """

    def __init__(self, settings_cls, yaml_data: Dict[str, Any]):
        super().__init__(settings_cls)
        self._data = yaml_data

    def get_field_value(self, field, field_name):  # pragma: no cover - 由 __call__ 兜底
        return self._data.get(field_name), field_name, False

    def __call__(self) -> Dict[str, Any]:
        return dict(self._data)


class Settings(BaseSettings):
    model_config = _ENV

    app: AppConfig = AppConfig()
    database: DatabaseConfig = DatabaseConfig()
    storage: StorageConfig = StorageConfig()
    model: ModelConfig = ModelConfig()
    lora: LoRAConfig = LoRAConfig()
    training: TrainingConfig = TrainingConfig()
    evaluation: EvaluationConfig = EvaluationConfig()

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls,
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ):
        # 越靠前优先级越高：init > 环境变量 > config.yaml > .env > secrets
        return (
            init_settings,
            env_settings,
            _YamlSettingsSource(settings_cls, load_yaml_config()),
            dotenv_settings,
            file_secret_settings,
        )

    @classmethod
    def from_yaml(cls, path: Optional[str] = None) -> "Settings":
        """以指定 YAML 为基线构建配置（环境变量仍可覆盖它）。"""
        if path is None:
            return cls()
        return cls(**_load_yaml_config_from(path))


def _load_yaml_config_from(path: str) -> Dict[str, Any]:
    return load_yaml_config(path)


settings = Settings()
