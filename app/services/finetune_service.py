import os
import json
import threading
from typing import Dict, Any, Optional
from pathlib import Path
from sqlalchemy.orm import Session

from app.models.database import FinetuneJob
from app.services.model_service import ModelService
from app.services.data_service import DataService
from app.config import settings


class FinetuneService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.model_service = ModelService(db_session)
        self.data_service = DataService(db_session)
        self.models_path = Path(settings.storage.models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)
        self.active_jobs: Dict[int, threading.Thread] = {}

    def start_finetune(self, job_id: int) -> Dict[str, Any]:
        job = self.model_service.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": f"Job {job_id} not found"}

        if job.status == "running":
            return {"status": "error", "message": "Job already running"}

        self.model_service.update_finetune_status(job_id, "running", 0.0)

        thread = threading.Thread(target=self._run_finetune, args=(job_id,))
        thread.start()
        self.active_jobs[job_id] = thread

        return {"status": "started", "job_id": job_id}

    def _run_finetune(self, job_id: int):
        try:
            job = self.model_service.get_finetune_job(job_id)
            model = self.model_service.get_model(job.model_id)

            training_data_path = self.data_service.export_to_training_format(job.dataset_id)
            output_dir = str(self.models_path / f"lora_{job_id}")

            self._run_lora_training(
                base_model=model.model_path or model.base_model,
                data_path=training_data_path,
                output_dir=output_dir,
                job_id=job_id
            )

            self.model_service.update_finetune_status(job_id, "completed", 100.0, output_dir)
            self.model_service.update_lora_path(model.id, output_dir)

        except Exception as e:
            self.model_service.update_finetune_status(job_id, "failed", 0.0, error_message=str(e))

    def _run_lora_training(self, base_model: str, data_path: str, 
                           output_dir: str, job_id: int):
        try:
            from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
            from peft import LoraConfig, get_peft_model, TaskType
            from datasets import Dataset
            
            self.model_service.update_finetune_status(job_id, "running", 10.0)

            tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
            if tokenizer.pad_token is None:
                tokenizer.pad_token = tokenizer.eos_token

            self.model_service.update_finetune_status(job_id, "running", 20.0)

            model = AutoModelForCausalLM.from_pretrained(
                base_model,
                torch_dtype="auto",
                device_map="auto",
                trust_remote_code=True
            )

            self.model_service.update_finetune_status(job_id, "running", 30.0)

            lora_config = LoraConfig(
                task_type=TaskType.CAUSAL_LM,
                r=settings.lora.r,
                lora_alpha=settings.lora.lora_alpha,
                lora_dropout=settings.lora.lora_dropout,
                target_modules=settings.lora.target_modules,
                bias="none"
            )
            model = get_peft_model(model, lora_config)

            self.model_service.update_finetune_status(job_id, "running", 40.0)

            with open(data_path, "r", encoding="utf-8") as f:
                data = [json.loads(line) for line in f if line.strip()]

            def format_example(example):
                prompt = f"<|im_start|>user\n{example['instruction']}\n{example.get('input', '')}<|im_end|>\n<|im_start|>assistant\n{example['output']}<|im_end|>"
                return {"text": prompt}

            dataset = Dataset.from_list(data)
            dataset = dataset.map(format_example)

            def tokenize_function(examples):
                return tokenizer(examples["text"], truncation=True, max_length=2048, padding="max_length")

            tokenized_dataset = dataset.map(tokenize_function, batched=True)

            self.model_service.update_finetune_status(job_id, "running", 50.0)

            training_args = TrainingArguments(
                output_dir=output_dir,
                num_train_epochs=settings.training.num_train_epochs,
                per_device_train_batch_size=settings.training.per_device_train_batch_size,
                gradient_accumulation_steps=settings.training.gradient_accumulation_steps,
                learning_rate=settings.training.learning_rate,
                logging_steps=settings.training.logging_steps,
                save_steps=settings.training.save_steps,
                fp16=True,
                report_to="none"
            )

            trainer = Trainer(
                model=model,
                args=training_args,
                train_dataset=tokenized_dataset,
                tokenizer=tokenizer
            )

            self.model_service.update_finetune_status(job_id, "running", 60.0)
            trainer.train()

            self.model_service.update_finetune_status(job_id, "running", 90.0)
            model.save_pretrained(output_dir)
            tokenizer.save_pretrained(output_dir)

        except ImportError as e:
            raise RuntimeError(f"Required libraries not installed: {e}")
        except Exception as e:
            raise RuntimeError(f"Training failed: {e}")

    def get_job_status(self, job_id: int) -> Optional[Dict[str, Any]]:
        job = self.model_service.get_finetune_job(job_id)
        if not job:
            return None
        return {
            "job_id": job.id,
            "model_id": job.model_id,
            "dataset_id": job.dataset_id,
            "job_name": job.job_name,
            "method": job.method,
            "status": job.status,
            "progress": job.progress,
            "output_path": job.output_path,
            "error_message": job.error_message,
            "started_at": job.started_at,
            "completed_at": job.completed_at
        }

    def cancel_job(self, job_id: int) -> Dict[str, Any]:
        job = self.model_service.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": f"Job {job_id} not found"}

        if job.status != "running":
            return {"status": "error", "message": "Job is not running"}

        self.model_service.update_finetune_status(job_id, "cancelled")
        return {"status": "cancelled", "job_id": job_id}
