"""评测服务：真实可复现的指标，不再返回编造数值。

原实现的问题
------------
1. ``run_evaluation`` 默认 ``test_data=None``，而内部 ``test_data[:100]`` 会抛
   ``TypeError``；每个指标函数都把这个异常吞掉，返回 ``{"mock_value": 15.5}``，
   评测状态却仍被标成 ``completed``。
2. ``_evaluate_accuracy`` 实际逻辑是"只要参考答案非空就算答对"，永远接近 1.0。
3. ``_evaluate_latency`` 测的是 ``time.sleep(0.01)`` 的耗时，与模型无关。

现在改为：真实调用当前推理后端取预测 -> 与参考答案比对 -> 计算指标。
缺数据就诚实报错（HTTP 400），缺能力（如未装 torch）就返回
``available: false`` 并说明如何启用，绝不给出看起来像真结果的假数字。

指标口径
--------
- ``exact_match``：归一化（去空白、转小写、去中英文标点）后完全一致的比例。
- ``token_f1``   ：按**字符**切分计算 F1，对中文与英文都稳定；
                   逐样本计算后取宏平均。空白切分对中文不适用，故不用。
- ``latency``    ：逐样本实测端到端推理耗时（含后端调用），给 min/avg/p50/p95。
- ``perplexity`` ：需 torch + transformers 才能真正计算；未安装时返回
                   ``available: false``，不填占位数字。
"""

import re
import time
from collections import Counter
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.config import settings
from app.core.values import has_visible_content
from app.models.database import Evaluation, utcnow
from app.services.data_service import DataService
from app.services.inference_service import InferenceService
from app.services.model_service import ModelService

_PUNCT_RE = re.compile(r"[\s\u3000!-/:-@\[-`{-~\u3001-\u303f\uff01-\uff5e\u2018\u2019\u201c\u201d]+")


def normalize_text(text: Optional[str]) -> str:
    if not text:
        return ""
    return _PUNCT_RE.sub("", text).lower()


def char_f1(prediction: str, reference: str) -> float:
    """字符级 F1。两边都为空视为 1.0（完全一致的空答案）。"""
    pred = normalize_text(prediction)
    ref = normalize_text(reference)
    if not pred and not ref:
        return 1.0
    if not pred or not ref:
        return 0.0
    pred_counter = Counter(pred)
    ref_counter = Counter(ref)
    overlap = sum((pred_counter & ref_counter).values())
    if overlap == 0:
        return 0.0
    precision = overlap / len(pred)
    recall = overlap / len(ref)
    return 2 * precision * recall / (precision + recall)


def percentile(sorted_values: List[float], ratio: float) -> float:
    if not sorted_values:
        return 0.0
    idx = min(int(round((len(sorted_values) - 1) * ratio)), len(sorted_values) - 1)
    return sorted_values[idx]


