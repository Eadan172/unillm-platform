import os
from typing import List, Optional, Dict, Any
from sqlalchemy.orm import Session
from pathlib import Path

from app.models.database import Model, FinetuneJob
from app.config import settings


class ModelService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.models_path = Path(settings.storage.models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)
        self.loaded_models: Dict[str, Any] = {}

    def register_model(self, name: str, model_type: str = "base",
                       base_model: str = None, model_path: str = None,
                       description: str = None) -> Model:
        model = Model(
            name=name,
            model_type=model_type,
            base_model=base_model,
            model_path=model_path,
            description=description
        )
        self.db.add(model)
        self.db.commit()
        self.db.refresh(model)
        return model

    def get_model(self, model_id: int) -> Optional[Model]:
        return self.db.query(Model).filter(Model.id == model_id).first()

    def get_model_by_name(self, name: str) -> Optional[Model]:
        return self.db.query(Model).filter(Model.name == name).first()

    def list_models(self, model_type: str = None, skip: int = 0, limit: int = 100) -> List[Model]:
        query = self.db.query(Model)
        if model_type:
            query = query.filter(Model.model_type == model_type)
        return query.offset(skip).limit(limit).all()

    def set_model_loaded(self, model_id: int, is_loaded: bool) -> Model:
        model = self.db.query(Model).filter(Model.id == model_id).first()
        if model:
            model.is_loaded = is_loaded
            self.db.commit()
            self.db.refresh(model)
        return model

    def update_lora_path(self, model_id: int, lora_path: str) -> Model:
        model = self.db.query(Model).filter(Model.id == model_id).first()
        if model:
            model.lora_path = lora_path
            model.model_type = "lora"
            self.db.commit()
            self.db.refresh(model)
        return model

    def delete_model(self, model_id: int) -> bool:
        model = self.db.query(Model).filter(Model.id == model_id).first()
        if model:
            self.db.delete(model)
            self.db.commit()
            return True
        return False

    def create_finetune_job(self, model_id: int, dataset_id: int, job_name: str,
                            method: str = "lora", config: Dict = None) -> FinetuneJob:
        job = FinetuneJob(
            model_id=model_id,
            dataset_id=dataset_id,
            job_name=job_name,
            method=method,
            config=config or {}
        )
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_finetune_job(self, job_id: int) -> Optional[FinetuneJob]:
        return self.db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()

    def list_finetune_jobs(self, model_id: int = None, skip: int = 0, limit: int = 100) -> List[FinetuneJob]:
        query = self.db.query(FinetuneJob)
        if model_id:
            query = query.filter(FinetuneJob.model_id == model_id)
        return query.offset(skip).limit(limit).all()

    def update_finetune_status(self, job_id: int, status: str, progress: float = None,
                               output_path: str = None, error_message: str = None) -> FinetuneJob:
        job = self.db.query(FinetuneJob).filter(FinetuneJob.id == job_id).first()
        if job:
            job.status = status
            if progress is not None:
                job.progress = progress
            if output_path:
                job.output_path = output_path
            if error_message:
                job.error_message = error_message
            if status == "running" and not job.started_at:
                from datetime import datetime
                job.started_at = datetime.utcnow()
            if status in ["completed", "failed"]:
                from datetime import datetime
                job.completed_at = datetime.utcnow()
            self.db.commit()
            self.db.refresh(job)
        return job
