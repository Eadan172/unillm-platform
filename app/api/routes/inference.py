"""OpenAI 兼容推理 API。

修复：
1. 删除了 ``if inference_svc.current_model is None and ...: pass`` 这段空操作死代码
   （它原本想做的"按请求指定模型"从未实现）。
2. 响应体增加 ``backend`` 字段，调用方能立刻知道这是真实模型输出还是占位文本。
3. ``stream=True`` 目前不支持，改为显式 400，而不是静默返回非流式结果。
4. ``/v1/models`` 原先硬编码一个模型名和固定的 created 时间戳；现在列出注册表
   中真实存在的模型，未注册时如实返回空列表。
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_inference_service
from app.config import settings
from app.models.schemas import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    ChatCompletionChoice,
    ChatMessage,
    CompletionChoice,
    CompletionRequest,
    CompletionResponse,
)
from app.services.inference_service import InferenceService
from app.services.model_service import ModelService

router = APIRouter(tags=["Inference (OpenAI Compatible)"])


@router.post("/v1/completions", response_model=CompletionResponse)
async def create_completion(
    request: CompletionRequest,
    inference_svc: InferenceService = Depends(get_inference_service),
):
    if request.stream:
        raise HTTPException(status_code=400, detail="暂不支持 stream=true，请传 stream=false")

    response = inference_svc.create_completion_response(
        prompt=request.prompt,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
    )

    return CompletionResponse(
        id=response["id"],
        object=response["object"],
        model=response["model"],
        backend=response["backend"],
        choices=[
            CompletionChoice(
                index=c["index"], text=c["text"], finish_reason=c["finish_reason"]
            )
            for c in response["choices"]
        ],
        created=response["created"],
        usage=response["usage"],
    )


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    inference_svc: InferenceService = Depends(get_inference_service),
):
    if request.stream:
        raise HTTPException(status_code=400, detail="暂不支持 stream=true，请传 stream=false")
    if not request.messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")

    messages = [{"role": m.role, "content": m.content} for m in request.messages]

    response = inference_svc.create_chat_response(
        messages=messages,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p,
    )

    return ChatCompletionResponse(
        id=response["id"],
        object=response["object"],
        model=response["model"],
        backend=response["backend"],
        choices=[
            ChatCompletionChoice(
                index=c["index"],
                message=ChatMessage(
                    role=c["message"]["role"], content=c["message"]["content"]
                ),
                finish_reason=c["finish_reason"],
            )
            for c in response["choices"]
        ],
        created=response["created"],
        usage=response["usage"],
    )


@router.get("/v1/models")
async def list_models(db: Session = Depends(get_db)):
    """列出已注册模型。未注册任何模型时返回空 data（不再伪造一条记录）。"""
    models = ModelService(db).list_models(limit=1000)
    data = [
        {
            "id": model.name,
            "object": "model",
            "created": int(model.created_at.timestamp()) if model.created_at else 0,
            "owned_by": "unillm",
        }
        for model in models
    ]
    if not data:
        # 让 OpenAI 兼容客户端在未注册模型时仍有一个可用的默认名，
        # 但明确标注它是配置里的默认值、而非已注册模型。
        data = [
            {
                "id": settings.model.default_model,
                "object": "model",
                "created": 0,
                "owned_by": "unillm",
                "note": "default-from-config (未注册)",
            }
        ]
    return {"object": "list", "data": data}