class EvaluateService:
    def __init__(self, db_session: Session, inference_service: Optional[InferenceService] = None):
        self.db = db_session
        self.model_service = ModelService(db_session)
        self.data_service = DataService(db_session)
        self.inference_service = inference_service or InferenceService()

    # ---------------- CRUD ----------------

    def create_evaluation(
        self,
        model_id: int,
        eval_name: str,
        dataset_id: int = None,
        metrics: List[str] = None,
    ) -> Evaluation:
        record = Evaluation(
            model_id=model_id,
            dataset_id=dataset_id,
            eval_name=eval_name,
            metrics={"requested": metrics or settings.evaluation.metrics},
            status="pending",
        )
        self.db.add(record)
        self.db.commit()
        self.db.refresh(record)
        return record

    def get_evaluation(self, eval_id: int) -> Optional[Evaluation]:
        return self.db.query(Evaluation).filter(Evaluation.id == eval_id).first()

    def list_evaluations(
        self, model_id: int = None, skip: int = 0, limit: int = 100
    ) -> List[Evaluation]:
        query = self.db.query(Evaluation)
        if model_id:
            query = query.filter(Evaluation.model_id == model_id)
        return query.offset(skip).limit(limit).all()

    # ---------------- 执行 ----------------

    def run_evaluation(
        self, eval_id: int, test_data: List[Dict] = None
    ) -> Dict[str, Any]:
        record = self.get_evaluation(eval_id)
        if not record:
            return {"status": "error", "message": f"Evaluation {eval_id} not found"}

        try:
            samples = self.resolve_samples(record, test_data)
        except ValueError as exc:
            record.status = "failed"
            record.results = {"error": str(exc)}
            self.db.commit()
            return {"status": "error", "message": str(exc)}

        record.status = "running"
        self.db.commit()

        try:
            predictions = self._predict(samples)

            results: Dict[str, Any] = {
                "sample_count": len(samples),
                "backend": self.inference_service.backend_name,
                "backend_is_real_model": self.inference_service.is_real_backend,
                "metric_definitions": {
                    "exact_match": "归一化后完全一致的比例（宏平均）",
                    "token_f1": "字符级 F1 的宏平均（适配中英文）",
                    "latency": "逐样本实测端到端推理耗时（毫秒）",
                    "perplexity": "需 torch+transformers，未安装则 available=false",
                },
            }

            requested = (record.metrics or {}).get("requested", []) or []
            # 兼容旧配置里的 "accuracy"：映射到 exact_match
            wants_em = any(m in requested for m in ("accuracy", "exact_match"))
            wants_f1 = any(m in requested for m in ("accuracy", "f1", "token_f1", "rouge"))
            wants_latency = "latency" in requested
            wants_ppl = "perplexity" in requested

            if wants_em:
                results["exact_match"] = self._exact_match(predictions)
            if wants_f1:
                results["token_f1"] = self._token_f1(predictions)
            if wants_latency:
                results["latency"] = self._latency(predictions)
            if wants_ppl:
                results["perplexity"] = self.compute_perplexity(record.model_id, samples)

            record.status = "completed"
            record.results = results
            record.completed_at = utcnow()
            self.db.commit()
            return {"status": "completed", "results": results}

        except Exception as exc:  # 后端异常等
            record.status = "failed"
            record.results = {"error": str(exc)}
            self.db.commit()
            return {"status": "error", "message": str(exc)}

    def resolve_samples(
        self, record: Evaluation, test_data: Optional[List[Dict]] = None
    ) -> List[Dict[str, str]]:
        """取得评测样本。缺数据时抛 ValueError，而不是悄悄用假数据。"""
        raw: List[Dict] = []

        if test_data:
            raw = [item for item in test_data if isinstance(item, dict)]
        elif record.dataset_id:
            annotations = self.data_service.get_annotations(record.dataset_id, limit=10000)
            raw = [
                {
                    "instruction": ann.instruction,
                    # 取默认值语义（无值给空串），不是判空语义，保持原样。
                    # 读 TEXT 列时 0 落库为 '0'（str），无 falsy 短路风险。
                    "input": ann.input_text or "",
                    "output": ann.output_text or "",
                }
                for ann in annotations
            ]

        samples = []
        for item in raw:
            # 显式区分「键不存在」与「值是 0」：本案例的情感标签就是 0/1，
            # 旧写法 ``item.get("output") or item.get("answer") or ""`` 中
            # ``0 or ...`` 会短路成 ""，把 output=0 的样本静默 continue 掉——
            # 评测于是跑在一个被悄悄改小的测试集上，样本数变少却无人知晓，
            # 指标数字看起来完全正常。这是「不报错、数字合理、结论错误」。
            raw_reference = item.get("output")
            if raw_reference is None:
                raw_reference = item.get("answer")
            if not has_visible_content(raw_reference):
                continue  # 真的没有参考答案的样本才无法参与指标计算
            samples.append(
                {
                    "prompt": self.build_prompt(item),
                    "reference": str(raw_reference),
                }
            )

        if not samples:
            raise ValueError(
                "没有可用的评测数据：请在请求体传入 test_data，"
                "或为该评测指定含有参考答案（output/answer）的 dataset_id。"
            )

        return samples[: settings.evaluation.max_samples]

    @staticmethod
    def build_prompt(item: Dict) -> str:
        # 回退只在**键缺失 / 值为 None** 时发生。不要写成
        # ``item.get("instruction") or item.get("question") or ""``——``0 or ...``
        # 会把合法的 instruction=0 替换成空串，与导入侧「数值 0 是真实内容」
        # 的语义打架（导入侧已允许 {"instruction": 0} 入库）。
        instruction = item.get("instruction")
        if instruction is None:
            instruction = item.get("question")
        extra = item.get("input")
        if extra is None:
            extra = item.get("context")
        return (
            f"<|im_start|>user\n{'' if instruction is None else instruction}\n"
            f"{'' if extra is None else extra}<|im_end|>\n"
            f"<|im_start|>assistant\n"
        )

    def _predict(self, samples: List[Dict[str, str]]) -> List[Dict[str, Any]]:
        predictions = []
        for sample in samples:
            start = time.perf_counter()
            generated = self.inference_service.generate(sample["prompt"])
            elapsed_ms = (time.perf_counter() - start) * 1000
            predictions.append(
                {
                    "prediction": generated["text"],
                    "reference": sample["reference"],
                    "latency_ms": round(elapsed_ms, 3),
                }
            )
        return predictions

    # ---------------- 指标 ----------------

    @staticmethod
    def _exact_match(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        hits = sum(
            1
            for p in predictions
            if normalize_text(p["prediction"]) == normalize_text(p["reference"])
        )
        total = len(predictions)
        return {
            "value": round(hits / total, 4) if total else 0.0,
            "correct": hits,
            "total": total,
        }

    @staticmethod
    def _token_f1(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        scores = [char_f1(p["prediction"], p["reference"]) for p in predictions]
        total = len(scores)
        return {
            "value": round(sum(scores) / total, 4) if total else 0.0,
            "unit": "char",
            "total": total,
        }

    @staticmethod
    def _latency(predictions: List[Dict[str, Any]]) -> Dict[str, Any]:
        latencies = sorted(p["latency_ms"] for p in predictions)
        if not latencies:
            return {"avg_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "samples": 0}
        return {
            "avg_ms": round(sum(latencies) / len(latencies), 3),
            "min_ms": round(latencies[0], 3),
            "max_ms": round(latencies[-1], 3),
            "p50_ms": round(percentile(latencies, 0.50), 3),
            "p95_ms": round(percentile(latencies, 0.95), 3),
            "samples": len(latencies),
        }

    def compute_perplexity(
        self, model_id: int, samples: List[Dict[str, str]]
    ) -> Dict[str, Any]:
        """真实困惑度。缺 torch/transformers 或权重时如实说明，不填占位值。"""
        try:
            import torch  # noqa: F401
            from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: F401
        except ImportError:
            return {
                "available": False,
                "reason": "未安装 torch / transformers",
                "how_to_enable": "pip install -r requirements-gpu.txt（需 Linux + CUDA）",
            }

        model_record = self.model_service.get_model(model_id)
        if model_record is None:
            return {"available": False, "reason": f"模型 {model_id} 不存在"}

        model_path = (
            model_record.lora_path or model_record.model_path or model_record.base_model
        )
        if not model_path:
            return {"available": False, "reason": "该模型记录没有可用的本地权重路径"}

        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        try:
            tokenizer = AutoTokenizer.from_pretrained(model_path, trust_remote_code=True)
            model = AutoModelForCausalLM.from_pretrained(
                model_path, torch_dtype="auto", device_map="auto", trust_remote_code=True
            )
        except Exception as exc:
            return {
                "available": False,
                "reason": f"权重加载失败：{exc}",
                "model_path": model_path,
            }

        total_loss = 0.0
        total_tokens = 0
        with torch.no_grad():
            for sample in samples:
                text = f"{sample['prompt']}{sample['reference']}"
                inputs = tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
                inputs = {k: v.to(model.device) for k, v in inputs.items()}
                outputs = model(**inputs, labels=inputs["input_ids"])
                n_tokens = inputs["input_ids"].size(1)
                total_loss += outputs.loss.item() * n_tokens
                total_tokens += n_tokens

        if total_tokens == 0:
            return {"available": False, "reason": "样本 token 数为 0"}

        value = float(torch.exp(torch.tensor(total_loss / total_tokens)).item())
        return {
            "available": True,
            "value": round(value, 4),
            "tokens": total_tokens,
            "model_path": model_path,
        }

    # ---------------- 汇总 ----------------

    def get_evaluation_summary(self, eval_id: int) -> Dict[str, Any]:
        record = self.get_evaluation(eval_id)
        if not record:
            return {"error": f"Evaluation {eval_id} not found"}

        return {
            "eval_id": record.id,
            "model_id": record.model_id,
            "dataset_id": record.dataset_id,
            "eval_name": record.eval_name,
            "status": record.status,
            "metrics": record.metrics,
            "results": record.results,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "completed_at": record.completed_at.isoformat() if record.completed_at else None,
        }
