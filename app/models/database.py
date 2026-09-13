"""ORM 模型与数据库引擎。

原实现的缺陷：``init_database()`` 与 6 个路由模块各自
``create_engine`` 一次，同一个进程里最多存在 7 个互不相干的 Engine，
连接池无法复用，且 SQLite 在多线程下会抛
``SQLite objects created in a thread can only be used in that same thread``
（微调任务是在线程里访问数据库的）。

现在收敛为进程内单例 Engine + 单例 Session 工厂：
- ``get_engine()``      返回同一个 Engine
- ``get_session_maker()`` 返回同一个 sessionmaker
- ``init_database()``   建表并返回 sessionmaker（幂等）
- ``reset_database()``  释放单例，仅供测试隔离使用

相对路径的 SQLite 文件统一锚定到项目根目录，不再随启动时的工作目录漂移。
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

from app.config import PROJECT_ROOT, settings

Base = declarative_base()


def utcnow() -> datetime:
    """当前 UTC 时间（naive）。

    ``datetime.utcnow()`` 自 Python 3.12 起已被弃用。这里用等价的
    ``now(timezone.utc)`` 再剥离 tzinfo，保持与既有 naive 列一致的语义，
    避免混入带时区的值导致 SQLite 比较异常。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Dataset(Base):
    __tablename__ = "datasets"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    source_type = Column(String(50), default="file")
    file_path = Column(String(512), nullable=True)
    total_samples = Column(Integer, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    annotations = relationship("Annotation", back_populates="dataset")


class Annotation(Base):
    __tablename__ = "annotations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("annotation_tasks.id"), nullable=True)
    instruction = Column(Text, nullable=False)
    input_text = Column(Text, nullable=True)
    output_text = Column(Text, nullable=True)
    raw_data = Column(JSON, nullable=True)
    status = Column(String(50), default="pending")
    annotator = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    dataset = relationship("Dataset", back_populates="annotations")
    task = relationship("AnnotationTask", back_populates="annotations")


class AnnotationTask(Base):
    __tablename__ = "annotation_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    annotation_type = Column(String(50), default="text")
    total_items = Column(Integer, default=0)
    completed_items = Column(Integer, default=0)
    status = Column(String(50), default="pending")
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    annotations = relationship("Annotation", back_populates="task")


class Model(Base):
    __tablename__ = "models"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), nullable=False)
    model_type = Column(String(50), default="base")
    base_model = Column(String(255), nullable=True)
    model_path = Column(String(512), nullable=True)
    lora_path = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    is_loaded = Column(Boolean, default=False)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)

    finetune_jobs = relationship("FinetuneJob", back_populates="model")
    evaluations = relationship("Evaluation", back_populates="model")


class FinetuneJob(Base):
    __tablename__ = "finetune_jobs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=False)
    job_name = Column(String(255), nullable=False)
    method = Column(String(50), default="lora")
    status = Column(String(50), default="pending")
    progress = Column(Float, default=0.0)
    config = Column(JSON, nullable=True)
    output_path = Column(String(512), nullable=True)
    error_message = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow)

    model = relationship("Model", back_populates="finetune_jobs")


class Evaluation(Base):
    __tablename__ = "evaluations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    dataset_id = Column(Integer, ForeignKey("datasets.id"), nullable=True)
    eval_name = Column(String(255), nullable=False)
    status = Column(String(50), default="pending")
    metrics = Column(JSON, nullable=True)
    results = Column(JSON, nullable=True)
    created_at = Column(DateTime, default=utcnow)
    completed_at = Column(DateTime, nullable=True)

    model = relationship("Model", back_populates="evaluations")


class InferenceLog(Base):
    __tablename__ = "inference_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=True)
    request_type = Column(String(50), default="completion")
    prompt = Column(Text, nullable=True)
    response = Column(Text, nullable=True)
    tokens_used = Column(Integer, default=0)
    latency_ms = Column(Float, default=0.0)
    backend = Column(String(50), default="mock")
    created_at = Column(DateTime, default=utcnow)


# --------------------------------------------------------------------------
# 单例 Engine / Session 工厂
# --------------------------------------------------------------------------

_engine: Optional[Engine] = None
_session_maker: Optional[sessionmaker] = None


def resolve_db_path(db_path: Optional[str] = None) -> Path:
    """把配置里的数据库路径解析为绝对路径（相对路径锚定项目根）。"""
    raw = Path(db_path or settings.database.path)
    return raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()


def get_engine(db_path: Optional[str] = None) -> Engine:
    """返回进程内唯一的 SQLAlchemy Engine。"""
    global _engine
    if _engine is None:
        path = resolve_db_path(db_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        _engine = create_engine(
            f"sqlite:///{path.as_posix()}",
            # 微调任务在线程中写库，必须放开 SQLite 的线程归属检查
            connect_args={"check_same_thread": False},
            future=True,
        )
    return _engine


def get_session_maker(db_path: Optional[str] = None) -> sessionmaker:
    """返回进程内唯一的 sessionmaker。"""
    global _session_maker
    if _session_maker is None:
        _session_maker = sessionmaker(
            bind=get_engine(db_path), autoflush=False, expire_on_commit=False
        )
    return _session_maker


def init_database(db_path: Optional[str] = None) -> sessionmaker:
    """建表（幂等）并返回 sessionmaker。"""
    engine = get_engine(db_path)
    Base.metadata.create_all(engine)
    return get_session_maker(db_path)


def reset_database() -> None:
    """丢弃单例 Engine / Session 工厂。仅供测试隔离使用。"""
    global _engine, _session_maker
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_maker = None
