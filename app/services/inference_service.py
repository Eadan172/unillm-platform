import time
import uuid
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from app.models.database import InferenceLog
from app.config import settings


class InferenceService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.engine = None
        self.current_model: Optional[str] = None

    def load_model(self, model_name: str, model_path: str = None, lora_path: str = None):
        try:
            from vllm import LLM
            
            actual_path = model_path or model_name
            
            self.engine = LLM(
                model=actual_path,
                tensor_parallel_size=settings.model.tensor_parallel_size,
                gpu_memory_utilization=settings.model.gpu_memory_utilization,
                max_model_len=settings.model.max_model_len,
                trust_remote_code=True
            )
            self.current_model = model_name
            return {"status": "success", "model": model_name}
        except ImportError:
            return {"status": "error", "message": "vLLM not installed, using mock mode"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def unload_model(self):
        self.engine = None
        self.current_model = None
        return {"status": "success"}

    def generate(self, prompt: str, max_tokens: int = 512, 
                 temperature: float = 0.7, top_p: float = 0.9) -> Dict[str, Any]:
        start_time = time.time()
        
        if self.engine is None:
            response_text = f"[Mock Response] Model not loaded. Prompt was: {prompt[:100]}..."
            tokens_used = len(prompt.split()) + 50
        else:
            try:
                from vllm import SamplingParams
                
                sampling_params = SamplingParams(
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p
                )
                outputs = self.engine.generate([prompt], sampling_params)
                response_text = outputs[0].outputs[0].text
                tokens_used = len(prompt.split()) + len(response_text.split())
            except Exception as e:
                response_text = f"Error: {str(e)}"
                tokens_used = 0

        latency_ms = (time.time() - start_time) * 1000

        log = InferenceLog(
            request_type="completion",
            prompt=prompt[:1000],
            response=response_text[:1000],
            tokens_used=tokens_used,
            latency_ms=latency_ms
        )
        self.db.add(log)
        self.db.commit()

        return {
            "text": response_text,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms
        }

    def chat(self, messages: List[Dict[str, str]], max_tokens: int = 512,
             temperature: float = 0.7, top_p: float = 0.9) -> Dict[str, Any]:
        start_time = time.time()
        
        prompt = self._format_chat_prompt(messages)
        
        if self.engine is None:
            response_text = f"[Mock Response] Model not loaded. Last message was: {messages[-1]['content'][:100]}..."
            tokens_used = sum(len(m["content"].split()) for m in messages) + 50
        else:
            try:
                from vllm import SamplingParams
                
                sampling_params = SamplingParams(
                    max_tokens=max_tokens,
                    temperature=temperature,
                    top_p=top_p
                )
                outputs = self.engine.generate([prompt], sampling_params)
                response_text = outputs[0].outputs[0].text
                tokens_used = len(prompt.split()) + len(response_text.split())
            except Exception as e:
                response_text = f"Error: {str(e)}"
                tokens_used = 0

        latency_ms = (time.time() - start_time) * 1000

        log = InferenceLog(
            request_type="chat",
            prompt=prompt[:1000],
            response=response_text[:1000],
            tokens_used=tokens_used,
            latency_ms=latency_ms
        )
        self.db.add(log)
        self.db.commit()

        return {
            "content": response_text,
            "tokens_used": tokens_used,
            "latency_ms": latency_ms
        }

    def _format_chat_prompt(self, messages: List[Dict[str, str]]) -> str:
        formatted_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                formatted_parts.append(f"<|im_start|>system\n{content}<|im_end|>\n")
            elif role == "user":
                formatted_parts.append(f"<|im_start|>user\n{content}<|im_end|>\n")
            elif role == "assistant":
                formatted_parts.append(f"<|im_start|>assistant\n{content}<|im_end|>\n")
        formatted_parts.append("<|im_start|>assistant\n")
        return "".join(formatted_parts)

    def create_completion_response(self, prompt: str, model: str, 
                                    max_tokens: int = 512, 
                                    temperature: float = 0.7,
                                    top_p: float = 0.9) -> Dict[str, Any]:
        result = self.generate(prompt, max_tokens, temperature, top_p)
        
        return {
            "id": f"cmpl-{uuid.uuid4().hex[:8]}",
            "object": "text_completion",
            "model": model,
            "choices": [{
                "index": 0,
                "text": result["text"],
                "finish_reason": "stop"
            }],
            "created": int(time.time()),
            "usage": {
                "prompt_tokens": len(prompt.split()),
                "completion_tokens": result["tokens_used"],
                "total_tokens": len(prompt.split()) + result["tokens_used"]
            }
        }

    def create_chat_response(self, messages: List[Dict[str, str]], model: str,
                              max_tokens: int = 512,
                              temperature: float = 0.7,
                              top_p: float = 0.9) -> Dict[str, Any]:
        result = self.chat(messages, max_tokens, temperature, top_p)
        
        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": result["content"]
                },
                "finish_reason": "stop"
            }],
            "created": int(time.time()),
            "usage": {
                "prompt_tokens": sum(len(m["content"].split()) for m in messages),
                "completion_tokens": result["tokens_used"],
                "total_tokens": sum(len(m["content"].split()) for m in messages) + result["tokens_used"]
            }
        }
