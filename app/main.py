from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path

from app.config import settings
from app.models.database import init_database
from app.models.schemas import HealthResponse
from app.api.routes import data, annotation, model, inference, finetune, evaluate


@asynccontextmanager
async def lifespan(app: FastAPI):
    Path(settings.storage.datasets_path).mkdir(parents=True, exist_ok=True)
    Path(settings.storage.annotations_path).mkdir(parents=True, exist_ok=True)
    Path(settings.storage.models_path).mkdir(parents=True, exist_ok=True)
    Path(settings.storage.logs_path).mkdir(parents=True, exist_ok=True)
    
    init_database(settings.database.path)
    
    yield
    
    print("Shutting down UniLLM Platform...")


app = FastAPI(
    title=settings.app.name,
    version=settings.app.version,
    description="""
## UniLLM Platform - 统一多模态大模型平台

一站式大模型开发平台，支持从数据接入 → 标注 → 微调 → 评测 → 推理的全流程闭环。

### 核心功能

- **数据管理**: 数据导入、存储、导出
- **数据标注**: 标注任务管理、标注结果存储
- **模型管理**: 模型注册、加载、卸载
- **模型推理**: OpenAI 兼容的推理 API
- **模型微调**: LoRA 微调流程
- **模型评测**: 多维度评测指标

### 技术栈

- FastAPI + vLLM + PEFT + SQLite
""",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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
        "redoc": "/redoc"
    }


@app.get("/health", response_model=HealthResponse, tags=["Health"])
async def health_check():
    return HealthResponse(
        status="healthy",
        version=settings.app.version,
        models_loaded=0
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app.host,
        port=settings.app.port,
        reload=settings.app.debug
    )
