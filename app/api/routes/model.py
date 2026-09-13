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
