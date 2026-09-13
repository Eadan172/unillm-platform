"""数据管理 API。

本轮修复：
1. **路径穿越**：``file.filename`` 原先直接拼进保存路径，
   ``../../..\\app\\main.py`` 这类文件名可以写到工作目录之外。现在只取
   ``Path(filename).name`` 并剥离危险字符。
2. **孤儿数据**：原先先把文件落盘、再创建 Dataset、最后才校验扩展名，
   校验失败时磁盘上留下无用文件、库里留下空数据集。现在校验前置，
   且任何失败都会回滚已写入的文件与记录。
3. **导出空文件**：导出接口不校验数据集是否存在，也不报告"无可导出样本"。
   现在返回明确错误。
4. 数据集查询统一 404，不再依赖 service 返回 None 后继续执行。
"""

import re
from pathlib import Path
from typing import List

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse

from app.api.deps import get_data_service
from app.config import settings
from app.models.schemas import DatasetCreate, DatasetResponse
from app.services.data_service import DataService

router = APIRouter(prefix="/api/data", tags=["Data Management"])

ALLOWED_EXTENSIONS = {"json", "jsonl", "csv"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB
_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._\u4e00-\u9fff-]")
# 下载文件名净化：去掉引号、换行、制表符与路径分隔符，防止 HTTP 头注入
_HEADER_UNSAFE_CHARS = re.compile(r'[\r\n\t"\\/]+')


def _safe_filename(raw_name: str) -> str:
    """把客户端文件名收敛为安全的纯文件名，阻断路径穿越。"""
    name = Path(raw_name or "").name  # 丢弃任何目录部分
    name = _UNSAFE_CHARS.sub("_", name).lstrip(".")
    if not name:
        raise HTTPException(status_code=400, detail="非法文件名")
    return name


def _sanitize_download_name(raw_name: str) -> str:
    """净化用于 ``Content-Disposition`` 的数据集名，防止 header 注入。

    去除引号、换行、制表符与路径分隔符；净化后为空则回退为 ``dataset``。
    """
    name = _HEADER_UNSAFE_CHARS.sub("_", str(raw_name or "")).strip()
    return name or "dataset"


def _to_response(dataset) -> DatasetResponse:
    return DatasetResponse(
        id=dataset.id,
        name=dataset.name,
        description=dataset.description,
        source_type=dataset.source_type,
        total_samples=dataset.total_samples,
        created_at=dataset.created_at,
    )


@router.post("/import", response_model=DatasetResponse)
async def import_dataset(
    name: str,
    file: UploadFile = File(...),
    description: str = None,
    data_service: DataService = Depends(get_data_service),
):
    safe_name = _safe_filename(file.filename)
    file_type = Path(safe_name).suffix.lstrip(".").lower()
    if file_type not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件类型 '.{file_type}'，仅支持 {sorted(ALLOWED_EXTENSIONS)}",
        )

    storage_path = Path(settings.storage.datasets_path)
    storage_path.mkdir(parents=True, exist_ok=True)
    file_path = storage_path / safe_name

    size = 0
    try:
        with open(file_path, "wb") as buffer:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件超过 {MAX_UPLOAD_BYTES // (1024 * 1024)}MB 上限",
                    )
                buffer.write(chunk)
    except HTTPException:
        file_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}") from exc

    dataset = None
    dataset_id = None
    try:
        dataset = data_service.create_dataset(name, description)
        dataset_id = dataset.id
        count = data_service.import_data_from_file(dataset_id, str(file_path), file_type)
    except Exception as exc:
        # 解析失败：回滚数据库记录与落盘文件，不留孤儿数据。
        # 注意：必须先 rollback 再访问 ORM 属性。若 commit/flush 已抛异常，
        # Session 会被标记为失效，此时取 dataset.id 会触发 refresh 而二次抛
        # PendingRollbackError，导致 400 从未构造、异常穿透成 500。
        try:
            data_service.db.rollback()
        except Exception:
            pass
        if dataset_id is not None:
            try:
                data_service.delete_dataset(dataset_id)
            except Exception:
                pass
        file_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"数据导入失败: {exc}") from exc

    return _to_response(data_service.get_dataset(dataset_id))


@router.post("/create", response_model=DatasetResponse)
async def create_dataset(
    dataset: DatasetCreate,
    data_service: DataService = Depends(get_data_service),
):
    created = data_service.create_dataset(
        name=dataset.name,
        description=dataset.description,
        source_type=dataset.source_type.value,
    )
    return _to_response(created)


@router.get("/list", response_model=List[DatasetResponse])
async def list_datasets(
    skip: int = 0,
    limit: int = 100,
    data_service: DataService = Depends(get_data_service),
):
    if skip < 0 or limit <= 0:
        raise HTTPException(status_code=400, detail="skip 必须 >= 0，limit 必须 > 0")
    return [_to_response(d) for d in data_service.list_datasets(skip, limit)]


@router.get("/{dataset_id}/export")
async def export_training_data(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service),
):
    try:
        output_path = data_service.export_to_training_format(dataset_id)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc
    return {"status": "success", "dataset_id": dataset_id, "output_path": output_path}


@router.get("/{dataset_id}/export/download")
async def download_training_data(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service),
):
    """把导出产物作为文件返回，供浏览器下载 JSONL。

    复用既有 ``export_to_training_format`` 的错误语义（与 ``/export`` 完全一致）：
    数据集不存在 -> 404；无已标注样本 -> 400 且带回同样的中文 ``detail``。
    """
    try:
        output_path = data_service.export_to_training_format(dataset_id)
    except ValueError as exc:
        detail = str(exc)
        status = 404 if "not found" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc

    dataset = data_service.get_dataset(dataset_id)
    dataset_name = dataset.name if dataset is not None else str(dataset_id)
    safe_name = _sanitize_download_name(dataset_name)
    return FileResponse(
        path=output_path,
        media_type="application/x-ndjson",
        filename=f"{safe_name}_training.jsonl",
    )


@router.get("/{dataset_id}", response_model=DatasetResponse)
async def get_dataset(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service),
):
    dataset = data_service.get_dataset(dataset_id)
    if not dataset:
        raise HTTPException(status_code=404, detail="Dataset not found")
    return _to_response(dataset)


@router.delete("/{dataset_id}")
async def delete_dataset(
    dataset_id: int,
    data_service: DataService = Depends(get_data_service),
):
    if not data_service.delete_dataset(dataset_id):
        raise HTTPException(status_code=404, detail="Dataset not found")
    return {"status": "deleted", "dataset_id": dataset_id}
