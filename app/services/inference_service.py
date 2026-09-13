"""推理服务：可插拔后端 + 诚实降级。

后端选择
--------
1. 安装了 vLLM 且模型加载成功      -> ``backend="vllm"``，真实推理。
2. 未安装 vLLM / 加载失败          -> ``backend="mock"``，返回**确定性**占位文本。

为什么要有 mock 后端
--------------------
vLLM 只在 Linux + CUDA 上可用，Windows 装不上。原实现在这种情况下直接返回
``{"status": "error", "message": "vLLM not installed, using mock mode"}``
——消息里说"使用 mock 模式"，实际却走 HTTP 200 返回错误体，且 mock 文本形如
``[Mock Response] Model not loaded. Prompt was: ...``，调用方无法与真实输出区分。

现在把降级做成显式的：响应带 ``backend`` 字段，占位文本以 ``[MOCK]`` 开头并附带
prompt 哈希，任何调用方都能一眼识别这不是模型输出。全部占位内容由 prompt 决定，
同一 prompt 永远得到同一结果，可被测试断言。
"""

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional

from app.config import settings
from app.models.database import InferenceLog, get_session_maker

MOCK_MARKER = "[MOCK]"


class MockBackend:
    """确定性占位后端。不是模型，输出必须可被识别。"""

    name = "mock"
    is_real = False

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        digest = hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:12]
        # 取 prompt 尾部作为可读线索，便于人工核对请求确实被收到
        tail = " ".join(prompt.split())[-160:]
        return (
            f"{MOCK_MARKER} vLLM 后端不可用，以下为确定性占位文本，非模型输出。"
            f"prompt_sha1={digest} prompt_tail=...{tail}"
        )


class ScriptedBackend:
    """测试用后端：按顺序返回预设答案。

    让"评测指标是否算对"可以被确定性验证，而不依赖任何模型。
    """

    name = "scripted"
    is_real = False

    def __init__(self, responses: List[str]):
        self.responses = list(responses)
        self.calls: List[str] = []

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        self.calls.append(prompt)
        if not self.responses:
            return ""
        index = min(len(self.calls) - 1, len(self.responses) - 1)
        return self.responses[index]


class VLLMBackend:
    """真实 vLLM 后端。"""

    name = "vllm"
    is_real = True

    def __init__(self, engine: Any):
        self.engine = engine

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> str:
        from vllm import SamplingParams

        sampling_params = SamplingParams(
            max_tokens=max_tokens, temperature=temperature, top_p=top_p
        )
        outputs = self.engine.generate([prompt], sampling_params)
        return outputs[0].outputs[0].text


