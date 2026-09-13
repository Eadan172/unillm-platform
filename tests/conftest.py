"""pytest 共享夹具。

关键点：**在导入 app 模块之前**就把数据库与存储目录改到临时目录，
避免测试写脏工作区里的 data/unillm.db。
"""

import json
import sys
import tempfile
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.config import settings  # noqa: E402

# ---- 隔离：把落盘位置全部改到临时目录（在 import app.main 之前生效） ----
_TMP_ROOT = Path(tempfile.mkdtemp(prefix="unillm-test-"))
settings.database.path = str(_TMP_ROOT / "test.db")
settings.storage.datasets_path = str(_TMP_ROOT / "datasets")
settings.storage.annotations_path = str(_TMP_ROOT / "annotations")
settings.storage.models_path = str(_TMP_ROOT / "models")
settings.storage.logs_path = str(_TMP_ROOT / "logs")
settings.app.debug = False
settings.app.auth_enabled = False
settings.evaluation.max_samples = 100

from app.api.deps import reset_inference_service  # noqa: E402
from app.main import app  # noqa: E402
from app.models.database import init_database, reset_database  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _isolated_runtime():
    reset_database()
    init_database()
    yield _TMP_ROOT
    reset_database()


@pytest.fixture(autouse=True)
def _clean_state():
    """每个用例前重建所有表、清空存储目录并重置推理后端，保证用例互不影响。"""
    import shutil

    from app.models.database import Base, get_engine

    engine = get_engine()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    for directory in (
        settings.storage.datasets_path,
        settings.storage.annotations_path,
        settings.storage.models_path,
        settings.storage.logs_path,
    ):
        path = Path(directory)
        shutil.rmtree(path, ignore_errors=True)
        path.mkdir(parents=True, exist_ok=True)

    reset_inference_service()
    yield
    reset_inference_service()


@pytest.fixture
def client():
    from starlette.testclient import TestClient

    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_rows():
    """小而完整的问答数据（自带答案 => 导入后即为已标注状态）。"""
    return [
        {"instruction": "1+1=?", "input": "", "output": "2"},
        {"instruction": "中国的首都？", "input": "", "output": "北京"},
        {"instruction": "水的化学式？", "input": "", "output": "H2O"},
    ]


@pytest.fixture
def sample_jsonl(tmp_path, sample_rows):
    path = tmp_path / "sample.jsonl"
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in sample_rows),
        encoding="utf-8",
    )
    return path
