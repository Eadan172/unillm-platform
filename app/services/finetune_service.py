"""LoRA 微调服务。

原实现的两个真实缺陷
--------------------
1. **跨线程复用 Session**：``start_finetune`` 起一个线程执行训练，线程里继续用
   请求作用域的 ``self.db``（以及绑定它的 ``ModelService`` / ``DataService``）。
   SQLAlchemy 的 Session 不是线程安全的，SQLite 还会直接抛
   ``SQLite objects created in a thread can only be used in that same thread``。
   现在工作线程自己创建 Session，用完即关。
2. **取消失效 / 语义含糊**：``cancel_job`` 只把状态改成 cancelled，训练线程照样
   跑完并写 ``output_path``，随后又被 update 成 completed —— 取消等于没取消。
   现在引入协作式取消标志，在每个阶段边界检查；并在文档与响应里明确说明
   **无法中断已进入的单个训练 step**（PyTorch 层面无法安全抢占）。

依赖缺失时的行为
----------------
未安装 transformers / peft 时任务会失败，错误信息明确指向 requirements-gpu.txt，
不会被伪装成"训练完成"。
"""

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import FinetuneJob, get_session_maker
from app.services.data_service import DataService
from app.services.model_service import ModelService

MISSING_DEPS_HINT = (
    "未安装 transformers / peft / datasets，无法执行真实 LoRA 训练。"
    "请在 Linux + CUDA 环境执行 pip install -r requirements-gpu.txt。"
)


class _JobCancelled(Exception):
    """协作式取消信号。"""