class InferenceService:
    def __init__(self, db_session=None):
        # 保留参数以兼容旧调用；日志统一走短生命周期会话
        self.db = db_session
        self.backend: Any = MockBackend()
        self.current_model: Optional[str] = None
        self.load_error: Optional[str] = None

    # ---------------- 后端管理 ----------------

    @property
    def backend_name(self) -> str:
        return self.backend.name

    @property
    def is_real_backend(self) -> bool:
        return bool(getattr(self.backend, "is_real", False))

    def set_backend(self, backend: Any) -> str:
        """注入自定义后端（测试 / 自研引擎）。"""
        self.backend = backend
        return self.backend.name

    def load_model(
        self,
        model_name: str,
        model_path: Optional[str] = None,
        lora_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """尝试加载真实模型；不可用时显式降级，绝不谎报成功。"""
        actual_path = model_path or model_name

        try:
            from vllm import LLM  # noqa: F401
        except ImportError:
            self.backend = MockBackend()
            self.current_model = model_name
            self.load_error = "vllm-not-installed"
            return {
                "status": "degraded",
                "model": model_name,
                "backend": self.backend_name,
                "degraded": True,
                "reason": (
                    "未安装 vLLM，已切换到确定性 mock 后端（占位输出，非模型输出）。"
                    "如需真实推理：Linux + CUDA 环境执行 "
                    "pip install -r requirements-gpu.txt"
                ),
            }

        try:
            from vllm import LLM

            engine = LLM(
                model=actual_path,
                tensor_parallel_size=settings.model.tensor_parallel_size,
                gpu_memory_utilization=settings.model.gpu_memory_utilization,
                max_model_len=settings.model.max_model_len,
                trust_remote_code=True,
            )
        except Exception as exc:  # 显存不足 / 路径错误 / 权重损坏
            self.backend = MockBackend()
            self.current_model = model_name
            self.load_error = str(exc)
            return {
                "status": "degraded",
                "model": model_name,
                "backend": self.backend_name,
                "degraded": True,
                "reason": f"vLLM 加载失败，已切换到 mock 后端：{exc}",
            }

        self.backend = VLLMBackend(engine)
        self.current_model = model_name
        self.load_error = None
        return {
            "status": "success",
            "model": model_name,
            "backend": self.backend_name,
            "degraded": False,
        }

    def unload_model(self) -> Dict[str, Any]:
        self.backend = MockBackend()
        self.current_model = None
        self.load_error = None
        return {"status": "success", "backend": self.backend_name}

    def describe(self) -> Dict[str, Any]:
        return {
            "backend": self.backend_name,
            "is_real_model": self.is_real_backend,
            "current_model": self.current_model,
            "load_error": self.load_error,
        }

    # ---------------- 推理 ----------------

    def generate(
        self,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        start = time.perf_counter()
        text = self.backend.generate(prompt, max_tokens, temperature, top_p)
        latency_ms = (time.perf_counter() - start) * 1000

        # 注意：这里是空白切分的近似 token 数，非分词器精确计数
        tokens_used = len(prompt.split()) + len(text.split())

        self._log("completion", prompt, text, tokens_used, latency_ms)

        return {
            "text": text,
            "tokens_used": tokens_used,
            "latency_ms": round(latency_ms, 3),
            "backend": self.backend_name,
        }

    def chat(
        self,
        messages: List[Dict[str, str]],
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        prompt = self._format_chat_prompt(messages)
        result = self.generate(prompt, max_tokens, temperature, top_p)
        return {
            "content": result["text"],
            "tokens_used": result["tokens_used"],
            "latency_ms": result["latency_ms"],
            "backend": result["backend"],
        }

    @staticmethod
    def _format_chat_prompt(messages: List[Dict[str, str]]) -> str:
        parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role in ("system", "user", "assistant"):
                parts.append(f"<|im_start|>{role}\n{content}<|im_end|>\n")
        parts.append("<|im_start|>assistant\n")
        return "".join(parts)

    def _log(
        self,
        request_type: str,
        prompt: str,
        response: str,
        tokens_used: int,
        latency_ms: float,
    ) -> None:
        """写推理日志。日志失败不得影响推理响应。"""
        try:
            session = get_session_maker()()
        except Exception:
            return
        try:
            session.add(
                InferenceLog(
                    request_type=request_type,
                    prompt=prompt[:1000],
                    response=response[:1000],
                    tokens_used=tokens_used,
                    latency_ms=latency_ms,
                    backend=self.backend_name,
                )
            )
            session.commit()
        except Exception:
            session.rollback()
        finally:
            session.close()

    # ---------------- OpenAI 兼容响应 ----------------

    def create_completion_response(
        self,
        prompt: str,
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        result = self.generate(prompt, max_tokens, temperature, top_p)
        prompt_tokens = len(prompt.split())
        return {
            "id": f"cmpl-{uuid.uuid4().hex[:8]}",
            "object": "text_completion",
            "model": model,
            "backend": result["backend"],
            "choices": [
                {"index": 0, "text": result["text"], "finish_reason": "stop"}
            ],
            "created": int(time.time()),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": result["tokens_used"],
                "total_tokens": prompt_tokens + result["tokens_used"],
            },
        }

    def create_chat_response(
        self,
        messages: List[Dict[str, str]],
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        top_p: float = 0.9,
    ) -> Dict[str, Any]:
        result = self.chat(messages, max_tokens, temperature, top_p)
        prompt_tokens = sum(len(m.get("content", "").split()) for m in messages)
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "model": model,
            "backend": result["backend"],
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": result["content"]},
                    "finish_reason": "stop",
                }
            ],
            "created": int(time.time()),
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": result["tokens_used"],
                "total_tokens": prompt_tokens + result["tokens_used"],
            },
        }
