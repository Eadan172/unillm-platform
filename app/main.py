"""UniLLM Platform 应用入口。

本轮在既有能力之上补齐产品化基座：
1. **鉴权**：``AuthMiddleware`` 对 ``/api/*`` 与 ``/v1/*`` 做统一 Token 校验；
   ``/console/*``、``/health``、``/docs`` 等公开。中间件逐请求读取
   ``settings.app.auth_enabled``（不快照），且 ``OPTIONS`` 预检直接放行。
2. **统一错误契约**：``register_exception_handlers`` 让 401/400/404/413/422/500
   都返回 ``{detail, error_code, hint}``（保留 ``detail`` 键）。
3. **内置控制台**：``/console/`` 托管原生 HTML 控制台（公开静态，数据靠 API 拦）；
   根路径 ``/`` 302 到 ``/console/``，原根 JSON 信息迁到受保护的 ``/api/info``。
4. 中间件顺序保证 **CORS 在最外层**：先加 ``AuthMiddleware`` 再加 ``CORSMiddleware``
   （Starlette 后加的更靠外），避免跨域预检被鉴权拦掉。
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.deps import get_inference_service
from app.api.routes import annotation, auth, data, evaluate, finetune, inference, model
from app.config import PROJECT_ROOT, settings
from app.core import security
from app.core.errors import register_exception_handlers
from app.core.security import AuthMiddleware
from app.models.database import get_session_maker, init_database, resolve_db_path
from app.models.schemas import HealthResponse

# 内置控制台静态目录
WEB_DIR = PROJECT_ROOT / "app" / "web"


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
    # 确保存在访问 Token，并在启动日志中醒目打印（自动生成时同时持久化）
    security.ensure_token()
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
- **内置控制台**: 原生 HTML 控制台，零构建、离线可用（`/console/`）

### 鉴权

`/api/*` 与 `/v1/*` 需要 Token（`Authorization: Bearer <token>` 或 `X-API-Token`）。
`/console/*`、`/health`、`/docs`、`/redoc`、`/openapi.json` 公开。

### 运行模式

未安装 vLLM（GPU 增强依赖）时，推理自动降级为**确定性 mock 后端**：
响应体带 `backend: "mock"`，占位文本以 `[MOCK]` 开头。
这保证无 GPU 的环境也能跑通完整链路，同时不会把占位结果冒充为模型输出。

### 技术栈

FastAPI + SQLAlchemy(SQLite) + vLLM(可选) + PEFT(可选)
""",
    lifespan=lifespan,
)

# 统一错误契约：401/400/404/413/422/500 全部返回 {detail, error_code, hint}
register_exception_handlers(app)

# 中间件顺序：先加 Auth（内层），再加 CORS（外层）——后加的更靠外，保证预检先被 CORS 处理
app.add_middleware(AuthMiddleware)

_cors_origins = settings.app.cors_origins or ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    # 通配来源与携带凭证不能共存，否则浏览器按规范直接拒绝
    allow_credentials=settings.app.cors_allow_credentials and "*" not in _cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内置控制台：静态托管（公开）。html=True 使 /console/ 直接返回 index.html。
WEB_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/console", StaticFiles(directory=str(WEB_DIR), html=True), name="console")

app.include_router(auth.router)
app.include_router(data.router)
app.include_router(annotation.router)
app.include_router(model.router)
app.include_router(inference.router)
app.include_router(finetune.router)
app.include_router(evaluate.router)


@app.get("/", tags=["Root"], include_in_schema=False)
async def root():
    """根路径重定向到内置控制台。"""
    return RedirectResponse("/console/", status_code=302)


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
