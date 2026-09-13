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
from app.core.values import has_visible_content
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
    # 空答案校验：只有空白字符的答案视为无效，拒绝提交（前端也会禁用按钮双保险）。
    #
    # 统一走 has_visible_content：此处**未构成缺陷**——AnnotationUpdate.output_text
    # 类型标注为 ``str``，Pydantic v2 在入口就把 JSON 数字 0 / 0.0 / false 判为
    # ValidationError（422），根本到不了这一行；能到达的值必是字符串，因此
    # 字符串 "0" 与旧写法一样被正确放行。这里只做写法收敛，消除散落的 ``or ""``
    # 判空形态，避免列类型或 schema 变化后重新踩坑。
    if not has_visible_content(update.output_text):
        raise HTTPException(status_code=400, detail="标注答案不能为空")
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
