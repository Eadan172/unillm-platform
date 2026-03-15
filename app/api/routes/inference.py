from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.models.database import get_session_maker
from app.models.schemas import (
    ChatCompletionRequest, ChatCompletionResponse,
    CompletionRequest, CompletionResponse,
    ChatMessage, ChatCompletionChoice, CompletionChoice
)
from app.services.inference_service import InferenceService
from app.config import settings

router = APIRouter(tags=["Inference (OpenAI Compatible)"])

session_maker = get_session_maker(settings.database.path)

inference_service = None


def get_db():
    db = session_maker()
    try:
        yield db
    finally:
        db.close()


def get_inference_service(db: Session = Depends(get_db)) -> InferenceService:
    global inference_service
    if inference_service is None:
        inference_service = InferenceService(db)
    return inference_service


@router.post("/v1/completions", response_model=CompletionResponse)
async def create_completion(
    request: CompletionRequest,
    inference_svc: InferenceService = Depends(get_inference_service)
):
    if inference_svc.current_model is None and request.model != settings.model.default_model:
        pass
    
    response = inference_svc.create_completion_response(
        prompt=request.prompt,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p
    )
    
    return CompletionResponse(
        id=response["id"],
        object=response["object"],
        model=response["model"],
        choices=[
            CompletionChoice(
                index=c["index"],
                text=c["text"],
                finish_reason=c["finish_reason"]
            ) for c in response["choices"]
        ],
        created=response["created"],
        usage=response["usage"]
    )


@router.post("/v1/chat/completions", response_model=ChatCompletionResponse)
async def create_chat_completion(
    request: ChatCompletionRequest,
    inference_svc: InferenceService = Depends(get_inference_service)
):
    messages = [{"role": m.role, "content": m.content} for m in request.messages]
    
    response = inference_svc.create_chat_response(
        messages=messages,
        model=request.model,
        max_tokens=request.max_tokens,
        temperature=request.temperature,
        top_p=request.top_p
    )
    
    return ChatCompletionResponse(
        id=response["id"],
        object=response["object"],
        model=response["model"],
        choices=[
            ChatCompletionChoice(
                index=c["index"],
                message=ChatMessage(
                    role=c["message"]["role"],
                    content=c["message"]["content"]
                ),
                finish_reason=c["finish_reason"]
            ) for c in response["choices"]
        ],
        created=response["created"],
        usage=response["usage"]
    )


@router.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": settings.model.default_model,
                "object": "model",
                "created": 1700000000,
                "owned_by": "unillm"
            }
        ]
    }
