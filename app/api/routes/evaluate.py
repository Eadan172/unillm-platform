from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.models.database import get_session_maker
from app.models.schemas import EvaluationCreate, EvaluationResponse
from app.services.evaluate_service import EvaluateService
from app.config import settings

router = APIRouter(prefix="/api/evaluate", tags=["Evaluation"])

session_maker = get_session_maker(settings.database.path)


def get_db():
    db = session_maker()
    try:
        yield db
    finally:
        db.close()


def get_evaluate_service(db: Session = Depends(get_db)) -> EvaluateService:
    return EvaluateService(db)


@router.post("/create", response_model=EvaluationResponse)
async def create_evaluation(
    request: EvaluationCreate,
    evaluate_service: EvaluateService = Depends(get_evaluate_service)
):
    evaluation = evaluate_service.create_evaluation(
        model_id=request.model_id,
        eval_name=request.eval_name,
        dataset_id=request.dataset_id,
        metrics=request.metrics
    )
    return EvaluationResponse(
        id=evaluation.id,
        model_id=evaluation.model_id,
        eval_name=evaluation.eval_name,
        status=evaluation.status,
        metrics=evaluation.metrics,
        results=evaluation.results,
        created_at=evaluation.created_at
    )


@router.post("/{eval_id}/run")
async def run_evaluation(
    eval_id: int,
    evaluate_service: EvaluateService = Depends(get_evaluate_service)
):
    result = evaluate_service.run_evaluation(eval_id)
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.get("/{eval_id}/result")
async def get_evaluation_result(
    eval_id: int,
    evaluate_service: EvaluateService = Depends(get_evaluate_service)
):
    result = evaluate_service.get_evaluation_summary(eval_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/list", response_model=List[EvaluationResponse])
async def list_evaluations(
    model_id: int = None,
    skip: int = 0,
    limit: int = 100,
    evaluate_service: EvaluateService = Depends(get_evaluate_service)
):
    evaluations = evaluate_service.list_evaluations(model_id, skip, limit)
    return [
        EvaluationResponse(
            id=e.id,
            model_id=e.model_id,
            eval_name=e.eval_name,
            status=e.status,
            metrics=e.metrics,
            results=e.results,
            created_at=e.created_at
        ) for e in evaluations
    ]
