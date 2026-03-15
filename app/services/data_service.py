import os
import json
import pandas as pd
from pathlib import Path
from typing import List, Optional
from sqlalchemy.orm import Session

from app.models.database import Dataset, Annotation, init_database
from app.config import settings


class DataService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.storage_path = Path(settings.storage.datasets_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def create_dataset(self, name: str, description: str = None, source_type: str = "file") -> Dataset:
        dataset = Dataset(
            name=name,
            description=description,
            source_type=source_type
        )
        self.db.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def import_data_from_file(self, dataset_id: int, file_path: str, file_type: str = "json") -> int:
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        if file_type == "json":
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        elif file_type == "jsonl":
            data = []
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))
        elif file_type == "csv":
            df = pd.read_csv(file_path)
            data = df.to_dict("records")
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        count = 0
        for item in data:
            instruction = item.get("instruction", item.get("question", ""))
            input_text = item.get("input", item.get("context", ""))
            output_text = item.get("output", item.get("answer", ""))

            annotation = Annotation(
                dataset_id=dataset_id,
                instruction=instruction,
                input_text=input_text,
                output_text=output_text,
                raw_data=item,
                status="pending"
            )
            self.db.add(annotation)
            count += 1

        dataset.total_samples = count
        dataset.file_path = file_path
        self.db.commit()

        dest_path = self.storage_path / f"dataset_{dataset_id}.json"
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return count

    def get_dataset(self, dataset_id: int) -> Optional[Dataset]:
        return self.db.query(Dataset).filter(Dataset.id == dataset_id).first()

    def list_datasets(self, skip: int = 0, limit: int = 100) -> List[Dataset]:
        return self.db.query(Dataset).offset(skip).limit(limit).all()

    def delete_dataset(self, dataset_id: int) -> bool:
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if dataset:
            self.db.query(Annotation).filter(Annotation.dataset_id == dataset_id).delete()
            self.db.delete(dataset)
            self.db.commit()
            return True
        return False

    def get_annotations(self, dataset_id: int, skip: int = 0, limit: int = 100) -> List[Annotation]:
        return self.db.query(Annotation).filter(
            Annotation.dataset_id == dataset_id
        ).offset(skip).limit(limit).all()

    def export_to_training_format(self, dataset_id: int, output_path: str = None) -> str:
        annotations = self.db.query(Annotation).filter(
            Annotation.dataset_id == dataset_id,
            Annotation.status == "completed"
        ).all()

        training_data = []
        for ann in annotations:
            training_data.append({
                "instruction": ann.instruction,
                "input": ann.input_text or "",
                "output": ann.output_text
            })

        if output_path is None:
            output_path = str(self.storage_path / f"training_data_{dataset_id}.jsonl")

        with open(output_path, "w", encoding="utf-8") as f:
            for item in training_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return output_path
