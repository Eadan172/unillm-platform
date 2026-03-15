from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.models.database import get_session_maker
from app.models.schemas import ModelLoadRequest, ModelResponse
from app.services.model_service import ModelService
from app.services.inference_service import InferenceService
from app.config import settings

router = APIRouter(prefix="/api/model", tags=["Model Management"])

session_maker = get_session_maker(settings.database.path)

inference_service = None


def get_db():
    db = session_maker()
    try:
        yield db
    finally:
        db.close()


def get_model_service(db: Session = Depends(get_db)) -> ModelService:
    return ModelService(db)


def get_inference_service(db: Session = Depends(get_db)) -> InferenceService:
    global inference_service
    if inference_service is None:
        inference_service = InferenceService(db)
    return inference_service


@router.post("/register", response_model=ModelResponse)
async def register_model(
    name: str,
    model_type: str = "base",
    base_model: str = None,
    model_path: str = None,
    description: str = None,
    model_service: ModelService = Depends(get_model_service)
):
    model = model_service.register_model(
        name=name,
        model_type=model_type,
        base_model=base_model,
        model_path=model_path,
        description=description
    )
    return ModelResponse(
        id=model.id,
        name=model.name,
        model_type=model.model_type,
        base_model=model.base_model,
        is_loaded=model.is_loaded,
        created_at=model.created_at
    )


@router.post("/load")
async def load_model(
    request: ModelLoadRequest,
    model_service: ModelService = Depends(get_model_service),
    inference_svc: InferenceService = Depends(get_inference_service)
):
    model = model_service.get_model_by_name(request.model_name)
    if not model:
        model = model_service.register_model(
            name=request.model_name,
            model_type="base",
            model_path=request.model_path
        )
    
    result = inference_svc.load_model(
        model_name=request.model_name,
        model_path=request.model_path or request.model_name,
        lora_path=request.lora_path
    )
    
    if result["status"] == "success":
        model_service.set_model_loaded(model.id, True)
    
    return result


@router.post("/unload")
async def unload_model(
    inference_svc: InferenceService = Depends(get_inference_service)
):
    return inference_svc.unload_model()


@router.get("/list", response_model=List[ModelResponse])
async def list_models(
    model_type: str = None,
    skip: int = 0,
    limit: int = 100,
    model_service: ModelService = Depends(get_model_service)
):
    models = model_service.list_models(model_type, skip, limit)
    return [
        ModelResponse(
            id=m.id,
            name=m.name,
            model_type=m.model_type,
            base_model=m.base_model,
            is_loaded=m.is_loaded,
            created_at=m.created_at
        ) for m in models
    ]


@router.get("/{model_id}", response_model=ModelResponse)
async def get_model(
    model_id: int,
    model_service: ModelService = Depends(get_model_service)
):
    model = model_service.get_model(model_id)
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    return ModelResponse(
        id=model.id,
        name=model.name,
        model_type=model.model_type,
        base_model=model.base_model,
        is_loaded=model.is_loaded,
        created_at=model.created_at
    )


@router.delete("/{model_id}")
async def delete_model(
    model_id: int,
    model_service: ModelService = Depends(get_model_service)
):
    success = model_service.delete_model(model_id)
    if not success:
        raise HTTPException(status_code=404, detail="Model not found")
    return {"status": "deleted", "model_id": model_id}
