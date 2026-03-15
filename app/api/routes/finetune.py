from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.models.database import get_session_maker
from app.models.schemas import FinetuneCreate, FinetuneResponse
from app.services.finetune_service import FinetuneService
from app.config import settings

router = APIRouter(prefix="/api/finetune", tags=["Fine-tuning"])

session_maker = get_session_maker(settings.database.path)


def get_db():
    db = session_maker()
    try:
        yield db
    finally:
        db.close()


def get_finetune_service(db: Session = Depends(get_db)) -> FinetuneService:
    return FinetuneService(db)


@router.post("/create", response_model=FinetuneResponse)
async def create_finetune_job(
    request: FinetuneCreate,
    finetune_service: FinetuneService = Depends(get_finetune_service)
):
    job = finetune_service.model_service.create_finetune_job(
        model_id=request.model_id,
        dataset_id=request.dataset_id,
        job_name=request.job_name,
        method=request.method,
        config=request.config
    )
    return FinetuneResponse(
        id=job.id,
        model_id=job.model_id,
        dataset_id=job.dataset_id,
        job_name=job.job_name,
        method=job.method,
        status=job.status,
        progress=job.progress,
        created_at=job.created_at
    )


@router.post("/{job_id}/start")
async def start_finetune(
    job_id: int,
    finetune_service: FinetuneService = Depends(get_finetune_service)
):
    result = finetune_service.start_finetune(job_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/{job_id}/status")
async def get_finetune_status(
    job_id: int,
    finetune_service: FinetuneService = Depends(get_finetune_service)
):
    status = finetune_service.get_job_status(job_id)
    if not status:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@router.post("/{job_id}/cancel")
async def cancel_finetune(
    job_id: int,
    finetune_service: FinetuneService = Depends(get_finetune_service)
):
    result = finetune_service.cancel_job(job_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/list", response_model=List[FinetuneResponse])
async def list_finetune_jobs(
    model_id: int = None,
    skip: int = 0,
    limit: int = 100,
    finetune_service: FinetuneService = Depends(get_finetune_service)
):
    jobs = finetune_service.model_service.list_finetune_jobs(model_id, skip, limit)
    return [
        FinetuneResponse(
            id=j.id,
            model_id=j.model_id,
            dataset_id=j.dataset_id,
            job_name=j.job_name,
            method=j.method,
            status=j.status,
            progress=j.progress,
            created_at=j.created_at
        ) for j in jobs
    ]
