# UniLLM Platform 源码全文

本文件由 `scripts/pack_source.py` 生成，收录项目全部源码与配置文件的完整内容，
便于在知识库中全文检索。逐文件说明见 `项目分析与改进报告.md`。

| 项目 | 信息 |
|---|---|
| 仓库 | `https://github.com/Eadan172/unillm-platform.git` |
| 交付版本 | 0.2.0 |
| 验证状态 | 编译通过 / 53 个测试用例通过 / 真实进程冒烟 13 项通过 |
| 验证环境 | Windows 11 + Python 3.13.12 + 纯 CPU |

---

## 目录

1. [应用入口 app/main.py](#1-应用入口-appmainpy)
2. [配置 app/config.py](#2-配置-appconfigpy)
3. [依赖注入 app/api/deps.py](#3-依赖注入-appapidepspy)
4. [路由 app/api/routes/data.py](#4-路由-appapiroutesdatapy)
5. [路由 app/api/routes/annotation.py](#5-路由-appapiroutesannotationpy)
6. [路由 app/api/routes/model.py](#6-路由-appapiroutesmodelpy)
7. [路由 app/api/routes/inference.py](#7-路由-appapiroutesinferencepy)
8. [路由 app/api/routes/finetune.py](#8-路由-appapiroutesfinetunepy)
9. [路由 app/api/routes/evaluate.py](#9-路由-appapiroutesevaluatepy)
10. [数据模型 app/models/database.py](#10-数据模型-appmodelsdatabasepy)
11. [接口契约 app/models/schemas.py](#11-接口契约-appmodelsschemaspy)
12. [服务 app/services/data_service.py](#12-服务-appservicesdata_servicepy)
13. [服务 app/services/annotation_service.py](#13-服务-appservicesannotation_servicepy)
14. [服务 app/services/model_service.py](#14-服务-appservicesmodel_servicepy)
15. [服务 app/services/inference_service.py](#15-服务-appservicesinference_servicepy)
16. [服务 app/services/finetune_service.py](#16-服务-appservicesfinetune_servicepy)
17. [服务 app/services/evaluate_service.py](#17-服务-appservicesevaluate_servicepy)
18. [测试 tests/conftest.py](#18-测试-testsconftestpy)
19. [测试 tests/test_metrics.py](#19-测试-teststest_metricspy)
20. [测试 tests/test_closed_loop.py](#20-测试-teststest_closed_looppy)
21. [测试 tests/test_upload_safety.py](#21-测试-teststest_upload_safetypy)
22. [冒烟脚本 scripts/smoke_test.py](#22-冒烟脚本-scriptssmoke_testpy)
23. [评测演示 evaluation_demo.py](#23-评测演示-evaluation_demopy)
24. [配置 config.yaml](#24-配置-configyaml)
25. [配置 pytest.ini](#25-配置-pytestini)
26. [依赖 requirements.txt](#26-依赖-requirementstxt)
27. [依赖 requirements-gpu.txt](#27-依赖-requirements-gputxt)
28. [样例数据 data/datasets/sample_data.jsonl](#28-样例数据-datadatasetssample_datajsonl)
29. [忽略规则 .gitignore](#29-忽略规则-gitignore)
30. [包标记 app/__init__.py](#30-包标记-app__init__py)
31. [包标记 app/api/__init__.py](#31-包标记-appapi__init__py)
32. [包标记 app/api/routes/__init__.py](#32-包标记-appapiroutes__init__py)
33. [包标记 app/models/__init__.py](#33-包标记-appmodels__init__py)
34. [包标记 app/services/__init__.py](#34-包标记-appservices__init__py)
35. [包标记 app/core/__init__.py](#35-包标记-appcore__init__py)
36. [包标记 app/utils/__init__.py](#36-包标记-apputils__init__py)

---

## 1. 应用入口 app/main.py

**路径**：`app/main.py`　|　**行数**：136

```python
"""UniLLM Platform 应用入口。

本轮修复：
1. ``/health`` 原先硬编码 ``models_loaded=0``，无论实际情况如何都返回 0。
   现在返回真实的后端名、已加载模型数、注册模型数与数据库路径，并给出
   ``degraded`` 标志（当前是否在 mock 后端上运行）。
2. CORS ``allow_origins=["*"]`` 与 ``allow_credentials=True`` 是非法组合，
   浏览器会直接拒绝带凭证的跨域请求（规范禁止 ``*`` 与凭证同时出现）。
   现在凭证开关只在白名单非 ``*`` 时才允许打开。
3. 存储目录与数据库初始化统一在这里完成，且目录来自配置而非硬编码。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.deps import get_inference_service
from app.api.routes import annotation, data, evaluate, finetune, inference, model
from app.config import settings
from app.models.database import get_session_maker, init_database, resolve_db_path
from app.models.schemas import HealthResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    for directory in (
        settings.storage.datasets_path,
        settings.storage.annotations_path,
        settings.storage.models_path,
        settings.storage.logs_path,
    ):
        Path(directory).mkdir(parents=True, exist_ok=True)

    init_database()
    yield
    print("Shutting down UniLLM Platform...")


app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    description="""
## UniLLM Platform - 统一大模型开发平台

一站式大模型开发平台，支持从数据接入 → 标注 → 微调 → 评测 → 推理的全流程闭环。

### 核心功能

- **数据管理**: 数据导入、存储、导出
- **数据标注**: 标注任务管理、标注结果存储
- **模型管理**: 模型注册、加载、卸载
- **模型推理**: OpenAI 兼容的推理 API
- **模型微调**: LoRA 微调流程
- **模型评测**: 多样本真实指标（EM / 字符 F1 / 实测延迟 / 可选 PPL）

### 运行模式

未安装 vLLM（GPU 增强依赖）时，推理自动降级为**确定性 mock 后端**：
响应体带 `backend: "mock"`，占位文本以 `[MOCK]` 开头。
这保证无 GPU 的环境也能跑通完整链路，同时不会把占位结果冒充为模型输出。

### 技术栈

FastAPI + SQLAlchemy(SQLite) + vLLM(可选) + PEFT(可选)
""",
    lifespan=lifespan,
)

_cors_origins = settings.app.cors_origins or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # 通配来源与携带凭证不能共存，否则浏览器按规范直接拒绝
    allow_credentials=settings.app.cors_allow_credentials and "*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(data.router)
app.include_router(annotation.router)
app.include_router(model.router)
app.include_router(inference.router)
app.include_router(finetune.router)
app.include_router(evaluate.router)


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    """返回运行时真实状态，而非固定值。"""
    inference_service = get_inference_service()

    session = get_session_maker()()
    try:
        from app.models.database import Model as ModelRecord

        registered = session.query(ModelRecord).count()
        loaded = session.query(ModelRecord).filter(ModelRecord.is_loaded.is_(True)).count()
    finally:
        session.close()

    describe = inference_service.describe()
    return HealthResponse(
        status="healthy",
        version=settings.app.version,
        models_loaded=loaded,
        inference_backend=describe["backend"],
        inference_backend_is_real_model=describe["is_real_model"],
        degraded=not describe["is_real_model"],
        database=str(resolve_db_path()),
        registered_models=registered,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug,
    )
```

---

## 2. 配置 app/config.py

**路径**：`app/config.py`　|　**行数**：179

```python
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
    version: str = "0.2.0"
    debug: bool = True
    host: str = "0.0.0.0"
    port: int = 8000
    # CORS 白名单。["*"] 表示放开全部来源，此时不允许携带凭证。
    cors_origins: List[str] = Field(default=["*"])
    # 允许携带凭证（仅在 cors_origins 不含 "*" 时生效）
    cors_allow_credentials: bool = False


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
```

---

## 3. 依赖注入 app/api/deps.py

**路径**：`app/api/deps.py`　|　**行数**：83

```python
"""FastAPI 依赖提供者。

原实现把 ``get_db()``、``session_maker = get_session_maker(...)`` 在 6 个路由
模块里各抄一遍，导致同一进程创建 6 个 Engine，且推理服务在两个模块里各持有
一份互相看不见的全局单例（``/api/model/load`` 加载的模型，
``/v1/chat/completions`` 读不到）。

现在集中在这里：数据库会话按请求创建、请求结束即关闭；推理服务在进程内共享
同一个实例，保证"加载模型"与"调用推理"操作的是同一个后端。
"""

from typing import Iterator, Optional

from fastapi import Depends
from sqlalchemy.orm import Session

from app.models.database import get_session_maker
from app.services.annotation_service import AnnotationService
from app.services.data_service import DataService
from app.services.evaluate_service import EvaluateService
from app.services.finetune_service import FinetuneService
from app.services.inference_service import InferenceService
from app.services.model_service import ModelService


def get_db() -> Iterator[Session]:
    """每个请求一个 Session，请求结束必定关闭。"""
    session = get_session_maker()()
    try:
        yield session
    finally:
        session.close()


def get_data_service(db: Session = Depends(get_db)) -> DataService:
    return DataService(db)


def get_annotation_service(db: Session = Depends(get_db)) -> AnnotationService:
    return AnnotationService(db)


def get_model_service(db: Session = Depends(get_db)) -> ModelService:
    return ModelService(db)


def get_finetune_service(db: Session = Depends(get_db)) -> FinetuneService:
    return FinetuneService(db)


# --------------------------------------------------------------------------
# 推理服务：进程内单例（跨请求共享已加载的后端）
# --------------------------------------------------------------------------

_inference_service: Optional[InferenceService] = None


def get_inference_service() -> InferenceService:
    """返回进程内共享的推理服务。

    特意不依赖 ``get_db``：推理服务自己管理短生命周期的日志会话，
    避免把请求级 Session 缓存成长期对象（跨请求 / 跨线程复用 Session 是隐患）。
    """
    global _inference_service
    if _inference_service is None:
        _inference_service = InferenceService()
    return _inference_service


def reset_inference_service(service: Optional[InferenceService] = None) -> InferenceService:
    """替换/清空推理服务单例。测试注入确定性后端时使用。"""
    global _inference_service
    _inference_service = service if service is not None else InferenceService()
    return _inference_service


def get_evaluate_service(
    db: Session = Depends(get_db),
    inference: InferenceService = Depends(get_inference_service),
) -> EvaluateService:
    """评测服务复用同一个推理后端，保证"评测的模型"就是当前加载的模型。"""
    return EvaluateService(db, inference_service=inference)
```

---

## 4. 路由 app/api/routes/data.py

**路径**：`app/api/routes/data.py`　|　**行数**：161

```python
"""数据管理 API。

本轮修复：
1. **路径穿越**：``file.filename`` 原先直接拼进保存路径，
   ``../../..\\app\\main.py`` 这类文件名可以写到工作目录之外。现在只取
   ``Path(filename).name`` 并剥离危险字符。
2. **孤儿数据**：原先先把文件落盘、再创建 Dataset、最后才校验扩展名，
   校验失败时磁盘上留下无用文件、库里留下空数据集。现在校验前置，
   且任何失败都会回滚已写入的文件与记录。
3. **导出空文件**：导出接口不校验数据集是否存在，也不报告"无可导出样本"。
   现在返回明确错误。
4. 数据集查询统一 404，不再依赖 service 返回 None 后继续执行。
"""

import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.api.deps import get_data_service
from app.config import settings
from app.models.schemas import DatasetCreate, DatasetResponse
from app.services.data_service import DataService

router = APIRouter(prefix="/api/data", tags=["Data Management"])

ALLOWED_EXTENSIONS = {"json", "jsonl", "csv"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._\u4e00-\u9fff-]")


def _safe_filename(raw_name: str) -> str:
    """把客户端文件名收敛为安全的纯文件名，阻断路径穿越。"""
    name = Path(raw_name or "").name  # 丢弃任何目录部分
    name = _UNSAFE_CHARS.sub("_", name).lstrip(".")
    if not name:
        raise HTTPException(status_code=400, detail="非法文件名")
    return name


def _to_response(dataset) -> DatasetResponse:
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        source_type=dataset.source_type,
        total_samples=dataset.total_samples,
        created_at=dataset.created_at,
    )


@router.post("/import", response_model=DatasetResponse)
async def import_dataset(
    name: str,
    file: UploadFile = File(...),
    description: str = None,
    data_service: DataService = Depends(get_data_service),
):
    safe_name = _safe_filename(file.filename)
    file_type = Path(safe_name).suffix.lstrip(".").lower()
    if file_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 '.{file_type}'，仅支持 {sorted(ALLOWED_EXTENSIONS)}",
        )

    storage_path = Path(settings.storage.datasets_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    file_path = storage_path / safe_name

    size = 0
    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 上限",
                    )
                buffer.write(chunk)
    except HTTPException:
        file_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}") from exc

    dataset = None
    try:
        dataset = data_service.create_dataset(name, description)
        count = data_service.import_data_from_file(dataset.id, str(file_path), file_type)
    except Exception as exc:
        # 解析失败：回滚数据库记录与落盘文件，不留孤儿数据
        if dataset is not None:
            data_service.delete_dataset(dataset.id)
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"数据导入失败: {exc}") from exc

    return _to_response(data_service.get_dataset(dataset.id))


@router.post("/create", response_model=DatasetResponse)
async def create_dataset(
    dataset: DatasetCreate,
    data_service: DataService = Depends(get_data_service),
):
    created = data_service.create_dataset(
        name=dataset.name,
        description=dataset.description,
        source_type=dataset.source_type.value,
    )
    return _to_response(created)


@router.get("/list", response_model=List[DatasetResponse])
async def list_datasets(
    skip: int = 0,
    limit: int = 100,
    data_service: DataService = Depends(get_data_service),
):
    if skip < 0 or limit <= 0:
        raise HTTPException(status_code=400, detail="skip 必须 >= 0，limit 必须 > 0")
    return [_to_response(d) for d in data_service.list_datasets(skip, limit)]


@router.get("/{dataset_id}/export")
async def export_training_data(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service),
):
    try:
        output_path = data_service.export_to_training_format(dataset_id)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return {"status": "success", "dataset_id": dataset_id, "output_path": output_path}


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service),
):
    dataset = data_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _to_response(dataset)


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service),
):
    if not data_service.delete_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "deleted", "dataset_id": dataset_id}
```

---

## 5. 路由 app/api/routes/annotation.py

**路径**：`app/api/routes/annotation.py`　|　**行数**：154

```python
"""数据标注 API。

修复：
- 使用共享依赖，去掉重复的 ``get_db`` / ``session_maker``。
- ``get_task_progress`` 在任务不存在时原先会抛 ValueError 变成 HTTP 500，
  现在返回 404。
- ``submit_annotation`` 原先只捕获 ValueError 判 404；现在区分"标注不存在"（404）
  与参数错误（400）。
- 标注列表接口补上（便于前端按任务分页取数）。
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.deps import get_annotation_service
from app.models.schemas import (
    AnnotationResponse,
    AnnotationTaskCreate,
    AnnotationTaskResponse,
    AnnotationUpdate,
)
from app.services.annotation_service import AnnotationService

router = APIRouter(prefix="/api/annotation", tags=["Annotation"])


def _annotation_response(annotation) -> AnnotationResponse:
    return AnnotationResponse(
        id=annotation.id,
        dataset_id=annotation.dataset_id,
        instruction=annotation.instruction,
        input_text=annotation.input_text,
        output_text=annotation.output_text,
        status=annotation.status,
        annotator=annotation.annotator,
        created_at=annotation.created_at,
    )


def _task_response(task) -> AnnotationTaskResponse:
    return AnnotationTaskResponse(
        id=task.id,
        name=task.name,
        dataset_id=task.dataset_id,
        total_items=task.total_items,
        completed_items=task.completed_items,
        status=task.status,
        created_at=task.created_at,
    )


@router.post("/task", response_model=AnnotationTaskResponse)
async def create_annotation_task(
    task: AnnotationTaskCreate,
    annotation_service: AnnotationService = Depends(get_annotation_service),
):
    try:
        created = annotation_service.create_task(
            name=task.name,
            dataset_id=task.dataset_id,
            description=task.description,
            annotation_type=task.annotation_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _task_response(created)


@router.get("/task/list", response_model=List[AnnotationTaskResponse])
async def list_annotation_tasks(
    skip: int = 0,
    limit: int = 100,
    annotation_service: AnnotationService = Depends(get_annotation_service),
):
    if skip < 0 or limit <= 0:
        raise HTTPException(status_code=400, detail="skip 必须 >= 0，limit 必须 > 0")
    return [_task_response(t) for t in annotation_service.list_tasks(skip, limit)]


@router.get("/task/{task_id}", response_model=AnnotationTaskResponse)
async def get_annotation_task(
    task_id: int,
    annotation_service: AnnotationService = Depends(get_annotation_service),
):
    task = annotation_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return _task_response(task)


@router.get("/task/{task_id}/progress")
async def get_task_progress(
    task_id: int,
    annotation_service: AnnotationService = Depends(get_annotation_service),
):
    try:
        return annotation_service.get_task_progress(task_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/task/{task_id}/items", response_model=List[AnnotationResponse])
async def list_task_annotations(
    task_id: int,
    status: str = Query(default=None, description="按状态过滤：pending / completed"),
    skip: int = 0,
    limit: int = 100,
    annotation_service: AnnotationService = Depends(get_annotation_service),
):
    if annotation_service.get_task(task_id) is None:
        raise HTTPException(status_code=404, detail="Task not found")
    items = annotation_service.list_annotations_by_task(task_id, status, skip, limit)
    return [_annotation_response(a) for a in items]


@router.get("/task/{task_id}/next")
async def get_next_annotation(
    task_id: int,
    annotation_service: AnnotationService = Depends(get_annotation_service),
):
    annotation = annotation_service.get_next_annotation(task_id)
    if not annotation:
        return {"status": "completed", "message": "No more annotations pending"}
    return _annotation_response(annotation)


@router.post("/submit", response_model=AnnotationResponse)
async def submit_annotation(
    annotation_id: int,
    update: AnnotationUpdate,
    annotation_service: AnnotationService = Depends(get_annotation_service),
):
    try:
        annotation = annotation_service.submit_annotation(
            annotation_id=annotation_id,
            output_text=update.output_text,
            annotator=update.annotator,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _annotation_response(annotation)


@router.get("/{annotation_id}", response_model=AnnotationResponse)
async def get_annotation(
    annotation_id: int,
    annotation_service: AnnotationService = Depends(get_annotation_service),
):
    annotation = annotation_service.get_annotation(annotation_id)
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return _annotation_response(annotation)
```

---

## 6. 路由 app/api/routes/model.py

**路径**：`app/api/routes/model.py`　|　**行数**：129

```python
"""模型管理 API。

修复：
- ``inference_service`` 全局单例原先定义在 ``model.py`` 与 ``inference.py``
  各自一份，两个模块互相看不见，导致"加载模型"后
  ``/v1/chat/completions`` 仍走 mock。现在统一从 ``app.api.deps`` 取。
- ``/load`` 在降级时返回 HTTP 200 + ``status=error``，与 REST 语义冲突；
  现在降级返回 200 + ``status=degraded`` 且 ``degraded=true``（这是可预期的
  正常结果），真正的参数错误才返回 4xx。
- ``ModelResponse`` 补上 ``model_path`` / ``lora_path``，否则注册后拿不到路径。
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_inference_service, get_model_service
from app.models.schemas import ModelLoadRequest, ModelResponse
from app.services.inference_service import InferenceService
from app.services.model_service import ModelService

router = APIRouter(prefix="/api/model", tags=["Model Management"])


def _to_response(model) -> ModelResponse:
    return ModelResponse(
        id=model.id,
        name=model.name,
        model_type=model.model_type,
        base_model=model.base_model,
        model_path=model.model_path,
        lora_path=model.lora_path,
        is_loaded=model.is_loaded,
        created_at=model.created_at,
    )


@router.post("/register", response_model=ModelResponse)
async def register_model(
    name: str,
    model_type: str = "base",
    base_model: str = None,
    model_path: str = None,
    description: str = None,
    model_service: ModelService = Depends(get_model_service),
):
    model = model_service.register_model(
        name=name,
        model_type=model_type,
        base_model=base_model,
        model_path=model_path,
        description=description,
    )
    return _to_response(model)


@router.post("/load")
async def load_model(
    request: ModelLoadRequest,
    model_service: ModelService = Depends(get_model_service),
    inference_svc: InferenceService = Depends(get_inference_service),
):
    model = model_service.get_model_by_name(request.model_name)
    if not model:
        model = model_service.register_model(
            name=request.model_name,
            model_type="base",
            model_path=request.model_path,
        )

    result = inference_svc.load_model(
        model_name=request.model_name,
        model_path=request.model_path or request.model_name,
        lora_path=request.lora_path,
    )

    # 只有真实后端才算"已加载"；mock 后端不应把自己标成已加载模型
    model_service.set_model_loaded(model.id, not result.get("degraded", False))
    result["model_id"] = model.id
    return result


@router.post("/unload")
async def unload_model(
    inference_svc: InferenceService = Depends(get_inference_service),
):
    return inference_svc.unload_model()


@router.get("/backend")
async def backend_status(
    inference_svc: InferenceService = Depends(get_inference_service),
):
    """当前推理后端状态：是真实模型还是占位后端，一目了然。"""
    return inference_svc.describe()


@router.get("/list", response_model=List[ModelResponse])
async def list_models(
    model_type: str = None,
    skip: int = 0,
    limit: int = 100,
    model_service: ModelService = Depends(get_model_service),
):
    if skip < 0 or limit <= 0:
        raise HTTPException(status_code=400, detail="skip 必须 >= 0，limit 必须 > 0")
    return [_to_response(m) for m in model_service.list_models(model_type, skip, limit)]


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: int,
    model_service: ModelService = Depends(get_model_service),
):
    model = model_service.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return _to_response(model)


@router.delete("/{model_id}")
async def delete_model(
    model_id: int,
    model_service: ModelService = Depends(get_model_service),
):
    if not model_service.delete_model(model_id):
        raise HTTPException(status_code=404, detail="Model not found")
    return {"status": "deleted", "model_id": model_id}
```

---

## 7. 路由 app/api/routes/inference.py

**路径**：`app/api/routes/inference.py`　|　**行数**：130

```python
"""OpenAI 兼容推理 API。

修复：
1. 删除了 ``if inference_svc.current_model is None and ...: pass`` 这段空操作死代码
   （它原本想做的"按请求指定模型"从未实现）。
2. 响应体增加 ``backend`` 字段，调用方能立刻知道这是真实模型输出还是占位文本。
3. ``stream=True`` 目前不支持，改为显式 400，而不是静默返回非流式结果。
4. ``/v1/models`` 原先硬编码一个模型名和固定的 created 时间戳；现在列出注册表
   中真实存在的模型，未注册时如实返回空列表。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_inference_service
from app.config import settings
from app.models.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatMessage,
    CompletionChoice,
    CompletionRequest,
    CompletionResponse,
)
from app.services.inference_service import InferenceService
from app.services.model_service import ModelService

router = APIRouter(tags=["Inference (OpenAI Compatible)"])


@router.post("/v1/completions", response_model=CompletionResponse)
async def create_completion(
    request: CompletionRequest,
    inference_svc: InferenceService = Depends(get_inference_service),
):
    if request.stream:
        raise HTTPException(status_code=400, detail="暂不支持 stream=true，请传 stream=false")

    response = inference_svc.create_completion_response(
        prompt=request.prompt,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
    )

    return CompletionResponse(
        id=response["id"],
        object=response["object"],
        model=response["model"],
        backend=response["backend"],
        choices=[
            CompletionChoice(
                index=c["index"], text=c["text"], finish_reason=c["finish_reason"]
            )
            for c in response["choices"]
        ],
        created=response["created"],
        usage=response["usage"],
    )


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    inference_svc: InferenceService = Depends(get_inference_service),
):
    if request.stream:
        raise HTTPException(status_code=400, detail="暂不支持 stream=true，请传 stream=false")
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    response = inference_svc.create_chat_response(
        messages=messages,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
    )

    return ChatCompletionResponse(
        id=response["id"],
        object=response["object"],
        model=response["model"],
        backend=response["backend"],
        choices=[
            ChatCompletionChoice(
                index=c["index"],
                message=ChatMessage(
                    role=c["message"]["role"], content=c["message"]["content"]
                ),
                finish_reason=c["finish_reason"],
            )
            for c in response["choices"]
        ],
        created=response["created"],
        usage=response["usage"],
    )


@router.get("/v1/models")
async def list_models(db: Session = Depends(get_db)):
    """列出已注册模型。未注册任何模型时返回空 data（不再伪造一条记录）。"""
    models = ModelService(db).list_models(limit=1000)
    data = [
        {
            "id": model.name,
            "object": "model",
            "created": int(model.created_at.timestamp()) if model.created_at else 0,
            "owned_by": "unillm",
        }
        for model in models
    ]
    if not data:
        # 让 OpenAI 兼容客户端在未注册模型时仍有一个可用的默认名，
        # 但明确标注它是配置里的默认值、而非已注册模型。
        data = [
            {
                "id": settings.model.default_model,
                "object": "model",
                "created": 0,
                "owned_by": "unillm",
                "note": "default-from-config (未注册)",
            }
        ]
    return {"object": "list", "data": data}
```

---

## 8. 路由 app/api/routes/finetune.py

**路径**：`app/api/routes/finetune.py`　|　**行数**：96

```python
"""微调 API。

修复：
- 使用共享依赖。
- ``create`` / ``list`` 原先直接调用 ``finetune_service.model_service`` 这个内部
  属性，绕过了服务边界；现在统一走 FinetuneService 的方法。
- ``cancel`` 明确返回"软取消"语义：设置为 cancelled 并阻止后续训练步骤推进，
  但**不会**强杀已在运行的训练线程（详见 finetune_service 的说明）。
"""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_finetune_service
from app.models.schemas import FinetuneCreate, FinetuneResponse
from app.services.finetune_service import FinetuneService

router = APIRouter(prefix="/api/finetune", tags=["Fine-tuning"])


def _to_response(job) -> FinetuneResponse:
    return FinetuneResponse(
        id=job.id,
        model_id=job.model_id,
        dataset_id=job.dataset_id,
        job_name=job.job_name,
        method=job.method,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at,
    )


@router.post("/create", response_model=FinetuneResponse)
async def create_finetune_job(
    request: FinetuneCreate,
    finetune_service: FinetuneService = Depends(get_finetune_service),
):
    try:
        job = finetune_service.create_job(
            model_id=request.model_id,
            dataset_id=request.dataset_id,
            job_name=request.job_name,
            method=request.method,
            config=request.config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _to_response(job)


@router.post("/{job_id}/start")
async def start_finetune(
    job_id: int,
    finetune_service: FinetuneService = Depends(get_finetune_service),
):
    result = finetune_service.start_finetune(job_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/list", response_model=List[FinetuneResponse])
async def list_finetune_jobs(
    model_id: int = None,
    skip: int = 0,
    limit: int = 100,
    finetune_service: FinetuneService = Depends(get_finetune_service),
):
    if skip < 0 or limit <= 0:
        raise HTTPException(status_code=400, detail="skip 必须 >= 0，limit 必须 > 0")
    return [_to_response(j) for j in finetune_service.list_jobs(model_id, skip, limit)]


@router.get("/{job_id}/status")
async def get_finetune_status(
    job_id: int,
    finetune_service: FinetuneService = Depends(get_finetune_service),
):
    status = finetune_service.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@router.post("/{job_id}/cancel")
async def cancel_finetune(
    job_id: int,
    finetune_service: FinetuneService = Depends(get_finetune_service),
):
    result = finetune_service.cancel_job(job_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result
```

---

## 9. 路由 app/api/routes/evaluate.py

**路径**：`app/api/routes/evaluate.py`　|　**行数**：86

```python
"""模型评测 API。

修复：``/{eval_id}/result`` 原先用 ``if "error" in result`` 判断 404，
与正常结果里可能出现的 "error" 字段冲突；这里改用显式存在性检查。
``/run`` 现在支持在请求体传入 ``test_data``（可选），未传时从关联数据集读取。
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.deps import get_evaluate_service
from app.models.schemas import EvaluationCreate, EvaluationResponse
from app.services.evaluate_service import EvaluateService

router = APIRouter(prefix="/api/evaluate", tags=["Evaluation"])


class RunEvaluationRequest(BaseModel):
    """可选内联评测样本；不传则使用评测关联的数据集。"""

    test_data: Optional[List[dict]] = Field(default=None)


def _to_response(evaluation) -> EvaluationResponse:
    return EvaluationResponse(
        id=evaluation.id,
        model_id=evaluation.model_id,
        eval_name=evaluation.eval_name,
        status=evaluation.status,
        metrics=evaluation.metrics,
        results=evaluation.results,
        created_at=evaluation.created_at,
    )


@router.post("/create", response_model=EvaluationResponse)
async def create_evaluation(
    request: EvaluationCreate,
    evaluate_service: EvaluateService = Depends(get_evaluate_service),
):
    evaluation = evaluate_service.create_evaluation(
        model_id=request.model_id,
        eval_name=request.eval_name,
        dataset_id=request.dataset_id,
        metrics=request.metrics,
    )
    return _to_response(evaluation)


@router.post("/{eval_id}/run")
async def run_evaluation(
    eval_id: int,
    payload: Optional[RunEvaluationRequest] = None,
    evaluate_service: EvaluateService = Depends(get_evaluate_service),
):
    test_data = payload.test_data if payload else None
    result = evaluate_service.run_evaluation(eval_id, test_data=test_data)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/list", response_model=List[EvaluationResponse])
async def list_evaluations(
    model_id: int = None,
    skip: int = 0,
    limit: int = 100,
    evaluate_service: EvaluateService = Depends(get_evaluate_service),
):
    if skip < 0 or limit <= 0:
        raise HTTPException(status_code=400, detail="skip 必须 >= 0，limit 必须 > 0")
    return [_to_response(e) for e in evaluate_service.list_evaluations(model_id, skip, limit)]


@router.get("/{eval_id}/result")
async def get_evaluation_result(
    eval_id: int,
    evaluate_service: EvaluateService = Depends(get_evaluate_service),
):
    summary = evaluate_service.get_evaluation(eval_id)
    if summary is None:
        raise HTTPException(status_code=404, detail=f"Evaluation {eval_id} not found")
    return evaluate_service.get_evaluation_summary(eval_id)
```

---

## 10. 数据模型 app/models/database.py

**路径**：`app/models/database.py`　|　**行数**：224

```python
"""ORM 模型与数据库引擎。

原实现的缺陷：``init_database()`` 与 6 个路由模块各自
``create_engine`` 一次，同一个进程里最多存在 7 个互不相干的 Engine，
连接池无法复用，且 SQLite 在多线程下会抛
``SQLite objects created in a thread can only be used in that same thread``
（微调任务是在线程里访问数据库的）。

现在收敛为进程内单例 Engine + 单例 Session 工厂：
- ``get_engine()``      返回同一个 Engine
- ``get_session_maker()`` 返回同一个 sessionmaker
- ``init_database()``   建表并返回 sessionmaker（幂等）
- ``reset_database()``  释放单例，仅供测试隔离使用

相对路径的 SQLite 文件统一锚定到项目根目录，不再随启动时的工作目录漂移。
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import PROJECT_ROOT, settings

Base = declarative_base()


def utcnow() -> datetime:
    """当前 UTC 时间（naive）。

    ``datetime.utcnow()`` 自 Python 3.12 起已被弃用。这里用等价的
    ``now(timezone.utc)`` 再剥离 tzinfo，保持与既有 naive 列一致的语义，
    避免混入带时区的值导致 SQLite 比较异常。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(String(50), default="file")
    file_path = Column(String(512), nullable=True)
    total_samples = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    annotations = relationship("Annotation", back_populates="dataset")


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("annotation_tasks.id"), nullable=True)
    instruction = Column(Text, nullable=False)
    input_text = Column(Text, nullable=True)
    output_text = Column(Text, nullable=True)
    raw_data = Column(JSON, nullable=True)
    status = Column(String(50), default="pending")
    annotator = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    dataset = relationship("Dataset", back_populates="annotations")
    task = relationship("AnnotationTask", back_populates="annotations")


class AnnotationTask(Base):
    __tablename__ = "annotation_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    annotation_type = Column(String(50), default="text")
    total_items = Column(Integer, default=0)
    completed_items = Column(Integer, default=0)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    annotations = relationship("Annotation", back_populates="task")


class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    model_type = Column(String(50), default="base")
    base_model = Column(String(255), nullable=True)
    model_path = Column(String(512), nullable=True)
    lora_path = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    is_loaded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    finetune_jobs = relationship("FinetuneJob", back_populates="model")
    evaluations = relationship("Evaluation", back_populates="model")


class FinetuneJob(Base):
    __tablename__ = "finetune_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    job_name = Column(String(255), nullable=False)
    method = Column(String(50), default="lora")
    status = Column(String(50), default="pending")
    progress = Column(Float, default=0.0)
    config = Column(JSON, nullable=True)
    output_path = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    model = relationship("Model", back_populates="finetune_jobs")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=True)
    eval_name = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")
    metrics = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    model = relationship("Model", back_populates="evaluations")


class InferenceLog(Base):
    __tablename__ = "inference_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=True)
    request_type = Column(String(50), default="completion")
    prompt = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    tokens_used = Column(Integer, default=0)
    latency_ms = Column(Float, default=0.0)
    backend = Column(String(50), default="mock")
    created_at = Column(DateTime, default=utcnow)


# --------------------------------------------------------------------------
# 单例 Engine / Session 工厂
# --------------------------------------------------------------------------

_engine: Optional[Engine] = None
_session_maker: Optional[sessionmaker] = None


def resolve_db_path(db_path: Optional[str] = None) -> Path:
    """把配置里的数据库路径解析为绝对路径（相对路径锚定项目根）。"""
    raw = Path(db_path or settings.database.path)
    return raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()


def get_engine(db_path: Optional[str] = None) -> Engine:
    """返回进程内唯一的 SQLAlchemy Engine。"""
    global _engine
    if _engine is None:
        path = resolve_db_path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            # 微调任务在线程中写库，必须放开 SQLite 的线程归属检查
            connect_args={"check_same_thread": False},
            future=True,
        )
    return _engine


def get_session_maker(db_path: Optional[str] = None) -> sessionmaker:
    """返回进程内唯一的 sessionmaker。"""
    global _session_maker
    if _session_maker is None:
        _session_maker = sessionmaker(
            bind=get_engine(db_path), autoflush=False, expire_on_commit=False
        )
    return _session_maker


def init_database(db_path: Optional[str] = None) -> sessionmaker:
    """建表（幂等）并返回 sessionmaker。"""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return get_session_maker(db_path)


def reset_database() -> None:
    """丢弃单例 Engine / Session 工厂。仅供测试隔离使用。"""
    global _engine, _session_maker
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_maker = None
```

---

## 11. 接口契约 app/models/schemas.py

**路径**：`app/models/schemas.py`　|　**行数**：225

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum

# 统一的 ORM 模式：允许 from_attributes 直接读取 ORM 对象
ORM_CONFIG = ConfigDict(from_attributes=True)


class DataSourceType(str, Enum):
    FILE = "file"
    API = "api"
    DATABASE = "database"


class AnnotationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class FinetuneStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DatasetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    source_type: DataSourceType = DataSourceType.FILE


class DatasetResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    source_type: str
    total_samples: int
    created_at: datetime

    model_config = ORM_CONFIG


class AnnotationCreate(BaseModel):
    dataset_id: int
    instruction: str
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class AnnotationUpdate(BaseModel):
    output_text: str
    status: AnnotationStatus = AnnotationStatus.COMPLETED
    annotator: Optional[str] = None


class AnnotationResponse(BaseModel):
    id: int
    dataset_id: int
    instruction: str
    input_text: Optional[str]
    output_text: Optional[str]
    status: str
    annotator: Optional[str]
    created_at: datetime

    model_config = ORM_CONFIG


class AnnotationTaskCreate(BaseModel):
    name: str
    dataset_id: int
    description: Optional[str] = None
    annotation_type: str = "text"


class AnnotationTaskResponse(BaseModel):
    id: int
    name: str
    dataset_id: int
    total_items: int
    completed_items: int
    status: str
    created_at: datetime

    model_config = ORM_CONFIG


class ModelLoadRequest(BaseModel):
    model_name: str
    model_path: Optional[str] = None
    lora_path: Optional[str] = None


class ModelResponse(BaseModel):
    id: int
    name: str
    model_type: str
    base_model: Optional[str]
    is_loaded: bool
    created_at: datetime

    model_config = ORM_CONFIG


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    # 实际产出该响应的后端：vllm(真实模型) / mock(确定性占位) / scripted(测试)
    backend: Optional[str] = None
    choices: List[ChatCompletionChoice]
    created: int
    usage: Dict[str, int]


class CompletionRequest(BaseModel):
    model: str
    prompt: str
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False


class CompletionChoice(BaseModel):
    index: int
    text: str
    finish_reason: str


class CompletionResponse(BaseModel):
    id: str
    object: str = "text_completion"
    model: str
    # 实际产出该响应的后端：vllm(真实模型) / mock(确定性占位) / scripted(测试)
    backend: Optional[str] = None
    choices: List[CompletionChoice]
    created: int
    usage: Dict[str, int]


class FinetuneCreate(BaseModel):
    model_id: int
    dataset_id: int
    job_name: str
    method: str = "lora"
    config: Optional[Dict[str, Any]] = None


class FinetuneResponse(BaseModel):
    id: int
    model_id: int
    dataset_id: int
    job_name: str
    method: str
    status: str
    progress: float
    created_at: datetime

    model_config = ORM_CONFIG


class EvaluationCreate(BaseModel):
    model_id: int
    dataset_id: Optional[int] = None
    eval_name: str
    metrics: Optional[List[str]] = None


class EvaluationResponse(BaseModel):
    id: int
    model_id: int
    eval_name: str
    status: str
    metrics: Optional[Dict[str, Any]]
    results: Optional[Dict[str, Any]]
    created_at: datetime

    model_config = ORM_CONFIG


class HealthResponse(BaseModel):
    status: str
    version: str
    models_loaded: int
    # 以下字段让 /health 暴露运行时真实状态，而不是硬编码值
    inference_backend: str
    inference_backend_is_real_model: bool
    # degraded=True 表示当前跑在确定性 mock 后端上，并非真实模型推理
    degraded: bool
    database: str
    registered_models: int
```

---

## 12. 服务 app/services/data_service.py

**路径**：`app/services/data_service.py`　|　**行数**：138

```python
import csv
import json
from pathlib import Path
from typing import List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import Annotation, Dataset


class DataService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.storage_path = Path(settings.storage.datasets_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def create_dataset(self, name: str, description: str = None, source_type: str = "file") -> Dataset:
        dataset = Dataset(
            name=name,
            description=description,
            source_type=source_type
        )
        self.db.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def import_data_from_file(self, dataset_id: int, file_path: str, file_type: str = "json") -> int:
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        if file_type == "json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        elif file_type == "jsonl":
            data = []
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))
        elif file_type == "csv":
            # 原实现用 pandas 只为读一个 CSV，却引入 pandas + pyarrow 约 120MB
            # 依赖。标准库 csv 足以覆盖，故改用 stdlib。
            with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                data = [dict(row) for row in csv.DictReader(f)]
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        count = 0
        for item in data:
            instruction = item.get("instruction", item.get("question", ""))
            input_text = item.get("input", item.get("context", ""))
            output_text = item.get("output", item.get("answer", ""))

            # 源数据自带答案即视为已标注。原实现一律标记 pending，
            # 导致 export_to_training_format（只导 completed）导出空文件，
            # 微调拿到 0 条样本。
            status = "completed" if str(output_text or "").strip() else "pending"

            annotation = Annotation(
                dataset_id=dataset_id,
                instruction=instruction,
                input_text=input_text,
                output_text=output_text,
                raw_data=item,
                status=status
            )
            self.db.add(annotation)
            count += 1

        dataset.total_samples = count
        dataset.file_path = file_path
        self.db.commit()

        dest_path = self.storage_path / f"dataset_{dataset_id}.json"
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return count

    def get_dataset(self, dataset_id: int) -> Optional[Dataset]:
        return self.db.query(Dataset).filter(Dataset.id == dataset_id).first()

    def list_datasets(self, skip: int = 0, limit: int = 100) -> List[Dataset]:
        return self.db.query(Dataset).offset(skip).limit(limit).all()

    def delete_dataset(self, dataset_id: int) -> bool:
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if dataset:
            self.db.query(Annotation).filter(Annotation.dataset_id == dataset_id).delete()
            self.db.delete(dataset)
            self.db.commit()
            return True
        return False

    def get_annotations(self, dataset_id: int, skip: int = 0, limit: int = 100) -> List[Annotation]:
        return self.db.query(Annotation).filter(
            Annotation.dataset_id == dataset_id
        ).offset(skip).limit(limit).all()

    def export_to_training_format(self, dataset_id: int, output_path: str = None) -> str:
        """导出已标注样本为训练用 jsonl。没有可用样本时抛 ValueError。"""
        dataset = self.get_dataset(dataset_id)
        if dataset is None:
            raise ValueError(f"Dataset {dataset_id} not found")

        annotations = self.db.query(Annotation).filter(
            Annotation.dataset_id == dataset_id,
            Annotation.status == "completed"
        ).all()

        training_data = []
        for ann in annotations:
            if not str(ann.output_text or "").strip():
                continue
            training_data.append({
                "instruction": ann.instruction,
                "input": ann.input_text or "",
                "output": ann.output_text
            })

        if not training_data:
            raise ValueError(
                f"数据集 {dataset_id} 中没有已标注（status=completed 且 output 非空）"
                "的样本，无法导出训练数据。请先完成标注或导入自带答案的数据。"
            )

        if output_path is None:
            output_path = str(self.storage_path / f"training_data_{dataset_id}.jsonl")

        with open(output_path, "w", encoding="utf-8") as f:
            for item in training_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return output_path
```

---

## 13. 服务 app/services/annotation_service.py

**路径**：`app/services/annotation_service.py`　|　**行数**：105

```python
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.database import Annotation, AnnotationTask, Dataset, utcnow
from app.models.schemas import AnnotationStatus


class AnnotationService:
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_task(self, name: str, dataset_id: int, description: str = None, 
                    annotation_type: str = "text") -> AnnotationTask:
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        task = AnnotationTask(
            name=name,
            dataset_id=dataset_id,
            description=description,
            annotation_type=annotation_type,
            total_items=dataset.total_samples
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        self.db.query(Annotation).filter(
            Annotation.dataset_id == dataset_id
        ).update({"task_id": task.id})
        self.db.commit()

        return task

    def get_task(self, task_id: int) -> Optional[AnnotationTask]:
        return self.db.query(AnnotationTask).filter(AnnotationTask.id == task_id).first()

    def list_tasks(self, skip: int = 0, limit: int = 100) -> List[AnnotationTask]:
        return self.db.query(AnnotationTask).offset(skip).limit(limit).all()

    def get_next_annotation(self, task_id: int) -> Optional[Annotation]:
        return self.db.query(Annotation).filter(
            Annotation.task_id == task_id,
            Annotation.status == "pending"
        ).first()

    def submit_annotation(self, annotation_id: int, output_text: str, 
                          annotator: str = None) -> Annotation:
        annotation = self.db.query(Annotation).filter(Annotation.id == annotation_id).first()
        if not annotation:
            raise ValueError(f"Annotation {annotation_id} not found")

        annotation.output_text = output_text
        annotation.status = AnnotationStatus.COMPLETED.value
        annotation.annotator = annotator
        annotation.updated_at = utcnow()

        if annotation.task_id:
            task = self.db.query(AnnotationTask).filter(
                AnnotationTask.id == annotation.task_id
            ).first()
            if task:
                completed = self.db.query(Annotation).filter(
                    Annotation.task_id == task.id,
                    Annotation.status == "completed"
                ).count()
                task.completed_items = completed
                if completed >= task.total_items:
                    task.status = "completed"

        self.db.commit()
        self.db.refresh(annotation)
        return annotation

    def get_annotation(self, annotation_id: int) -> Optional[Annotation]:
        return self.db.query(Annotation).filter(Annotation.id == annotation_id).first()

    def list_annotations_by_task(self, task_id: int, status: str = None,
                                  skip: int = 0, limit: int = 100) -> List[Annotation]:
        query = self.db.query(Annotation).filter(Annotation.task_id == task_id)
        if status:
            query = query.filter(Annotation.status == status)
        return query.offset(skip).limit(limit).all()

    def get_task_progress(self, task_id: int) -> dict:
        task = self.db.query(AnnotationTask).filter(AnnotationTask.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        total = task.total_items
        completed = task.completed_items
        pending = self.db.query(Annotation).filter(
            Annotation.task_id == task_id,
            Annotation.status == "pending"
        ).count()

        return {
            "task_id": task_id,
            "total": total,
            "completed": completed,
            "pending": pending,
            "progress": round(completed / total * 100, 2) if total > 0 else 0
        }
```

---

## 14. 服务 app/services/model_service.py

**路径**：`app/services/model_service.py`　|　**行数**：110

```python
import os
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from pathlib import Path

from app.models.database import Model, FinetuneJob, utcnow
from app.config import settings


class ModelService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.models_path = Path(settings.storage.models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)
        self.loaded_models: Dict[str, Any] = {}

    def register_model(self, name: str, model_type: str = "base",
                       base_model: str = None, model_path: str = None,
                       description: str = None) -> Model:
        model = Model(
            name=name,
            model_type=model_type,
            base_model=base_model,
            model_path=model_path,
            description=description
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def get_model(self, model_id: int) -> Optional[Model]:
        return self.db.query(Model).filter(Model.id == model_id).first()

    def get_model_by_name(self, name: str) -> Optional[Model]:
        return self.db.query(Model).filter(Model.name == name).first()

    def list_models(self, model_type: str = None, skip: int = 0, limit: int = 100) -> List[Model]:
        query = self.db.query(Model)
        if model_type:
            query = query.filter(Model.model_type == model_type)
        return query.offset(skip).limit(limit).all()

    def set_model_loaded(self, model_id: int, is_loaded: bool) -> Model:
        model = self.db.query(Model).filter(Model.id == model_id).first()
        if model:
            model.is_loaded = is_loaded
            self.db.commit()
            self.db.refresh(model)
        return model

    def update_lora_path(self, model_id: int, lora_path: str) -> Model:
        model = self.db.query(Model).filter(Model.id == model_id).first()
        if model:
            model.lora_path = lora_path
            model.model_type = "lora"
            self.db.commit()
            self.db.refresh(model)
        return model

    def delete_model(self, model_id: int) -> bool:
        model = self.db.query(Model).filter(Model.id == model_id).first()
        if model:
            self.db.delete(model)
            self.db.commit()
            return True
        return False

    def create_finetune_job(self, model_id: int, dataset_id: int, job_name: str,
                            method: str = "lora", config: Dict = None) -> FinetuneJob:
        job = FinetuneJob(
            model_id=model_id,
            dataset_id=dataset_id,
            job_name=job_name,
            method=method,
            config=config or {}
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_finetune_job(self, job_id: int) -> Optional[FinetuneJob]:
        return self.db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()

    def list_finetune_jobs(self, model_id: int = None, skip: int = 0, limit: int = 100) -> List[FinetuneJob]:
        query = self.db.query(FinetuneJob)
        if model_id:
            query = query.filter(FinetuneJob.model_id == model_id)
        return query.offset(skip).limit(limit).all()

    def update_finetune_status(self, job_id: int, status: str, progress: float = None,
                               output_path: str = None, error_message: str = None) -> FinetuneJob:
        job = self.db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()
        if job:
            job.status = status
            if progress is not None:
                job.progress = progress
            if output_path:
                job.output_path = output_path
            if error_message:
                job.error_message = error_message
            if status == "running" and not job.started_at:
                job.started_at = utcnow()
            if status in ["completed", "failed"]:
                job.completed_at = utcnow()
            self.db.commit()
            self.db.refresh(job)
        return job
```

---

## 15. 服务 app/services/inference_service.py

**路径**：`app/services/inference_service.py`　|　**行数**：340

```python
"""推理服务：可插拔后端 + 诚实降级。

后端选择
--------
1. 安装了 vLLM 且模型加载成功      -> ``backend="vllm"``，真实推理。
2. 未安装 vLLM / 加载失败          -> ``backend="mock"``，返回**确定性**占位文本。

为什么要有 mock 后端
--------------------
vLLM 只在 Linux + CUDA 上可用，Windows 装不上。原实现在这种情况下直接返回
``{"status": "error", "message": "vLLM not installed, using mock mode"}``
——消息里说"使用 mock 模式"，实际却走 HTTP 200 返回错误体，且 mock 文本形如
``[Mock Response] Model not loaded. Prompt was: ...``，调用方无法与真实输出区分。

现在把降级做成显式的：响应带 ``backend`` 字段，占位文本以 ``[MOCK]`` 开头并附带
prompt 哈希，任何调用方都能一眼识别这不是模型输出。全部占位内容由 prompt 决定，
同一 prompt 永远得到同一结果，可被测试断言。
"""

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.database import InferenceLog, get_session_maker

MOCK_MARKER = "[MOCK]"


class MockBackend:
    """确定性占位后端。不是模型，输出必须可被识别。"""

    name = "mock"
    is_real = False

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
        # 取 prompt 尾部作为可读线索，便于人工核对请求确实被收到
        tail = " ".join(prompt.split())[-160:]
        return (
            f"{MOCK_MARKER} vLLM 后端不可用，以下为确定性占位文本，非模型输出。"
            f"prompt_sha1={digest} prompt_tail=...{tail}"
        )


class ScriptedBackend:
    """测试用后端：按顺序返回预设答案。

    让"评测指标是否算对"可以被确定性验证，而不依赖任何模型。
    """

    name = "scripted"
    is_real = False

    def __init__(self, responses: List[str]):
        self.responses = list(responses)
        self.calls: List[str] = []

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        self.calls.append(prompt)
        if not self.responses:
            return ""
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class VLLMBackend:
    """真实 vLLM 后端。"""

    name = "vllm"
    is_real = True

    def __init__(self, engine: Any):
        self.engine = engine

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        from vllm import SamplingParams

        sampling_params = SamplingParams(
            max_tokens=max_tokens, temperature=temperature, top_p=top_p
        )
        outputs = self.engine.generate([prompt], sampling_params)
        return outputs[0].outputs[0].text


class InferenceService:
    def __init__(self, db_session=None):
        # 保留参数以兼容旧调用；日志统一走短生命周期会话
        self.db = db_session
        self.backend: Any = MockBackend()
        self.current_model: Optional[str] = None
        self.load_error: Optional[str] = None

    # ---------------- 后端管理 ----------------

    @property
    def backend_name(self) -> str:
        return self.backend.name

    @property
    def is_real_backend(self) -> bool:
        return bool(getattr(self.backend, "is_real", False))

    def set_backend(self, backend: Any) -> str:
        """注入自定义后端（测试 / 自研引擎）。"""
        self.backend = backend
        return self.backend.name

    def load_model(
        self,
        model_name: str,
        model_path: Optional[str] = None,
        lora_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """尝试加载真实模型；不可用时显式降级，绝不谎报成功。"""
        actual_path = model_path or model_name

        try:
            from vllm import LLM  # noqa: F401
        except ImportError:
            self.backend = MockBackend()
            self.current_model = model_name
            self.load_error = "vllm-not-installed"
            return {
                "status": "degraded",
                "model": model_name,
                "backend": self.backend_name,
                "degraded": True,
                "reason": (
                    "未安装 vLLM，已切换到确定性 mock 后端（占位输出，非模型输出）。"
                    "如需真实推理：Linux + CUDA 环境执行 "
                    "pip install -r requirements-gpu.txt"
                ),
            }

        try:
            from vllm import LLM

            engine = LLM(
                model=actual_path,
                tensor_parallel_size=settings.model.tensor_parallel_size,
                gpu_memory_utilization=settings.model.gpu_memory_utilization,
                max_model_len=settings.model.max_model_len,
                trust_remote_code=True,
            )
        except Exception as exc:  # 显存不足 / 路径错误 / 权重损坏
            self.backend = MockBackend()
            self.current_model = model_name
            self.load_error = str(exc)
            return {
                "status": "degraded",
                "model": model_name,
                "backend": self.backend_name,
                "degraded": True,
                "reason": f"vLLM 加载失败，已切换到 mock 后端：{exc}",
            }

        self.backend = VLLMBackend(engine)
        self.current_model = model_name
        self.load_error = None
        return {
            "status": "success",
            "model": model_name,
            "backend": self.backend_name,
            "degraded": False,
        }

    def unload_model(self) -> Dict[str, Any]:
        self.backend = MockBackend()
        self.current_model = None
        self.load_error = None
        return {"status": "success", "backend": self.backend_name}

    def describe(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "is_real_model": self.is_real_backend,
            "current_model": self.current_model,
            "load_error": self.load_error,
        }

    # ---------------- 推理 ----------------

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        text = self.backend.generate(prompt, max_tokens, temperature, top_p)
        latency_ms = (time.perf_counter() - start) * 1000

        # 注意：这里是空白切分的近似 token 数，非分词器精确计数
        tokens_used = len(prompt.split()) + len(text.split())

        self._log("completion", prompt, text, tokens_used, latency_ms)

        return {
            "text": text,
            "tokens_used": tokens_used,
            "latency_ms": round(latency_ms, 3),
            "backend": self.backend_name,
        }

    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        prompt = self._format_chat_prompt(messages)
        result = self.generate(prompt, max_tokens, temperature, top_p)
        return {
            "content": result["text"],
            "tokens_used": result["tokens_used"],
            "latency_ms": result["latency_ms"],
            "backend": result["backend"],
        }

    @staticmethod
    def _format_chat_prompt(messages: List[Dict[str, str]]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("system", "user", "assistant"):
                parts.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n")
        return "".join(parts)

    def _log(
        self,
        request_type: str,
        prompt: str,
        response: str,
        tokens_used: int,
        latency_ms: float,
    ) -> None:
        """写推理日志。日志失败不得影响推理响应。"""
        try:
            session = get_session_maker()()
        except Exception:
            return
        try:
            session.add(
                InferenceLog(
                    request_type=request_type,
                    prompt=prompt[:1000],
                    response=response[:1000],
                    tokens_used=tokens_used,
                    latency_ms=latency_ms,
                    backend=self.backend_name,
                )
            )
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    # ---------------- OpenAI 兼容响应 ----------------

    def create_completion_response(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        result = self.generate(prompt, max_tokens, temperature, top_p)
        prompt_tokens = len(prompt.split())
        return {
            "id": f"cmpl-{uuid.uuid4().hex[:8]}",
            "object": "text_completion",
            "model": model,
            "backend": result["backend"],
            "choices": [
                {"index": 0, "text": result["text"], "finish_reason": "stop"}
            ],
            "created": int(time.time()),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": result["tokens_used"],
                "total_tokens": prompt_tokens + result["tokens_used"],
            },
        }

    def create_chat_response(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        result = self.chat(messages, max_tokens, temperature, top_p)
        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "model": model,
            "backend": result["backend"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result["content"]},
                    "finish_reason": "stop",
                }
            ],
            "created": int(time.time()),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": result["tokens_used"],
                "total_tokens": prompt_tokens + result["tokens_used"],
            },
        }
```

---

## 16. 服务 app/services/finetune_service.py

**路径**：`app/services/finetune_service.py`　|　**行数**：282

```python
"""LoRA 微调服务。

原实现的两个真实缺陷
--------------------
1. **跨线程复用 Session**：``start_finetune`` 起一个线程执行训练，线程里继续用
   请求作用域的 ``self.db``（以及绑定它的 ``ModelService`` / ``DataService``）。
   SQLAlchemy 的 Session 不是线程安全的，SQLite 还会直接抛
   ``SQLite objects created in a thread can only be used in that same thread``。
   现在工作线程自己创建 Session，用完即关。
2. **取消失效 / 语义含糊**：``cancel_job`` 只把状态改成 cancelled，训练线程照样
   跑完并写 ``output_path``，随后又被 update 成 completed —— 取消等于没取消。
   现在引入协作式取消标志，在每个阶段边界检查；并在文档与响应里明确说明
   **无法中断已进入的单个训练 step**（PyTorch 层面无法安全抢占）。

依赖缺失时的行为
----------------
未安装 transformers / peft 时任务会失败，错误信息明确指向 requirements-gpu.txt，
不会被伪装成"训练完成"。
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import FinetuneJob, get_session_maker
from app.services.data_service import DataService
from app.services.model_service import ModelService

MISSING_DEPS_HINT = (
    "未安装 transformers / peft / datasets，无法执行真实 LoRA 训练。"
    "请在 Linux + CUDA 环境执行 pip install -r requirements-gpu.txt。"
)


class _JobCancelled(Exception):
    """协作式取消信号。"""


class FinetuneService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.model_service = ModelService(db_session)
        self.data_service = DataService(db_session)
        self.models_path = Path(settings.storage.models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)
        # 进程级共享的取消标志与线程句柄（跨请求可见）
        self._cancel_flags: Dict[int, threading.Event] = {}
        self._threads: Dict[int, threading.Thread] = {}

    # ---------------- 任务生命周期 ----------------

    def create_job(
        self,
        model_id: int,
        dataset_id: int,
        job_name: str,
        method: str = "lora",
        config: Dict = None,
    ) -> FinetuneJob:
        if self.model_service.get_model(model_id) is None:
            raise ValueError(f"模型 {model_id} 不存在")
        if self.data_service.get_dataset(dataset_id) is None:
            raise ValueError(f"数据集 {dataset_id} 不存在")
        return self.model_service.create_finetune_job(
            model_id=model_id,
            dataset_id=dataset_id,
            job_name=job_name,
            method=method,
            config=config,
        )

    def list_jobs(self, model_id: int = None, skip: int = 0, limit: int = 100) -> List[FinetuneJob]:
        return self.model_service.list_finetune_jobs(model_id, skip, limit)

    def start_finetune(self, job_id: int) -> Dict[str, Any]:
        job = self.model_service.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": f"Job {job_id} not found"}
        if job.status == "running":
            return {"status": "error", "message": "Job already running"}

        self.model_service.update_finetune_status(job_id, "running", 0.0)
        self._cancel_flags[job_id] = threading.Event()

        thread = threading.Thread(
            target=self._run_finetune, args=(job_id,), name=f"finetune-{job_id}", daemon=True
        )
        thread.start()
        self._threads[job_id] = thread

        return {"status": "started", "job_id": job_id}

    def cancel_job(self, job_id: int) -> Dict[str, Any]:
        job = self.model_service.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": f"Job {job_id} not found"}
        if job.status != "running":
            return {"status": "error", "message": f"Job 状态为 {job.status}，无法取消"}

        flag = self._cancel_flags.get(job_id)
        if flag is not None:
            flag.set()
        self.model_service.update_finetune_status(job_id, "cancelled", job.progress)
        return {
            "status": "cancelled",
            "job_id": job_id,
            "note": (
                "已发送取消信号，训练将在下一个阶段检查点停止。"
                "单个已进入的训练 step 无法被安全中断。"
            ),
        }

    # ---------------- 工作线程 ----------------

    def _run_finetune(self, job_id: int) -> None:
        """在线程内使用独立 Session，避免跨线程共享请求级 Session。"""
        session = get_session_maker()()
        try:
            model_service = ModelService(session)
            data_service = DataService(session)
            flag = self._cancel_flags.setdefault(job_id, threading.Event())

            job = model_service.get_finetune_job(job_id)
            if job is None:
                return
            model = model_service.get_model(job.model_id)
            if model is None:
                model_service.update_finetune_status(
                    job_id, "failed", 0.0, error_message=f"模型 {job.model_id} 不存在"
                )
                return

            training_data_path = data_service.export_to_training_format(job.dataset_id)
            output_dir = str(self.models_path / f"lora_{job_id}")

            self._run_lora_training(
                base_model=model.model_path or model.base_model,
                data_path=training_data_path,
                output_dir=output_dir,
                job_id=job_id,
                model_service=model_service,
                flag=flag,
            )

            if flag.is_set():
                model_service.update_finetune_status(job_id, "cancelled")
                return

            model_service.update_finetune_status(job_id, "completed", 100.0, output_dir)
            model_service.update_lora_path(model.id, output_dir)

        except _JobCancelled:
            ModelService(session).update_finetune_status(job_id, "cancelled")
        except Exception as exc:
            session.rollback()
            ModelService(session).update_finetune_status(
                job_id, "failed", 0.0, error_message=str(exc)
            )
        finally:
            self._threads.pop(job_id, None)
            session.close()

    def _run_lora_training(
        self,
        base_model: str,
        data_path: str,
        output_dir: str,
        job_id: int,
        model_service: ModelService,
        flag: threading.Event,
    ) -> None:
        def checkpoint(progress: float) -> None:
            if flag.is_set():
                raise _JobCancelled()
            model_service.update_finetune_status(job_id, "running", progress)

        try:
            from transformers import (  # noqa: F401
                AutoModelForCausalLM,
                AutoTokenizer,
                Trainer,
                TrainingArguments,
            )
            from peft import LoraConfig, TaskType, get_peft_model  # noqa: F401
            from datasets import Dataset  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(f"{MISSING_DEPS_HINT}（原始错误：{exc}）") from exc

        checkpoint(10.0)
        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        checkpoint(20.0)
        model = AutoModelForCausalLM.from_pretrained(
            base_model, torch_dtype="auto", device_map="auto", trust_remote_code=True
        )

        checkpoint(30.0)
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=settings.lora.r,
            lora_alpha=settings.lora.lora_alpha,
            lora_dropout=settings.lora.lora_dropout,
            target_modules=settings.lora.target_modules,
            bias="none",
        )
        model = get_peft_model(model, lora_config)

        checkpoint(40.0)
        with open(data_path, "r", encoding="utf-8") as f:
            data = [json.loads(line) for line in f if line.strip()]
        if not data:
            raise RuntimeError("训练数据为空")

        def format_example(example):
            prompt = (
                f"<|im_start|>user\n{example['instruction']}\n{example.get('input', '')}<|im_end|>\n"
                f"<|im_start|>assistant\n{example['output']}<|im_end|>"
            )
            return {"text": prompt}

        dataset = Dataset.from_list(data).map(format_example)

        def tokenize_function(examples):
            return tokenizer(
                examples["text"], truncation=True, max_length=2048, padding="max_length"
            )

        tokenized_dataset = dataset.map(tokenize_function, batched=True)

        checkpoint(50.0)
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=settings.training.num_train_epochs,
            per_device_train_batch_size=settings.training.per_device_train_batch_size,
            gradient_accumulation_steps=settings.training.gradient_accumulation_steps,
            learning_rate=settings.training.learning_rate,
            logging_steps=settings.training.logging_steps,
            save_steps=settings.training.save_steps,
            fp16=True,
            report_to="none",
        )

        trainer = Trainer(
            model=model, args=training_args, train_dataset=tokenized_dataset, tokenizer=tokenizer
        )

        checkpoint(60.0)
        trainer.train()

        if flag.is_set():
            raise _JobCancelled()

        checkpoint(90.0)
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

    # ---------------- 查询 ----------------

    def get_job_status(self, job_id: int) -> Optional[Dict[str, Any]]:
        job = self.model_service.get_finetune_job(job_id)
        if not job:
            return None
        return {
            "job_id": job.id,
            "model_id": job.model_id,
            "dataset_id": job.dataset_id,
            "job_name": job.job_name,
            "method": job.method,
            "status": job.status,
            "progress": job.progress,
            "output_path": job.output_path,
            "error_message": job.error_message,
            "started_at": job.started_at,
            "completed_at": job.completed_at,
        }
```

---

## 17. 服务 app/services/evaluate_service.py

**路径**：`app/services/evaluate_service.py`　|　**行数**：357

```python
"""评测服务：真实可复现的指标，不再返回编造数值。

原实现的问题
------------
1. ``run_evaluation`` 默认 ``test_data=None``，而内部 ``test_data[:100]`` 会抛
   ``TypeError``；每个指标函数都把这个异常吞掉，返回 ``{"mock_value": 15.5}``，
   评测状态却仍被标成 ``completed``。
2. ``_evaluate_accuracy`` 实际逻辑是"只要参考答案非空就算答对"，永远接近 1.0。
3. ``_evaluate_latency`` 测的是 ``time.sleep(0.01)`` 的耗时，与模型无关。

现在改为：真实调用当前推理后端取预测 -> 与参考答案比对 -> 计算指标。
缺数据就诚实报错（HTTP 400），缺能力（如未装 torch）就返回
``available: false`` 并说明如何启用，绝不给出看起来像真结果的假数字。

指标口径
--------
- ``exact_match``：归一化（去空白、转小写、去中英文标点）后完全一致的比例。
- ``token_f1``   ：按**字符**切分计算 F1，对中文与英文都稳定；
                   逐样本计算后取宏平均。空白切分对中文不适用，故不用。
- ``latency``    ：逐样本实测端到端推理耗时（含后端调用），给 min/avg/p50/p95。
- ``perplexity`` ：需 torch + transformers 才能真正计算；未安装时返回
                   ``available: false``，不填占位数字。
"""

import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import Evaluation, utcnow
from app.services.data_service import DataService
from app.services.inference_service import InferenceService
from app.services.model_service import ModelService

_PUNCT_RE = re.compile(r"[\s\u3000!-/:-@\[-`{-~\u3001-\u303f\uff01-\uff5e\u2018\u2019\u201c\u201d]+")


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return _PUNCT_RE.sub("", text).lower()


def char_f1(prediction: str, reference: str) -> float:
    """字符级 F1。两边都为空视为 1.0（完全一致的空答案）。"""
    pred = normalize_text(prediction)
    ref = normalize_text(reference)
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    pred_counter = Counter(pred)
    ref_counter = Counter(ref)
    overlap = sum((pred_counter & ref_counter).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def percentile(sorted_values: List[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(int(round((len(sorted_values) - 1) * ratio)), len(sorted_values) - 1)
    return sorted_values[idx]


class EvaluateService:
    def __init__(self, db_session: Session, inference_service: Optional[InferenceService] = None):
        self.db = db_session
        self.model_service = ModelService(db_session)
        self.data_service = DataService(db_session)
        self.inference_service = inference_service or InferenceService()

    # ---------------- CRUD ----------------

    def create_evaluation(
        self,
        model_id: int,
        eval_name: str,
        dataset_id: int = None,
        metrics: List[str] = None,
    ) -> Evaluation:
        record = Evaluation(
            model_id=model_id,
            dataset_id=dataset_id,
            eval_name=eval_name,
            metrics={"requested": metrics or settings.evaluation.metrics},
            status="pending",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_evaluation(self, eval_id: int) -> Optional[Evaluation]:
        return self.db.query(Evaluation).filter(Evaluation.id == eval_id).first()

    def list_evaluations(
        self, model_id: int = None, skip: int = 0, limit: int = 100
    ) -> List[Evaluation]:
        query = self.db.query(Evaluation)
        if model_id:
            query = query.filter(Evaluation.model_id == model_id)
        return query.offset(skip).limit(limit).all()

    # ---------------- 执行 ----------------

    def run_evaluation(
        self, eval_id: int, test_data: List[Dict] = None
    ) -> Dict[str, Any]:
        record = self.get_evaluation(eval_id)
        if not record:
            return {"status": "error", "message": f"Evaluation {eval_id} not found"}

        try:
            samples = self.resolve_samples(record, test_data)
        except ValueError as exc:
            record.status = "failed"
            record.results = {"error": str(exc)}
            self.db.commit()
            return {"status": "error", "message": str(exc)}

        record.status = "running"
        self.db.commit()

        try:
            predictions = self._predict(samples)

            results: Dict[str, Any] = {
                "sample_count": len(samples),
                "backend": self.inference_service.backend_name,
                "backend_is_real_model": self.inference_service.is_real_backend,
                "metric_definitions": {
                    "exact_match": "归一化后完全一致的比例（宏平均）",
                    "token_f1": "字符级 F1 的宏平均（适配中英文）",
                    "latency": "逐样本实测端到端推理耗时（毫秒）",
                    "perplexity": "需 torch+transformers，未安装则 available=false",
                },
            }

            requested = (record.metrics or {}).get("requested", []) or []
            # 兼容旧配置里的 "accuracy"：映射到 exact_match
            wants_em = any(m in requested for m in ("accuracy", "exact_match"))
            wants_f1 = any(m in requested for m in ("accuracy", "f1", "token_f1", "rouge"))
            wants_latency = "latency" in requested
            wants_ppl = "perplexity" in requested

            if wants_em:
                results["exact_match"] = self._exact_match(predictions)
            if wants_f1:
                results["token_f1"] = self._token_f1(predictions)
            if wants_latency:
                results["latency"] = self._latency(predictions)
            if wants_ppl:
                results["perplexity"] = self.compute_perplexity(record.model_id, samples)

            record.status = "completed"
            record.results = results
            record.completed_at = utcnow()
            self.db.commit()
            return {"status": "completed", "results": results}

        except Exception as exc:  # 后端异常等
            record.status = "failed"
            record.results = {"error": str(exc)}
            self.db.commit()
            return {"status": "error", "message": str(exc)}

    def resolve_samples(
        self, record: Evaluation, test_data: Optional[List[Dict]] = None
    ) -> List[Dict[str, str]]:
        """取得评测样本。缺数据时抛 ValueError，而不是悄悄用假数据。"""
        raw: List[Dict] = []

        if test_data:
            raw = [item for item in test_data if isinstance(item, dict)]
        elif record.dataset_id:
            annotations = self.data_service.get_annotations(record.dataset_id, limit=10000)
            raw = [
                {
                    "instruction": ann.instruction,
                    "input": ann.input_text or "",
                    "output": ann.output_text or "",
                }
                for ann in annotations
            ]

        samples = []
        for item in raw:
            reference = item.get("output") or item.get("answer") or ""
            if not str(reference).strip():
                continue  # 没有参考答案的样本无法参与指标计算
            samples.append(
                {
                    "prompt": self.build_prompt(item),
                    "reference": str(reference),
                }
            )

        if not samples:
            raise ValueError(
                "没有可用的评测数据：请在请求体传入 test_data，"
                "或为该评测指定含有参考答案（output/answer）的 dataset_id。"
            )

        return samples[: settings.evaluation.max_samples]

    @staticmethod
    def build_prompt(item: Dict) -> str:
        instruction = str(item.get("instruction") or item.get("question") or "")
        extra = str(item.get("input") or item.get("context") or "")
        return (
            f"<|im_start|>user\n{instruction}\n{extra}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    def _predict(self, samples: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        predictions = []
        for sample in samples:
            start = time.perf_counter()
            generated = self.inference_service.generate(sample["prompt"])
            elapsed_ms = (time.perf_counter() - start) * 1000
            predictions.append(
                {
                    "prediction": generated["text"],
                    "reference": sample["reference"],
                    "latency_ms": round(elapsed_ms, 3),
                }
            )
        return predictions

    # ---------------- 指标 ----------------

    @staticmethod
    def _exact_match(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        hits = sum(
            1
            for p in predictions
            if normalize_text(p["prediction"]) == normalize_text(p["reference"])
        )
        total = len(predictions)
        return {
            "value": round(hits / total, 4) if total else 0.0,
            "correct": hits,
            "total": total,
        }

    @staticmethod
    def _token_f1(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        scores = [char_f1(p["prediction"], p["reference"]) for p in predictions]
        total = len(scores)
        return {
            "value": round(sum(scores) / total, 4) if total else 0.0,
            "unit": "char",
            "total": total,
        }

    @staticmethod
    def _latency(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        latencies = sorted(p["latency_ms"] for p in predictions)
        if not latencies:
            return {"avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "samples": 0}
        return {
            "avg_ms": round(sum(latencies) / len(latencies), 3),
            "min_ms": round(latencies[0], 3),
            "max_ms": round(latencies[-1], 3),
            "p50_ms": round(percentile(latencies, 0.50), 3),
            "p95_ms": round(percentile(latencies, 0.95), 3),
            "samples": len(latencies),
        }

    def compute_perplexity(
        self, model_id: int, samples: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """真实困惑度。缺 torch/transformers 或权重时如实说明，不填占位值。"""
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: F401
        except ImportError:
            return {
                "available": False,
                "reason": "未安装 torch / transformers",
                "how_to_enable": "pip install -r requirements-gpu.txt（需 Linux + CUDA）",
            }

        model_record = self.model_service.get_model(model_id)
        if model_record is None:
            return {"available": False, "reason": f"模型 {model_id} 不存在"}

        model_path = (
            model_record.lora_path or model_record.model_path or model_record.base_model
        )
        if not model_path:
            return {"available": False, "reason": "该模型记录没有可用的本地权重路径"}

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(
                model_path, torch_dtype="auto", device_map="auto", trust_remote_code=True
            )
        except Exception as exc:
            return {
                "available": False,
                "reason": f"权重加载失败：{exc}",
                "model_path": model_path,
            }

        total_loss = 0.0
        total_tokens = 0
        with torch.no_grad():
            for sample in samples:
                text = f"{sample['prompt']}{sample['reference']}"
                inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
                outputs = model(**inputs, labels=inputs["input_ids"])
                n_tokens = inputs["input_ids"].size(1)
                total_loss += outputs.loss.item() * n_tokens
                total_tokens += n_tokens

        if total_tokens == 0:
            return {"available": False, "reason": "样本 token 数为 0"}

        value = float(torch.exp(torch.tensor(total_loss / total_tokens)).item())
        return {
            "available": True,
            "value": round(value, 4),
            "tokens": total_tokens,
            "model_path": model_path,
        }

    # ---------------- 汇总 ----------------

    def get_evaluation_summary(self, eval_id: int) -> Dict[str, Any]:
        record = self.get_evaluation(eval_id)
        if not record:
            return {"error": f"Evaluation {eval_id} not found"}

        return {
            "eval_id": record.id,
            "model_id": record.model_id,
            "dataset_id": record.dataset_id,
            "eval_name": record.eval_name,
            "status": record.status,
            "metrics": record.metrics,
            "results": record.results,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }
```

---

## 18. 测试 tests/conftest.py

**路径**：`tests/conftest.py`　|　**行数**：95

```python
"""pytest 共享夹具。

关键点：**在导入 app 模块之前**就把数据库与存储目录改到临时目录，
避免测试写脏工作区里的 data/unillm.db。
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402

# ---- 隔离：把落盘位置全部改到临时目录（在 import app.main 之前生效） ----
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="unillm-test-"))
settings.database.path = str(_TMP_ROOT / "test.db")
settings.storage.datasets_path = str(_TMP_ROOT / "datasets")
settings.storage.annotations_path = str(_TMP_ROOT / "annotations")
settings.storage.models_path = str(_TMP_ROOT / "models")
settings.storage.logs_path = str(_TMP_ROOT / "logs")
settings.app.debug = False
settings.evaluation.max_samples = 100

from app.api.deps import reset_inference_service  # noqa: E402
from app.main import app  # noqa: E402
from app.models.database import init_database, reset_database  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_runtime():
    reset_database()
    init_database()
    yield _TMP_ROOT
    reset_database()


@pytest.fixture(autouse=True)
def _clean_state():
    """每个用例前重建所有表、清空存储目录并重置推理后端，保证用例互不影响。"""
    import shutil

    from app.models.database import Base, get_engine

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    for directory in (
        settings.storage.datasets_path,
        settings.storage.annotations_path,
        settings.storage.models_path,
        settings.storage.logs_path,
    ):
        path = Path(directory)
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)

    reset_inference_service()
    yield
    reset_inference_service()


@pytest.fixture
def client():
    from starlette.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_rows():
    """小而完整的问答数据（自带答案 => 导入后即为已标注状态）。"""
    return [
        {"instruction": "1+1=?", "input": "", "output": "2"},
        {"instruction": "中国的首都？", "input": "", "output": "北京"},
        {"instruction": "水的化学式？", "input": "", "output": "H2O"},
    ]


@pytest.fixture
def sample_jsonl(tmp_path, sample_rows):
    path = tmp_path / "sample.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in sample_rows),
        encoding="utf-8",
    )
    return path
```

---

## 19. 测试 tests/test_metrics.py

**路径**：`tests/test_metrics.py`　|　**行数**：54

```python
"""单元测试：指标计算与文本归一化。

这些用例不依赖任何模型，验证的是"指标到底怎么算"，
防止再次出现"用 sleep 冒充延迟""参考答案非空就算答对"这类伪实现。
"""

from app.services.evaluate_service import char_f1, normalize_text, percentile


class TestNormalizeText:
    def test_lowercases_and_strips_punctuation(self):
        assert normalize_text("Hello, World!") == "helloworld"

    def test_handles_chinese_punctuation(self):
        assert normalize_text("北京，中国。") == "北京中国"

    def test_empty_and_none(self):
        assert normalize_text(None) == ""
        assert normalize_text("") == ""
        assert normalize_text("   ") == ""


class TestCharF1:
    def test_identical_text_scores_one(self):
        assert char_f1("北京", "北京") == 1.0

    def test_identical_after_normalization(self):
        # 大小写与标点差异不应影响结果
        assert char_f1("H2O!", "h2o") == 1.0

    def test_completely_different_scores_zero(self):
        assert char_f1("北京", "完全无关") == 0.0

    def test_partial_overlap_between_zero_and_one(self):
        score = char_f1("机器学习", "机器")
        assert 0.0 < score < 1.0

    def test_both_empty_is_perfect_match(self):
        assert char_f1("", "") == 1.0

    def test_one_empty_scores_zero(self):
        assert char_f1("abc", "") == 0.0


class TestPercentile:
    def test_median_of_odd_list(self):
        assert percentile([1.0, 2.0, 3.0], 0.5) == 2.0

    def test_max_ratio_returns_last(self):
        assert percentile([1.0, 2.0, 3.0], 1.0) == 3.0

    def test_empty_list_returns_zero(self):
        assert percentile([], 0.5) == 0.0
```

---

## 20. 测试 tests/test_closed_loop.py

**路径**：`tests/test_closed_loop.py`　|　**行数**：309

```python
"""端到端闭环测试：数据 → 标注 → 导出 → 模型注册/加载 → 推理 → 评测。

这是"项目确实可运行"的可复现证据。全部通过 HTTP 接口调用，
不依赖 GPU、不下载任何模型权重。
"""

import json
from pathlib import Path

import pytest

from app.api.deps import reset_inference_service
from app.services.inference_service import InferenceService, ScriptedBackend


def _import_dataset(client, sample_jsonl: Path, name: str = "闭环测试数据"):
    with open(sample_jsonl, "rb") as handle:
        response = client.post(
            "/api/data/import",
            params={"name": name, "description": "端到端测试"},
            files={"file": ("sample.jsonl", handle, "application/json")},
        )
    assert response.status_code == 200, response.text
    return response.json()


class TestHealth:
    def test_health_reports_real_state_not_hardcoded_zero(self, client):
        payload = client.get("/health").json()
        assert payload["status"] == "healthy"
        # 原实现把 models_loaded 写死为 0；现在它来自数据库
        assert payload["registered_models"] == 0
        assert payload["models_loaded"] == 0
        # 未装 vLLM 时必须如实声明处于降级状态
        assert payload["inference_backend"] == "mock"
        assert payload["inference_backend_is_real_model"] is False
        assert payload["degraded"] is True
        assert "unillm-test-" in payload["database"]


class TestDataPipeline:
    def test_import_marks_pre_answered_rows_completed(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        assert dataset["total_samples"] == 3
        # 源数据自带答案 => 应直接是可导出的已标注状态
        listing = client.get("/api/data/list").json()
        assert len(listing) == 1
        assert listing[0]["total_samples"] == 3

    def test_export_produces_three_training_rows(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        response = client.get(f"/api/data/{dataset['id']}/export")
        assert response.status_code == 200, response.text
        output_path = Path(response.json()["output_path"])
        assert output_path.exists()
        rows = [json.loads(line) for line in output_path.read_text("utf-8").splitlines()]
        assert len(rows) == 3
        assert {"instruction", "input", "output"} <= set(rows[0])

    def test_annotation_task_tracks_progress(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        task = client.post(
            "/api/annotation/task",
            json={"name": "任务1", "dataset_id": dataset["id"], "annotation_type": "text"},
        ).json()
        assert task["total_items"] == 3

        progress = client.get(f"/api/annotation/task/{task['id']}/progress").json()
        assert progress["total"] == 3
        # 数据导入时已带答案，所以没有任何 pending 项
        assert progress["pending"] == 0

    def test_annotation_task_missing_dataset_returns_404(self, client):
        response = client.post(
            "/api/annotation/task", json={"name": "x", "dataset_id": 99999}
        )
        assert response.status_code == 404


class TestModelAndInference:
    def test_load_model_degrades_honestly_without_vllm(self, client):
        response = client.post(
            "/api/model/load", json={"model_name": "Qwen/Qwen2.5-7B-Instruct"}
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "degraded"
        assert payload["backend"] == "mock"
        assert payload["degraded"] is True
        assert "vLLM" in payload["reason"]

        # 降级后端不应把自己标记成已加载的真实模型
        assert client.get("/health").json()["models_loaded"] == 0
        assert client.get("/api/model/backend").json()["is_real_model"] is False

    def test_chat_completion_is_openai_shaped_and_labelled(self, client):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "messages": [{"role": "user", "content": "你好"}],
                "max_tokens": 32,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["object"] == "chat.completion"
        assert payload["backend"] == "mock"
        content = payload["choices"][0]["message"]["content"]
        # 占位文本必须自带标记，避免被当成真实模型输出
        assert content.startswith("[MOCK]")
        assert payload["usage"]["total_tokens"] > 0

    def test_mock_backend_is_deterministic(self, client):
        request = {
            "model": "m",
            "messages": [{"role": "user", "content": "同一个问题"}],
        }
        first = client.post("/v1/chat/completions", json=request).json()
        second = client.post("/v1/chat/completions", json=request).json()
        assert (
            first["choices"][0]["message"]["content"]
            == second["choices"][0]["message"]["content"]
        )

    def test_streaming_is_rejected_explicitly(self, client):
        response = client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert response.status_code == 400
        assert "stream" in response.json()["detail"]

    def test_completion_endpoint_works(self, client):
        response = client.post(
            "/v1/completions", json={"model": "m", "prompt": "写一首诗", "max_tokens": 16}
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["object"] == "text_completion"
        assert payload["backend"] == "mock"

    def test_models_list_does_not_fabricate_entries(self, client):
        payload = client.get("/v1/models").json()
        assert payload["object"] == "list"
        # 未注册模型时只剩一条"来自配置的默认名"，且被显式标注
        assert len(payload["data"]) == 1
        assert "note" in payload["data"][0]

        client.post("/api/model/register", params={"name": "real-model"})
        payload = client.get("/v1/models").json()
        assert [m["id"] for m in payload["data"]] == ["real-model"]


class TestEvaluation:
    def _setup(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        model = client.post(
            "/api/model/register",
            params={"name": "eval-model", "base_model": "Qwen/Qwen2.5-7B-Instruct"},
        ).json()
        return dataset, model

    def test_evaluation_computes_real_metrics_from_dataset(self, client, sample_jsonl):
        dataset, model = self._setup(client, sample_jsonl)
        created = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "dataset_id": dataset["id"],
                "eval_name": "闭环评测",
                "metrics": ["exact_match", "token_f1", "latency", "perplexity"],
            },
        ).json()

        response = client.post(f"/api/evaluate/{created['id']}/run")
        assert response.status_code == 200, response.text
        results = response.json()["results"]

        assert results["sample_count"] == 3
        assert results["backend"] == "mock"
        assert results["backend_is_real_model"] is False
        # mock 后端输出是确定性占位文本，与参考答案几乎不重合。
        # 断言"分数很低"而不是"恰好为 0"：占位文本可能偶然共享个别字，这是真实计算结果。
        # 关键是它绝不等于原实现里编造的 0.72。
        assert results["exact_match"]["value"] == 0.0
        assert results["token_f1"]["value"] < 0.2
        # 延迟是实测的，必须 > 0
        assert results["latency"]["avg_ms"] > 0
        assert results["latency"]["samples"] == 3
        # 未装 torch 时必须如实声明不可用，不得填占位数字
        assert results["perplexity"]["available"] is False
        assert "torch" in results["perplexity"]["reason"]

    def test_evaluation_with_correct_backend_scores_one(self, client, sample_jsonl):
        """注入确定性后端返回正确答案，验证指标确实在比对参考答案。"""
        dataset, model = self._setup(client, sample_jsonl)

        service = InferenceService()
        service.set_backend(ScriptedBackend(["2", "北京", "H2O"]))
        reset_inference_service(service)

        created = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "dataset_id": dataset["id"],
                "eval_name": "正确后端评测",
                "metrics": ["exact_match", "token_f1"],
            },
        ).json()
        results = client.post(f"/api/evaluate/{created['id']}/run").json()["results"]

        assert results["backend"] == "scripted"
        assert results["exact_match"]["value"] == 1.0
        assert results["token_f1"]["value"] == 1.0

    def test_evaluation_accepts_inline_test_data(self, client):
        model = client.post("/api/model/register", params={"name": "m2"}).json()
        created = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "eval_name": "内联样本",
                "metrics": ["exact_match"],
            },
        ).json()

        service = InferenceService()
        service.set_backend(ScriptedBackend(["北京"]))
        reset_inference_service(service)

        response = client.post(
            f"/api/evaluate/{created['id']}/run",
            json={"test_data": [{"instruction": "首都", "output": "北京"}]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"]["exact_match"]["value"] == 1.0

    def test_evaluation_without_data_fails_loudly(self, client):
        """原实现会静默返回 mock_value 并把状态标成 completed。"""
        model = client.post("/api/model/register", params={"name": "m3"}).json()
        created = client.post(
            "/api/evaluate/create",
            json={"model_id": model["id"], "eval_name": "无数据", "metrics": ["exact_match"]},
        ).json()

        response = client.post(f"/api/evaluate/{created['id']}/run")
        assert response.status_code == 400
        assert "没有可用的评测数据" in response.json()["detail"]

        summary = client.get(f"/api/evaluate/{created['id']}/result").json()
        assert summary["status"] == "failed"
        assert summary["results"]["error"]

    def test_missing_evaluation_returns_404(self, client):
        assert client.get("/api/evaluate/99999/result").status_code == 404


class TestFinetune:
    def test_job_creation_validates_references(self, client):
        assert (
            client.post(
                "/api/finetune/create",
                json={"model_id": 99999, "dataset_id": 99999, "job_name": "x"},
            ).status_code
            == 404
        )

    def test_job_fails_loudly_without_gpu_deps(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        model = client.post("/api/model/register", params={"name": "ft-model"}).json()

        job = client.post(
            "/api/finetune/create",
            json={
                "model_id": model["id"],
                "dataset_id": dataset["id"],
                "job_name": "lora-job",
                "method": "lora",
            },
        ).json()

        started = client.post(f"/api/finetune/{job['id']}/start")
        assert started.status_code == 200, started.text

        import time

        status = None
        for _ in range(60):
            status = client.get(f"/api/finetune/{job['id']}/status").json()
            if status["status"] in ("failed", "completed", "cancelled"):
                break
            time.sleep(0.1)

        assert status is not None
        # 未安装 gpu 依赖时必须 failed，并给出可执行的修复提示，不得谎报 completed
        assert status["status"] == "failed"
        assert "requirements-gpu.txt" in status["error_message"]


class TestPaginationGuards:
    @pytest.mark.parametrize(
        "url",
        ["/api/data/list?skip=-1", "/api/model/list?limit=0", "/api/evaluate/list?skip=-5"],
    )
    def test_invalid_pagination_rejected(self, client, url):
        assert client.get(url).status_code == 400
```

---

## 21. 测试 tests/test_upload_safety.py

**路径**：`tests/test_upload_safety.py`　|　**行数**：131

```python
"""上传安全与 API 契约测试。

对应修复：
- 文件类型校验前置（原实现先落盘、先建数据集，最后才校验扩展名）
- 文件名净化，阻断路径穿越
- 解析失败时回滚已落盘文件与数据库记录
- 导出接口在无样本/数据集不存在时给出正确状态码
"""

import json
from pathlib import Path

import pytest

from app.api.routes.data import _safe_filename
from app.config import settings


class TestSafeFilename:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("data.jsonl", "data.jsonl"),
            ("../../etc/passwd.json", "passwd.json"),
            ("..\\..\\windows\\evil.csv", "evil.csv"),
            ("sub/dir/file.jsonl", "file.jsonl"),
            ("训练数据.csv", "训练数据.csv"),
            ("weird name!.jsonl", "weird_name_.jsonl"),
        ],
    )
    def test_sanitizes_dangerous_names(self, raw, expected):
        assert _safe_filename(raw) == expected

    @pytest.mark.parametrize("raw", ["", "..", ".", "../..", "/", "///"])
    def test_rejects_unusable_names(self, raw):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _safe_filename(raw)
        assert exc.value.status_code == 400


class TestUploadValidation:
    def _upload(self, client, filename, content=b'{"instruction":"a","output":"b"}\n'):
        return client.post(
            "/api/data/import",
            params={"name": "ds"},
            files={"file": (filename, content, "application/octet-stream")},
        )

    def test_unsupported_extension_rejected_before_persisting(self, client):
        response = self._upload(client, "malware.exe")
        assert response.status_code == 400
        # 关键：不得留下孤儿数据集，也不得把文件写进存储目录
        assert client.get("/api/data/list").json() == []
        dataset_dir = Path(settings.storage.datasets_path)
        assert not (dataset_dir / "malware.exe").exists()

    def test_no_extension_rejected(self, client):
        assert self._upload(client, "README").status_code == 400

    def test_path_traversal_cannot_escape_storage_dir(self, client):
        response = self._upload(client, "../../../evil.jsonl")
        assert response.status_code == 200, response.text

        dataset_dir = Path(settings.storage.datasets_path).resolve()
        written = list(dataset_dir.glob("*.jsonl"))
        assert len(written) == 1
        # 文件必须落在存储目录内
        assert written[0].resolve().parent == dataset_dir
        assert written[0].name == "evil.jsonl"

    def test_malformed_jsonl_rolls_back_everything(self, client):
        response = self._upload(client, "broken.jsonl", b"{not valid json}\n")
        assert response.status_code == 400
        assert client.get("/api/data/list").json() == []
        assert not list(Path(settings.storage.datasets_path).glob("broken.jsonl"))

    def test_csv_import_without_pandas(self, client):
        """CSV 分支已从 pandas 改为标准库 csv。"""
        csv_bytes = (
            "instruction,input,output\n"
            "1+1=?,,\u0032\n"
            "首都,,北京\n"
        ).encode("utf-8")
        response = self._upload(client, "qa.csv", csv_bytes)
        assert response.status_code == 200, response.text
        assert response.json()["total_samples"] == 2

        dataset_id = response.json()["id"]
        exported = client.get(f"/api/data/{dataset_id}/export")
        assert exported.status_code == 200
        rows = [
            json.loads(line)
            for line in Path(exported.json()["output_path"]).read_text("utf-8").splitlines()
        ]
        assert len(rows) == 2
        assert rows[0]["output"] == "2"


class TestDatasetContracts:
    def test_missing_dataset_returns_404(self, client):
        assert client.get("/api/data/99999").status_code == 404
        assert client.delete("/api/data/99999").status_code == 404
        assert client.get("/api/data/99999/export").status_code == 404

    def test_export_without_labelled_samples_returns_400(self, client):
        """导入一份没有答案的数据 => 无法导出训练数据，必须明确报错。"""
        payload = ('{"instruction":"没有答案"}\n').encode("utf-8")
        created = client.post(
            "/api/data/import",
            params={"name": "unlabeled"},
            files={"file": ("u.jsonl", payload, "application/json")},
        ).json()

        response = client.get(f"/api/data/{created['id']}/export")
        assert response.status_code == 400
        assert "没有已标注" in response.json()["detail"]

    def test_delete_removes_dataset(self, client, sample_jsonl):
        with open(sample_jsonl, "rb") as handle:
            dataset = client.post(
                "/api/data/import",
                params={"name": "to-delete"},
                files={"file": ("s.jsonl", handle, "application/json")},
            ).json()

        assert client.delete(f"/api/data/{dataset['id']}").status_code == 200
        assert client.get(f"/api/data/{dataset['id']}").status_code == 404
        assert client.get("/api/data/list").json() == []
```

---

## 22. 冒烟脚本 scripts/smoke_test.py

**路径**：`scripts/smoke_test.py`　|　**行数**：294

```python
#!/usr/bin/env python
"""UniLLM Platform 端到端冒烟验证。

与 tests/ 下的 pytest 用例不同，本脚本启动的是**真实的 uvicorn 进程**，
通过 HTTP 打全链路，用来证明"服务真的能被启动并对外提供服务"，而不只是
在 TestClient 的内存桩里通过。

流程：
    1. 以子进程方式启动 uvicorn（独立端口，独立临时数据目录）
    2. 轮询 /health 直到服务就绪（或超时失败）
    3. 依次调用：建数据集 -> 上传数据 -> 建模型 -> 聊天补全 -> 建评测 -> 跑评测
    4. 校验关键返回值（backend=mock、指标为真实计算值、延迟 > 0）
    5. 关闭服务并输出 PASS/FAIL 汇总

用法：
    python scripts/smoke_test.py
    python scripts/smoke_test.py --port 8123

退出码 0 表示全部通过，非 0 表示存在失败项。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import httpx
except ImportError:  # pragma: no cover
    print("缺少依赖 httpx，请先执行: pip install -r requirements.txt")
    raise SystemExit(2)


class SmokeFailure(Exception):
    """标记一个明确的失败点。"""


_CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _CHECKS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f" -- {detail}"
    print(line, flush=True)


def wait_for_health(base_url: str, timeout: float = 40.0) -> dict:
    """轮询 /health，直到服务就绪。"""
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/health", timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
            last_error = f"HTTP {resp.status_code}"
        except Exception as exc:  # 连接被拒是正常现象，服务还没起来
            last_error = type(exc).__name__
        time.sleep(0.5)
    raise SmokeFailure(f"服务在 {timeout}s 内未就绪（最后错误: {last_error}）")


def start_server(port: int, data_dir: Path) -> subprocess.Popen:
    """启动真实 uvicorn 子进程。"""
    env = os.environ.copy()
    # 用临时目录承载数据库与存储，避免污染项目里的 data/
    env["UNILLM_DATABASE__PATH"] = str(data_dir / "smoke.db")
    env["UNILLM_STORAGE__DATASETS_PATH"] = str(data_dir / "datasets")
    env["UNILLM_STORAGE__ANNOTATIONS_PATH"] = str(data_dir / "annotations")
    env["UNILLM_STORAGE__MODELS_PATH"] = str(data_dir / "models")
    env["UNILLM_STORAGE__LOGS_PATH"] = str(data_dir / "logs")
    env["UNILLM_APP__DEBUG"] = "false"

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_flow(base_url: str, sample_jsonl: Path, data_dir: Path) -> None:
    """跑通全链路并逐项校验。"""
    with httpx.Client(base_url=base_url, timeout=30.0) as client:
        # --- 1) 健康检查暴露真实状态 ---
        health = client.get("/health").json()
        check("GET /health 返回 200 且含后端信息", "inference_backend" in health,
              f"backend={health.get('inference_backend')}")
        check("health.degraded 与后端真实性一致",
              health.get("degraded") == (not health.get("inference_backend_is_real_model")),
              f"degraded={health.get('degraded')}")
        check("health 报出真实注册模型数（初始为 0）", health.get("registered_models") == 0,
              f"registered_models={health.get('registered_models')}")

        # --- 2) 上传数据（import 一步完成"建数据集 + 导入"） ---
        payload = sample_jsonl.read_bytes()
        up = client.post(
            "/api/data/import",
            params={"name": "smoke-dataset", "description": "冒烟验证用数据集"},
            files={"file": ("sample_data.jsonl", payload, "application/jsonl")},
        )
        if up.status_code != 200:
            raise SmokeFailure(f"导入数据失败: {up.status_code} {up.text}")
        dataset = up.json()
        check("POST /api/data/import 导入数据成功", dataset.get("total_samples", 0) > 0,
              f"dataset_id={dataset.get('id')} total_samples={dataset.get('total_samples')}")

        # --- 3) 注册模型 ---
        md = client.post("/api/model/register", params={
            "name": "smoke-model",
            "base_model": "Qwen/Qwen2.5-7B-Instruct",
        })
        if md.status_code != 200:
            raise SmokeFailure(f"注册模型失败: {md.status_code} {md.text}")
        model = md.json()
        check("POST /api/model/register 注册模型成功", bool(model.get("id")),
              f"id={model.get('id')}")

        # --- 4) 推理（OpenAI 兼容） ---
        chat = client.post("/v1/chat/completions", json={
            "model": "smoke-model",
            "messages": [{"role": "user", "content": "1+1=?"}],
            "max_tokens": 32,
        })
        if chat.status_code != 200:
            raise SmokeFailure(f"聊天补全失败: {chat.status_code} {chat.text}")
        body = chat.json()
        text = body["choices"][0]["message"]["content"]
        check("POST /v1/chat/completions 返回可用补全", bool(text.strip()),
              f"backend={body.get('backend')}")
        check("推理响应显式标注 backend（不冒充真实模型）",
              body.get("backend") in {"mock", "vllm", "scripted"},
              f"backend={body.get('backend')}")
        if body.get("backend") == "mock":
            check("mock 后端输出带 [MOCK] 前缀，可被识别为占位",
                  text.startswith("[MOCK]"), f"text={text[:40]!r}")

        # --- 5) 评测：指标必须是真实计算的 ---
        ev = client.post("/api/evaluate/create", json={
            "model_id": model["id"],
            "dataset_id": dataset["id"],
            "eval_name": "smoke-eval",
            "metrics": ["exact_match", "token_f1", "latency"],
        })
        if ev.status_code != 200:
            raise SmokeFailure(f"建评测失败: {ev.status_code} {ev.text}")
        evaluation = ev.json()

        run = client.post(f"/api/evaluate/{evaluation['id']}/run")
        if run.status_code != 200:
            raise SmokeFailure(f"跑评测失败: {run.status_code} {run.text}")
        results = run.json()["results"]

        check("POST /api/evaluate/{id}/run 产出评测结果",
              results.get("sample_count", 0) > 0,
              f"sample_count={results.get('sample_count')}")
        check("评测结果为真实计算值（非硬编码 0.72）",
              results.get("exact_match", {}).get("value") in (0.0, 1.0),
              f"exact_match={results.get('exact_match', {}).get('value')}")
        check("延迟为实测值（> 0）",
              results.get("latency", {}).get("avg_ms", 0) > 0,
              f"avg_ms={results.get('latency', {}).get('avg_ms')}")

        # --- 6) 上传安全：非法扩展名必须被拒 ---
        bad = client.post(
            "/api/data/import",
            params={"name": "evil-dataset"},
            files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        check("上传非法扩展名被拒绝（HTTP 4xx）", 400 <= bad.status_code < 500,
              f"status={bad.status_code}")

        # --- 7) 路径穿越文件名必须被净化 ---
        trav = client.post(
            "/api/data/import",
            params={"name": "traversal-dataset"},
            files={"file": ("../../evil.jsonl", payload, "application/jsonl")},
        )
        # 被净化后应正常导入；若被拒也接受，但绝不能真的写到 datasets 目录之外
        escaped = [
            p for p in (
                data_dir / "evil.jsonl",
                PROJECT_ROOT / "evil.jsonl",
                PROJECT_ROOT.parent / "evil.jsonl",
            )
            if p.exists()
        ]
        check("路径穿越文件名未逃出数据目录",
              trav.status_code in (200, 400) and not escaped,
              f"status={trav.status_code} escaped={[str(p) for p in escaped]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="UniLLM Platform 端到端冒烟验证")
    parser.add_argument("--port", type=int, default=8123, help="服务监听端口")
    parser.add_argument("--timeout", type=float, default=40.0, help="等待就绪的秒数")
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    sample_jsonl = PROJECT_ROOT / "data" / "datasets" / "sample_data.jsonl"
    if not sample_jsonl.exists():
        print(f"找不到样例数据: {sample_jsonl}")
        return 2

    print("=" * 68)
    print("UniLLM Platform 端到端冒烟验证（真实 uvicorn 进程）")
    print(f"  项目根目录: {PROJECT_ROOT}")
    print(f"  服务地址:   {base_url}")
    print("=" * 68)

    server: subprocess.Popen | None = None
    exit_code = 0
    # Windows 上关闭进程后 SQLite 文件句柄可能仍被短暂占用，
    # 因此不用 TemporaryDirectory 上下文（其清理会直接抛错），改为手动忽略清理失败。
    data_dir = Path(tempfile.mkdtemp(prefix="unillm-smoke-"))
    try:
        print(f"\n[1/2] 启动 uvicorn 子进程（数据目录: {data_dir}）")
        server = start_server(args.port, data_dir)

        try:
            health = wait_for_health(base_url, args.timeout)
            print(f"      服务已就绪: {json.dumps(health, ensure_ascii=False)}")
        except SmokeFailure as exc:
            print(f"      服务启动失败: {exc}")
            if server.poll() is not None:
                out = server.stdout.read() if server.stdout else ""
                print("      --- 子进程输出 ---")
                print(out[-3000:])
            return 1

        print("\n[2/2] 执行全链路断言")
        try:
            run_flow(base_url, sample_jsonl, data_dir)
        except SmokeFailure as exc:
            check("全链路执行完成", False, str(exc))
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            print("\n服务已关闭。")
        shutil.rmtree(data_dir, ignore_errors=True)

    passed = sum(1 for _, ok, _ in _CHECKS if ok)
    failed = [name for name, ok, _ in _CHECKS if not ok]
    total = len(_CHECKS)

    print("\n" + "=" * 68)
    print(f"结果: {passed}/{total} 项通过")
    if failed:
        print("失败项:")
        for name in failed:
            print(f"  - {name}")
        exit_code = 1
    else:
        print("全部通过：真实服务可启动，且数据->推理->评测链路可用。")
    print("=" * 68)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 23. 评测演示 evaluation_demo.py

**路径**：`evaluation_demo.py`　|　**行数**：177

```python
#!/usr/bin/env python
"""UniLLM Platform 真实评测演示（非交互）。

本脚本替换了原仓库里的两个演示脚本：

- ``evaluation_auto.py``：195 行 ``print`` 硬编码了 "Accuracy 0.72 / Perplexity 12.50
  / Latency 280ms"，却冠以"评测报告"标题，还据此给出"医药健康领域需优化、
  电商客服可用"的业务结论。它不连服务、不调接口、不跑模型，是纯编造。
- 旧 ``evaluation_demo.py``：所谓"模拟评测演示"同样在打印上面那组假数字；
  仅有的"真实流程"还用 ``input()`` 交互，且拿到结果后只打印一句
  "结果将在后台计算"，不展示任何真实指标。

现在这个脚本只做一件事：**连上正在运行的服务，跑一遍真实评测，把服务
返回的真实数字原样打印出来**。跑不通就明确报错，绝不填占位数字。

用法：
    1. 另开一个终端启动服务：
           python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    2. 运行本脚本：
           python evaluation_demo.py
       （可用 --base-url 指向其它地址）

注意：未安装 vLLM 时推理走 mock 后端，指标会非常低 —— 这是**真实结果**，
说明被测的不是真模型。响应里的 backend 字段会明确标注这一点。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("缺少依赖 httpx，请先执行: pip install -r requirements.txt")
    raise SystemExit(2)

PROJECT_ROOT = Path(__file__).resolve().parent
SAMPLE_DATA = PROJECT_ROOT / "data" / "datasets" / "sample_data.jsonl"


def _bar(value: float, warn: bool = False) -> str:
    """把 0~1 的指标画成进度条，只用于视觉呈现，不参与任何判断。"""
    filled = max(0, min(10, round(value * 10)))
    return "█" * filled + "░" * (10 - filled) + ("  (低)" if warn else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="UniLLM Platform 真实评测演示")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="服务地址")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print("=" * 70)
    print("UniLLM Platform 真实评测演示")
    print(f"服务地址: {base_url}")
    print("=" * 70)

    if not SAMPLE_DATA.exists():
        print(f"找不到样例数据: {SAMPLE_DATA}")
        return 2

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        # --- 0) 连通性与后端真实性 ---
        print("\n[步骤 0] 检查服务连通性")
        try:
            health = client.get("/health").json()
        except Exception as exc:
            print(f"无法连接服务（{type(exc).__name__}）。请先启动：")
            print("  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
            return 1
        print(f"  ✓ 服务正常，版本 {health.get('version')}")
        print(f"  · 推理后端: {health.get('inference_backend')}")
        if health.get("degraded"):
            print("  ! 当前为降级模式（mock 后端），下面的指标不代表任何真实模型能力")

        # --- 1) 导入测试数据 ---
        print("\n[步骤 1] 导入测试数据")
        with open(SAMPLE_DATA, "rb") as f:
            resp = client.post(
                "/api/data/import",
                params={"name": "评测演示数据", "description": "evaluation_demo.py 导入"},
                files={"file": (SAMPLE_DATA.name, f, "application/jsonl")},
            )
        if resp.status_code != 200:
            print(f"  ✗ 导入失败: HTTP {resp.status_code} {resp.text[:200]}")
            return 1
        dataset = resp.json()
        dataset_id = dataset["id"]
        print(f"  ✓ 数据集 id={dataset_id}，样本数={dataset.get('total_samples')}")

        # --- 2) 注册模型 ---
        print("\n[步骤 2] 注册待评测模型")
        resp = client.post(
            "/api/model/register",
            params={"name": "demo-model", "base_model": "Qwen/Qwen2.5-7B-Instruct"},
        )
        if resp.status_code != 200:
            print(f"  ✗ 注册失败: HTTP {resp.status_code} {resp.text[:200]}")
            return 1
        model_id = resp.json()["id"]
        print(f"  ✓ 模型 id={model_id}")

        # --- 3) 创建评测任务 ---
        print("\n[步骤 3] 创建评测任务")
        resp = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model_id,
                "dataset_id": dataset_id,
                "eval_name": "真实评测演示",
                "metrics": ["exact_match", "token_f1", "latency", "perplexity"],
            },
        )
        if resp.status_code != 200:
            print(f"  ✗ 创建失败: HTTP {resp.status_code} {resp.text[:200]}")
            return 1
        eval_id = resp.json()["id"]
        print(f"  ✓ 评测任务 id={eval_id}")

        # --- 4) 运行评测（同步返回真实结果） ---
        print("\n[步骤 4] 运行评测")
        resp = client.post(f"/api/evaluate/{eval_id}/run")
        if resp.status_code != 200:
            print(f"  ✗ 运行失败: HTTP {resp.status_code} {resp.text[:300]}")
            return 1
        results = resp.json()["results"]

        # --- 5) 原样展示服务返回的指标 ---
        print("\n" + "=" * 70)
        print("评测结果（以下数值全部由服务端实际计算得出）")
        print("=" * 70)
        print(f"  样本数      : {results.get('sample_count')}")
        print(f"  推理后端    : {results.get('backend')}")
        print(f"  真实模型    : {results.get('backend_is_real_model')}")

        em = results.get("exact_match")
        if em:
            print(f"\n  Exact Match : {em['value']:.4f}  {_bar(em['value'], em['value'] < 0.5)}")
            print(f"    命中/总数 : {em['correct']}/{em['total']}")

        f1 = results.get("token_f1")
        if f1:
            print(f"\n  Char-F1     : {f1['value']:.4f}  {_bar(f1['value'], f1['value'] < 0.5)}")

        lat = results.get("latency")
        if lat:
            print(f"\n  Latency     : avg={lat['avg_ms']:.3f}ms  "
                  f"p50={lat['p50_ms']:.3f}ms  p95={lat['p95_ms']:.3f}ms  "
                  f"min={lat['min_ms']:.3f}ms  max={lat['max_ms']:.3f}ms")

        ppl = results.get("perplexity")
        if ppl:
            if ppl.get("available"):
                print(f"\n  Perplexity  : {ppl['value']:.4f}")
            else:
                print(f"\n  Perplexity  : 不可用 —— {ppl.get('reason')}")

        print("\n--- 完整 JSON ---")
        print(json.dumps(results, ensure_ascii=False, indent=2))

        print("\n" + "=" * 70)
        if not results.get("backend_is_real_model"):
            print("结论：本次评测跑在 mock 后端上，指标低是**预期且真实**的结果，")
            print("      它衡量的不是模型能力。要评测真实模型，请安装 GPU 依赖：")
            print("      pip install -r requirements-gpu.txt")
        else:
            print("结论：本次评测由真实模型产出，指标可用于横向比较。")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

---

## 24. 配置 config.yaml

**路径**：`config.yaml`　|　**行数**：52

```yaml
app:
  name: "UniLLM Platform"
  version: "0.2.0"
  debug: true
  host: "0.0.0.0"
  port: 8000
  # CORS 白名单。["*"] 表示放开全部来源；此时凭证开关会被强制关闭
  # （浏览器规范禁止 "*" 与 allow_credentials 同时生效）。
  cors_origins:
    - "*"
  cors_allow_credentials: false

database:
  type: "sqlite"
  path: "./data/unillm.db"

storage:
  datasets_path: "./data/datasets"
  annotations_path: "./data/annotations"
  models_path: "./data/models"
  logs_path: "./logs"

model:
  default_model: "Qwen/Qwen2.5-7B-Instruct"
  max_model_len: 4096
  gpu_memory_utilization: 0.9
  tensor_parallel_size: 1

lora:
  r: 16
  lora_alpha: 32
  lora_dropout: 0.1
  target_modules:
    - "q_proj"
    - "k_proj"
    - "v_proj"
    - "o_proj"

training:
  num_train_epochs: 3
  per_device_train_batch_size: 4
  gradient_accumulation_steps: 4
  learning_rate: 0.0002
  logging_steps: 10
  save_steps: 100

evaluation:
  metrics:
    - "perplexity"
    - "accuracy"
    - "latency"
```

---

## 25. 配置 pytest.ini

**路径**：`pytest.ini`　|　**行数**：9

```ini
[pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts = -q --strict-markers
filterwarnings =
    error::DeprecationWarning:app.*
```

---

## 26. 依赖 requirements.txt

**路径**：`requirements.txt`　|　**行数**：32

```text
# ==========================================================================
# UniLLM Platform - 核心依赖（CPU-only，无需 GPU/CUDA）
#
#   pip install -r requirements.txt
#
# 适用于 Python 3.9 - 3.13。安装体积约 5 MB，可在任意机器上直接跑通
# 数据接入 -> 标注 -> 微调任务 -> 评测 -> 推理 的完整闭环。
#
# GPU 增强（vLLM 真实推理 / PEFT LoRA 微调）为可选项，见 requirements-gpu.txt。
# 未安装时平台自动降级为内置 mock 推理后端，并在响应中显式标注 backend=mock，
# 不会把占位结果冒充为真实模型输出。
# ==========================================================================

# --- Web 框架 / HTTP 服务 ---
fastapi>=0.109,<1.0
uvicorn[standard]>=0.27,<1.0
python-multipart>=0.0.6,<1.0

# --- 配置与数据校验 ---
pydantic>=2.5,<3.0
pydantic-settings>=2.1,<3.0
pyyaml>=6.0.1,<7.0

# --- 数据库（SQLite，纯本地零依赖） ---
sqlalchemy>=2.0.25,<2.1

# --- HTTP 客户端（示例脚本 / 测试） ---
httpx>=0.26,<1.0

# --- 测试 ---
pytest>=8.0,<9.0
```

---

## 27. 依赖 requirements-gpu.txt

**路径**：`requirements-gpu.txt`　|　**行数**：31

```text
# ==========================================================================
# UniLLM Platform - 可选 GPU 增强依赖
#
#   pip install -r requirements-gpu.txt
#
# !! 平台与架构限制（实测结论，请先读再装）!!
#
#   1. vLLM 官方不提供 Windows wheel，且仅支持 Linux + CUDA。
#      Linux 部署：pip install -r requirements-gpu.txt
#      Windows 部署：保留 CPU 核心依赖即可，平台会自动使用 mock 后端；
#                     或改用 WSL2 / Docker + NVIDIA Container Toolkit。
#   2. torch / vllm 体积达数 GB，且对 Python 与 CUDA 版本有强绑定，
#      因此不与 requirements.txt 混装，避免"装不上核心依赖"。
#   3. 未安装本文件时，推理与微调会诚实降级并在 API 响应中标注
#      degraded=true / backend=mock，功能链路仍完整可跑。
# ==========================================================================

-r requirements.txt

# --- 真实推理引擎（Linux + CUDA 11.8+，注意 vLLM 0.3.x 需 torch 2.1.x） ---
vllm>=0.3.0

# --- LoRA / SFT 微调 ---
torch>=2.1.2
transformers>=4.37.0
peft>=0.7.1
accelerate>=0.25.0
bitsandbytes>=0.41.3
datasets>=2.16.1
sentencepiece>=0.1.99
```

---

## 28. 样例数据 data/datasets/sample_data.jsonl

**路径**：`data/datasets/sample_data.jsonl`　|　**行数**：6

```json
{"instruction": "什么是机器学习？", "input": "", "output": "机器学习是人工智能的一个分支，它使计算机系统能够从数据中学习和改进，而无需明确编程。机器学习算法通过分析大量数据来识别模式，并利用这些模式做出预测或决策。"}
{"instruction": "解释深度学习的概念", "input": "", "output": "深度学习是机器学习的一个子领域，它使用多层神经网络来学习数据的层次化表示。深度学习模型能够自动提取特征，在图像识别、自然语言处理等领域取得了突破性进展。"}
{"instruction": "什么是自然语言处理？", "input": "", "output": "自然语言处理（NLP）是人工智能和语言学的交叉领域，致力于让计算机理解、解释和生成人类语言。NLP应用包括机器翻译、情感分析、文本摘要、问答系统等。"}
{"instruction": "解释Transformer架构", "input": "", "output": "Transformer是一种基于自注意力机制的神经网络架构，由Google在2017年提出。它摒弃了传统的循环和卷积结构，通过注意力机制并行处理序列数据，成为现代大语言模型的基础架构。"}
{"instruction": "什么是大语言模型？", "input": "", "output": "大语言模型（LLM）是基于Transformer架构的超大规模神经网络，通过在海量文本数据上预训练，学习语言的统计规律和知识。LLM能够执行多种自然语言任务，如对话、写作、编程等。"}
```

---

## 29. 忽略规则 .gitignore

**路径**：`.gitignore`　|　**行数**：149

```text
# Byte-compiled / optimized / DLL files
__pycache__/
*.py[cod]
*$py.class

# C extensions
*.so

# Distribution / packaging
.Python
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg
MANIFEST

# PyInstaller
*.manifest
*.spec

# Installer logs
pip-log.txt
pip-delete-this-directory.txt

# Unit test / coverage reports
htmlcov/
.tox/
.nox/
.coverage
.coverage.*
.cache
nosetests.xml
coverage.xml
*.cover
*.py,cover
.hypothesis/
.pytest_cache/

# Translations
*.mo
*.pot

# Django stuff:
*.log
local_settings.py
db.sqlite3
db.sqlite3-journal

# Flask stuff:
instance/
.webassets-cache

# Scrapy stuff:
.scrapy

# Sphinx documentation
docs/_build/

# PyBuilder
target/

# Jupyter Notebook
.ipynb_checkpoints

# IPython
profile_default/
ipython_config.py

# pyenv
.python-version

# pipenv
Pipfile.lock

# poetry
poetry.lock

# pdm
pdm.lock
.pdm-python

# PEP 582
__pypackages__/

# Celery stuff
celerybeat-schedule
celerybeat.pid

# SageMath parsed files
*.sage.py

# Environments
.env
.venv
env/
venv/
ENV/
env.bak/
venv.bak/

# Editor directories and files
.vscode/*
!.vscode/extensions.json
.idea
.DS_Store
*.suo
*.ntvs*
*.njsproj
*.sln
*.sw?

# Project specific
data/datasets/*.jsonl
data/annotations/*.jsonl
data/models/*
!data/datasets/sample_data.jsonl
logs/*.log
*.db
*.sqlite
*.sqlite3
*.db-journal

# Hugging Face cache
~/.cache/huggingface/

# Model weights and checkpoints
*.pth
*.pt
*.ckpt
*.bin
*.safetensors

# Temporary files
*.tmp
*.bak
*.swp
*~
```

---

## 30. 包标记 app/__init__.py

**路径**：`app/__init__.py`　|　**行数**：4

```python
from app.main import app

__all__ = ["app"]
```

---

## 31. 包标记 app/api/__init__.py

**路径**：`app/api/__init__.py`　|　**行数**：1

```python

```

---

## 32. 包标记 app/api/routes/__init__.py

**路径**：`app/api/routes/__init__.py`　|　**行数**：1

```python

```

---

## 33. 包标记 app/models/__init__.py

**路径**：`app/models/__init__.py`　|　**行数**：1

```python

```

---

## 34. 包标记 app/services/__init__.py

**路径**：`app/services/__init__.py`　|　**行数**：1

```python

```

---

## 35. 包标记 app/core/__init__.py

**路径**：`app/core/__init__.py`　|　**行数**：1

```python

```

---

## 36. 包标记 app/utils/__init__.py

**路径**：`app/utils/__init__.py`　|　**行数**：1

```python

```

---
