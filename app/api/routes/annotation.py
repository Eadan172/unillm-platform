from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.models.database import get_session_maker
from app.models.schemas import (
    AnnotationCreate, AnnotationUpdate, AnnotationResponse,
    AnnotationTaskCreate, AnnotationTaskResponse
)
from app.services.annotation_service import AnnotationService
from app.config import settings

router = APIRouter(prefix="/api/annotation", tags=["Annotation"])

session_maker = get_session_maker(settings.database.path)


def get_db():
    db = session_maker()
    try:
        yield db
    finally:
        db.close()


def get_annotation_service(db: Session = Depends(get_db)) -> AnnotationService:
    return AnnotationService(db)


@router.post("/task", response_model=AnnotationTaskResponse)
async def create_annotation_task(
    task: AnnotationTaskCreate,
    annotation_service: AnnotationService = Depends(get_annotation_service)
):
    created = annotation_service.create_task(
        name=task.name,
        dataset_id=task.dataset_id,
        description=task.description,
        annotation_type=task.annotation_type
    )
    return AnnotationTaskResponse(
        id=created.id,
        name=created.name,
        dataset_id=created.dataset_id,
        total_items=created.total_items,
        completed_items=created.completed_items,
        status=created.status,
        created_at=created.created_at
    )


@router.get("/task/list", response_model=List[AnnotationTaskResponse])
async def list_annotation_tasks(
    skip: int = 0,
    limit: int = 100,
    annotation_service: AnnotationService = Depends(get_annotation_service)
):
    tasks = annotation_service.list_tasks(skip, limit)
    return [
        AnnotationTaskResponse(
            id=t.id,
            name=t.name,
            dataset_id=t.dataset_id,
            total_items=t.total_items,
            completed_items=t.completed_items,
            status=t.status,
            created_at=t.created_at
        ) for t in tasks
    ]


@router.get("/task/{task_id}", response_model=AnnotationTaskResponse)
async def get_annotation_task(
    task_id: int,
    annotation_service: AnnotationService = Depends(get_annotation_service)
):
    task = annotation_service.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return AnnotationTaskResponse(
        id=task.id,
        name=task.name,
        dataset_id=task.dataset_id,
        total_items=task.total_items,
        completed_items=task.completed_items,
        status=task.status,
        created_at=task.created_at
    )


@router.get("/task/{task_id}/progress")
async def get_task_progress(
    task_id: int,
    annotation_service: AnnotationService = Depends(get_annotation_service)
):
    return annotation_service.get_task_progress(task_id)


@router.get("/task/{task_id}/next")
async def get_next_annotation(
    task_id: int,
    annotation_service: AnnotationService = Depends(get_annotation_service)
):
    annotation = annotation_service.get_next_annotation(task_id)
    if not annotation:
        return {"status": "completed", "message": "No more annotations pending"}
    return AnnotationResponse(
        id=annotation.id,
        dataset_id=annotation.dataset_id,
        instruction=annotation.instruction,
        input_text=annotation.input_text,
        output_text=annotation.output_text,
        status=annotation.status,
        annotator=annotation.annotator,
        created_at=annotation.created_at
    )


@router.post("/submit", response_model=AnnotationResponse)
async def submit_annotation(
    annotation_id: int,
    update: AnnotationUpdate,
    annotation_service: AnnotationService = Depends(get_annotation_service)
):
    try:
        annotation = annotation_service.submit_annotation(
            annotation_id=annotation_id,
            output_text=update.output_text,
            annotator=update.annotator
        )
        return AnnotationResponse(
            id=annotation.id,
            dataset_id=annotation.dataset_id,
            instruction=annotation.instruction,
            input_text=annotation.input_text,
            output_text=annotation.output_text,
            status=annotation.status,
            annotator=annotation.annotator,
            created_at=annotation.created_at
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{annotation_id}", response_model=AnnotationResponse)
async def get_annotation(
    annotation_id: int,
    annotation_service: AnnotationService = Depends(get_annotation_service)
):
    annotation = annotation_service.get_annotation(annotation_id)
    if not annotation:
        raise HTTPException(status_code=404, detail="Annotation not found")
    return AnnotationResponse(
        id=annotation.id,
        dataset_id=annotation.dataset_id,
        instruction=annotation.instruction,
        input_text=annotation.input_text,
        output_text=annotation.output_text,
        status=annotation.status,
        annotator=annotation.annotator,
        created_at=annotation.created_at
    )
