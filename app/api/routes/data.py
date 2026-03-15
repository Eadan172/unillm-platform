from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from typing import List
import os
import shutil
from pathlib import Path

from app.models.database import get_session_maker
from app.models.schemas import DatasetCreate, DatasetResponse
from app.services.data_service import DataService
from app.config import settings

router = APIRouter(prefix="/api/data", tags=["Data Management"])

session_maker = get_session_maker(settings.database.path)


def get_db():
    db = session_maker()
    try:
        yield db
    finally:
        db.close()


def get_data_service(db: Session = Depends(get_db)) -> DataService:
    return DataService(db)


@router.post("/import", response_model=DatasetResponse)
async def import_dataset(
    name: str,
    file: UploadFile = File(...),
    description: str = None,
    data_service: DataService = Depends(get_data_service)
):
    storage_path = Path(settings.storage.datasets_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    
    file_path = storage_path / file.filename
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    
    dataset = data_service.create_dataset(name, description)
    
    file_type = file.filename.split(".")[-1].lower()
    if file_type not in ["json", "jsonl", "csv"]:
        raise HTTPException(status_code=400, detail="Unsupported file type. Use json, jsonl, or csv.")
    
    count = data_service.import_data_from_file(dataset.id, str(file_path), file_type)
    
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        source_type=dataset.source_type,
        total_samples=count,
        created_at=dataset.created_at
    )


@router.post("/create", response_model=DatasetResponse)
async def create_dataset(
    dataset: DatasetCreate,
    data_service: DataService = Depends(get_data_service)
):
    created = data_service.create_dataset(
        name=dataset.name,
        description=dataset.description,
        source_type=dataset.source_type.value
    )
    return DatasetResponse(
        id=created.id,
        name=created.name,
        description=created.description,
        source_type=created.source_type,
        total_samples=created.total_samples,
        created_at=created.created_at
    )


@router.get("/list", response_model=List[DatasetResponse])
async def list_datasets(
    skip: int = 0,
    limit: int = 100,
    data_service: DataService = Depends(get_data_service)
):
    datasets = data_service.list_datasets(skip, limit)
    return [
        DatasetResponse(
            id=d.id,
            name=d.name,
            description=d.description,
            source_type=d.source_type,
            total_samples=d.total_samples,
            created_at=d.created_at
        ) for d in datasets
    ]


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service)
):
    dataset = data_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        source_type=dataset.source_type,
        total_samples=dataset.total_samples,
        created_at=dataset.created_at
    )


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service)
):
    success = data_service.delete_dataset(dataset_id)
    if not success:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "deleted", "dataset_id": dataset_id}


@router.get("/{dataset_id}/export")
async def export_training_data(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service)
):
    output_path = data_service.export_to_training_format(dataset_id)
    return {"status": "success", "output_path": output_path}