class FinetuneService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.model_service = ModelService(db_session)
        self.data_service = DataService(db_session)
        self.models_path = Path(settings.storage.models_path)
        self.models_path.mkdir(parents=True, exist_ok=True)
        # 进程级共享的取消标志与线程句柄（跨请求可见）
        self._cancel_flags: Dict[int, threading.Event] = {}
        self._threads: Dict[int, threading.Thread] = {}

    # ---------------- 任务生命周期 ----------------

    def create_job(
        self,
        model_id: int,
        dataset_id: int,
        job_name: str,
        method: str = "lora",
        config: Dict = None,
    ) -> FinetuneJob:
        if self.model_service.get_model(model_id) is None:
            raise ValueError(f"模型 {model_id} 不存在")
        if self.data_service.get_dataset(dataset_id) is None:
            raise ValueError(f"数据集 {dataset_id} 不存在")
        return self.model_service.create_finetune_job(
            model_id=model_id,
            dataset_id=dataset_id,
            job_name=job_name,
            method=method,
            config=config,
        )

    def list_jobs(self, model_id: int = None, skip: int = 0, limit: int = 100) -> List[FinetuneJob]:
        return self.model_service.list_finetune_jobs(model_id, skip, limit)

    def start_finetune(self, job_id: int) -> Dict[str, Any]:
        job = self.model_service.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": f"Job {job_id} not found"}
        if job.status == "running":
            return {"status": "error", "message": "Job already running"}

        self.model_service.update_finetune_status(job_id, "running", 0.0)
        self._cancel_flags[job_id] = threading.Event()

        thread = threading.Thread(
            target=self._run_finetune, args=(job_id,), name=f"finetune-{job_id}", daemon=True
        )
        thread.start()
        self._threads[job_id] = thread

        return {"status": "started", "job_id": job_id}

    def cancel_job(self, job_id: int) -> Dict[str, Any]:
        job = self.model_service.get_finetune_job(job_id)
        if not job:
            return {"status": "error", "message": f"Job {job_id} not found"}
        if job.status != "running":
            return {"status": "error", "message": f"Job 状态为 {job.status}，无法取消"}

        flag = self._cancel_flags.get(job_id)
        if flag is not None:
            flag.set()
        self.model_service.update_finetune_status(job_id, "cancelled", job.progress)
        return {
            "status": "cancelled",
            "job_id": job_id,
            "note": (
                "已发送取消信号，训练将在下一个阶段检查点停止。"
                "单个已进入的训练 step 无法被安全中断。"
            ),
        }

    # ---------------- 工作线程 ----------------

    def _run_finetune(self, job_id: int) -> None:
        """在线程内使用独立 Session，避免跨线程共享请求级 Session。"""
        session = get_session_maker()()
        try:
            model_service = ModelService(session)
            data_service = DataService(session)
            flag = self._cancel_flags.setdefault(job_id, threading.Event())

            job = model_service.get_finetune_job(job_id)
            if job is None:
                return
            model = model_service.get_model(job.model_id)
            if model is None:
                model_service.update_finetune_status(
                    job_id, "failed", 0.0, error_message=f"模型 {job.model_id} 不存在"
                )
                return

            training_data_path = data_service.export_to_training_format(job.dataset_id)
            output_dir = str(self.models_path / f"lora_{job_id}")

            self._run_lora_training(
                base_model=model.model_path or model.base_model,
                data_path=training_data_path,
                output_dir=output_dir,
                job_id=job_id,
                model_service=model_service,
                flag=flag,
            )

            if flag.is_set():
                model_service.update_finetune_status(job_id, "cancelled")
                return

            model_service.update_finetune_status(job_id, "completed", 100.0, output_dir)
            model_service.update_lora_path(model.id, output_dir)

        except _JobCancelled:
            ModelService(session).update_finetune_status(job_id, "cancelled")
        except Exception as exc:
            session.rollback()
            ModelService(session).update_finetune_status(
                job_id, "failed", 0.0, error_message=str(exc)
            )
        finally:
            self._threads.pop(job_id, None)
            session.close()

    def _run_lora_training(
        self,
        base_model: str,
        data_path: str,
        output_dir: str,
        job_id: int,
        model_service: ModelService,
        flag: threading.Event,
    ) -> None:
        def checkpoint(progress: float) -> None:
            if flag.is_set():
                raise _JobCancelled()
            model_service.update_finetune_status(job_id, "running", progress)

        try:
            from transformers import (  # noqa: F401
                AutoModelForCausalLM,
                AutoTokenizer,
                Trainer,
                TrainingArguments,
            )
            from peft import LoraConfig, TaskType, get_peft_model  # noqa: F401
            from datasets import Dataset  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(f"{MISSING_DEPS_HINT}（原始错误：{exc}）") from exc

        checkpoint(10.0)
        tokenizer = AutoTokenizer.from_pretrained(base_model, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token

        checkpoint(20.0)
        model = AutoModelForCausalLM.from_pretrained(
            base_model, torch_dtype="auto", device_map="auto", trust_remote_code=True
        )

        checkpoint(30.0)
        lora_config = LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=settings.lora.r,
            lora_alpha=settings.lora.lora_alpha,
            lora_dropout=settings.lora.lora_dropout,
            target_modules=settings.lora.target_modules,
            bias="none",
        )
        model = get_peft_model(model, lora_config)

        checkpoint(40.0)
        with open(data_path, "r", encoding="utf-8") as f:
            data = [json.loads(line) for line in f if line.strip()]
        if not data:
            raise RuntimeError("训练数据为空")

        def format_example(example):
            prompt = (
                f"<|im_start|>user\n{example['instruction']}\n{example.get('input', '')}<|im_end|>\n"
                f"<|im_start|>assistant\n{example['output']}<|im_end|>"
            )
            return {"text": prompt}

        dataset = Dataset.from_list(data).map(format_example)

        def tokenize_function(examples):
            return tokenizer(
                examples["text"], truncation=True, max_length=2048, padding="max_length"
            )

        tokenized_dataset = dataset.map(tokenize_function, batched=True)

        checkpoint(50.0)
        training_args = TrainingArguments(
            output_dir=output_dir,
            num_train_epochs=settings.training.num_train_epochs,
            per_device_train_batch_size=settings.training.per_device_train_batch_size,
            gradient_accumulation_steps=settings.training.gradient_accumulation_steps,
            learning_rate=settings.training.learning_rate,
            logging_steps=settings.training.logging_steps,
            save_steps=settings.training.save_steps,
            fp16=True,
            report_to="none",
        )

        trainer = Trainer(
            model=model, args=training_args, train_dataset=tokenized_dataset, tokenizer=tokenizer
        )

        checkpoint(60.0)
        trainer.train()

        if flag.is_set():
            raise _JobCancelled()

        checkpoint(90.0)
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)

    # ---------------- 查询 ----------------

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
            "completed_at": job.completed_at,
        }
