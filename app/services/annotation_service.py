from typing import List, Optional
from sqlalchemy.orm import Session
from datetime import datetime

from app.models.database import Annotation, AnnotationTask, Dataset
from app.models.schemas import AnnotationStatus


class AnnotationService:
    def __init__(self, db_session: Session):
        self.db = db_session

    def create_task(self, name: str, dataset_id: int, description: str = None, 
                    annotation_type: str = "text") -> AnnotationTask:
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        task = AnnotationTask(
            name=name,
            dataset_id=dataset_id,
            description=description,
            annotation_type=annotation_type,
            total_items=dataset.total_samples
        )
        self.db.add(task)
        self.db.commit()
        self.db.refresh(task)

        self.db.query(Annotation).filter(
            Annotation.dataset_id == dataset_id
        ).update({"task_id": task.id})
        self.db.commit()

        return task

    def get_task(self, task_id: int) -> Optional[AnnotationTask]:
        return self.db.query(AnnotationTask).filter(AnnotationTask.id == task_id).first()

    def list_tasks(self, skip: int = 0, limit: int = 100) -> List[AnnotationTask]:
        return self.db.query(AnnotationTask).offset(skip).limit(limit).all()

    def get_next_annotation(self, task_id: int) -> Optional[Annotation]:
        return self.db.query(Annotation).filter(
            Annotation.task_id == task_id,
            Annotation.status == "pending"
        ).first()

    def submit_annotation(self, annotation_id: int, output_text: str, 
                          annotator: str = None) -> Annotation:
        annotation = self.db.query(Annotation).filter(Annotation.id == annotation_id).first()
        if not annotation:
            raise ValueError(f"Annotation {annotation_id} not found")

        annotation.output_text = output_text
        annotation.status = AnnotationStatus.COMPLETED.value
        annotation.annotator = annotator
        annotation.updated_at = datetime.utcnow()

        if annotation.task_id:
            task = self.db.query(AnnotationTask).filter(
                AnnotationTask.id == annotation.task_id
            ).first()
            if task:
                completed = self.db.query(Annotation).filter(
                    Annotation.task_id == task.id,
                    Annotation.status == "completed"
                ).count()
                task.completed_items = completed
                if completed >= task.total_items:
                    task.status = "completed"

        self.db.commit()
        self.db.refresh(annotation)
        return annotation

    def get_annotation(self, annotation_id: int) -> Optional[Annotation]:
        return self.db.query(Annotation).filter(Annotation.id == annotation_id).first()

    def list_annotations_by_task(self, task_id: int, status: str = None,
                                  skip: int = 0, limit: int = 100) -> List[Annotation]:
        query = self.db.query(Annotation).filter(Annotation.task_id == task_id)
        if status:
            query = query.filter(Annotation.status == status)
        return query.offset(skip).limit(limit).all()

    def get_task_progress(self, task_id: int) -> dict:
        task = self.db.query(AnnotationTask).filter(AnnotationTask.id == task_id).first()
        if not task:
            raise ValueError(f"Task {task_id} not found")

        total = task.total_items
        completed = task.completed_items
        pending = self.db.query(Annotation).filter(
            Annotation.task_id == task_id,
            Annotation.status == "pending"
        ).count()

        return {
            "task_id": task_id,
            "total": total,
            "completed": completed,
            "pending": pending,
            "progress": round(completed / total * 100, 2) if total > 0 else 0
        }
