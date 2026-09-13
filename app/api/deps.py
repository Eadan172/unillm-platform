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
