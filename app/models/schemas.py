from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum


class DataSourceType(str, Enum):
    FILE = "file"
    API = "api"
    DATABASE = "database"


class AnnotationStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    REJECTED = "rejected"


class FinetuneStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EvaluationStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class DatasetCreate(BaseModel):
    name: str
    description: Optional[str] = None
    source_type: DataSourceType = DataSourceType.FILE


class DatasetResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]
    source_type: str
    total_samples: int
    created_at: datetime

    class Config:
        from_attributes = True


class AnnotationCreate(BaseModel):
    dataset_id: int
    instruction: str
    input_text: Optional[str] = None
    output_text: Optional[str] = None
    raw_data: Optional[Dict[str, Any]] = None


class AnnotationUpdate(BaseModel):
    output_text: str
    status: AnnotationStatus = AnnotationStatus.COMPLETED
    annotator: Optional[str] = None


class AnnotationResponse(BaseModel):
    id: int
    dataset_id: int
    instruction: str
    input_text: Optional[str]
    output_text: Optional[str]
    status: str
    annotator: Optional[str]
    created_at: datetime

    class Config:
        from_attributes = True


class AnnotationTaskCreate(BaseModel):
    name: str
    dataset_id: int
    description: Optional[str] = None
    annotation_type: str = "text"


class AnnotationTaskResponse(BaseModel):
    id: int
    name: str
    dataset_id: int
    total_items: int
    completed_items: int
    status: str
    created_at: datetime

    class Config:
        from_attributes = True


class ModelLoadRequest(BaseModel):
    model_name: str
    model_path: Optional[str] = None
    lora_path: Optional[str] = None


class ModelResponse(BaseModel):
    id: int
    name: str
    model_type: str
    base_model: Optional[str]
    is_loaded: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model: str
    messages: List[ChatMessage]
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False


class ChatCompletionChoice(BaseModel):
    index: int
    message: ChatMessage
    finish_reason: str


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    model: str
    choices: List[ChatCompletionChoice]
    created: int
    usage: Dict[str, int]


class CompletionRequest(BaseModel):
    model: str
    prompt: str
    temperature: Optional[float] = 0.7
    top_p: Optional[float] = 0.9
    max_tokens: Optional[int] = 512
    stream: Optional[bool] = False


class CompletionChoice(BaseModel):
    index: int
    text: str
    finish_reason: str


class CompletionResponse(BaseModel):
    id: str
    object: str = "text_completion"
    model: str
    choices: List[CompletionChoice]
    created: int
    usage: Dict[str, int]


class FinetuneCreate(BaseModel):
    model_id: int
    dataset_id: int
    job_name: str
    method: str = "lora"
    config: Optional[Dict[str, Any]] = None


class FinetuneResponse(BaseModel):
    id: int
    model_id: int
    dataset_id: int
    job_name: str
    method: str
    status: str
    progress: float
    created_at: datetime

    class Config:
        from_attributes = True


class EvaluationCreate(BaseModel):
    model_id: int
    dataset_id: Optional[int] = None
    eval_name: str
    metrics: Optional[List[str]] = None


class EvaluationResponse(BaseModel):
    id: int
    model_id: int
    eval_name: str
    status: str
    metrics: Optional[Dict[str, Any]]
    results: Optional[Dict[str, Any]]
    created_at: datetime

    class Config:
        from_attributes = True


class HealthResponse(BaseModel):
    status: str
    version: str
    models_loaded: int
