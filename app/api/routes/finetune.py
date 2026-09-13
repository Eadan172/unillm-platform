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
