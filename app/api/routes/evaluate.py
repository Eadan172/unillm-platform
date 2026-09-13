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
    # A3：校验 model_id 指向的模型确实存在。与读同一资源的语义保持一致
    # （GET /{eval_id}/result 不存在时 404），避免为不存在的模型创建评测。
    if request.model_id is not None and evaluate_service.model_service.get_model(
        request.model_id
    ) is None:
        raise HTTPException(status_code=404, detail=f"Model {request.model_id} not found")

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
