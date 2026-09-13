import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.values import (
    INVISIBLE_CHARS,
    coerce_scalar,
    has_visible_content,
    require_scalar,
    resolve_field,
)
from app.models.database import Annotation, Dataset

# 兼容旧引用：零宽 / 不可见字符常量统一由 app.core.values 定义。
_INVISIBLE_CHARS = INVISIBLE_CHARS


def _resolve_field(item, primary, alias):
    """薄委托，实现统一收敛在 app.core.values.resolve_field。"""
    return resolve_field(item, primary, alias)


# 文本文件读取：先按 UTF-8（含 BOM）尝试，失败再退到 GBK/GB18030。
# 依据 —— 中文 Windows 用户的真实来源：
#   1. 记事本另存为「UTF-8」会写入 BOM，裸 utf-8 打开会抛
#      "Unexpected UTF-8 BOM (decode using utf-8-sig)"（实测触发）
#   2. Excel 导出的 CSV/JSON 在中文环境下常是 GBK/GB18030 编码
# 这两个都不是攻击面，而是**日常使用必撞**的墙，故主动兼容。
_ENCODINGS = ("utf-8-sig", "gb18030")
# GB18030 是 GBK 的超集，能解出 GBK 无法表示的字符，故用更宽的那个兜底。


def _read_text_with_fallback(file_path: str, file_type: str) -> str:
    """按候选编码依次尝试读取文本；全失败时抛中文可操作提示。

    不做静默容错（``errors="replace"``）—— 那会把乱码写进数据集，
    比直接报错更糟。这里保持"拒绝"语义，只是把英文底层异常换成
    用户能照着做事的提示。
    """
    raw = Path(file_path).read_bytes() if False else None  # 占位：避免误用
    last_error: Optional[Exception] = None
    for encoding in _ENCODINGS:
        try:
            with open(file_path, "r", encoding=encoding, newline="") as f:
                return f.read()
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        except UnicodeError as exc:  # 包含 LookupError 之外的编码异常
            last_error = exc
            continue

    # 全部编码都失败：给出可操作的中文提示，附上真实的失败位置。
    raise ValueError(
        "文件编码无法识别：已尝试 UTF-8（含 BOM）与 GB18030（兼容 GBK），"
        "均无法解码。请用记事本或编辑器将文件「另存为」UTF-8 编码后重试"
        "（若源数据来自中文版 Excel，导出时请选择 UTF-8）。"
        f"原始错误：{last_error}"
    )


class DataService:
    def __init__(self, db_session: Session):
        self.db = db_session
        self.storage_path = Path(settings.storage.datasets_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)

    def rollback(self) -> None:
        """把 Session 从失败/失效状态恢复出来（薄封装，便于路由层调用）。"""
        self.db.rollback()

    def _safe_rollback(self) -> None:
        """在抛错前回滚未提交的挂起对象，避免泄漏成孤儿行。

        即便本次实现已把校验前置（抛错时通常无 pending 对象），仍显式回滚以
        防御未来改动：Session 若处于失效/挂起态，这里静默吞掉异常，绝不因
        回滚失败而掩盖真正的校验错误。
        """
        try:
            self.db.rollback()
        except Exception:
            pass

    @staticmethod
    def _coerce_scalar(value: Any) -> Any:
        """薄委托，实现统一收敛在 app.core.values.coerce_scalar。"""
        return coerce_scalar(value)

    @staticmethod
    def _require_scalar(field_name: str, value: Any) -> Any:
        """薄委托，实现统一收敛在 app.core.values.require_scalar。

        保留同名方法是为了不惊动既有调用点，并确保既有错误文案一字不变。
        """
        return require_scalar(field_name, value)

    @staticmethod
    def _has_visible_text(value: Any) -> bool:
        """判断字段值是否含「可见」内容。

        薄封装，实际判定统一收敛在 :func:`app.core.values.has_visible_content`，
        避免「有没有内容」的语义在各处重复实现（6 处 ``or ""`` 形态曾因此散落全项目）。
        """
        return has_visible_content(value)

    def create_dataset(self, name: str, description: str = None, source_type: str = "file") -> Dataset:
        dataset = Dataset(
            name=name,
            description=description,
            source_type=source_type
        )
        self.db.add(dataset)
        self.db.commit()
        self.db.refresh(dataset)
        return dataset

    def import_data_from_file(self, dataset_id: int, file_path: str, file_type: str = "json") -> int:
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if not dataset:
            raise ValueError(f"Dataset {dataset_id} not found")

        if file_type == "json":
            # 统一走编码回退读取：旧实现裸 utf-8 打开，遇到 BOM 或 GBK 直接抛
            # 英文 UnicodeDecodeError（实测触发），中文用户无从下手。
            text = _read_text_with_fallback(file_path, file_type)
            if not text.strip():
                # 0 字节 / 纯空白文件：旧实现直接喂给 json.load()，抛的是
                # "Expecting value: line 1 column 1 (char 0)" 英文底层异常，
                # 与其余分支的中文文案不一致。这里前移到统一提示。
                self._safe_rollback()
                raise ValueError(
                    "文件中没有任何有效记录：接受的格式为 "
                    "JSON / JSONL / CSV，且至少需包含一条记录（空文件、仅空行、"
                    "或 CSV 只有表头的文件会被拒绝）。"
                )
            try:
                data = json.loads(text)
            except json.JSONDecodeError as exc:
                self._safe_rollback()
                raise ValueError(
                    "JSON 解析失败：文件不是合法的 JSON。"
                    f"错误位置在第 {exc.lineno} 行第 {exc.colno} 列（{exc.msg}）。"
                    "请检查括号 / 引号是否配对、是否有多余逗号，"
                    "或改用 .jsonl（每行一条记录）。"
                ) from exc
        elif file_type == "jsonl":
            data = []
            text = _read_text_with_fallback(file_path, file_type)
            for lineno, line in enumerate(text.splitlines(), 1):
                if line.strip():
                    try:
                        data.append(json.loads(line))
                    except json.JSONDecodeError as exc:
                        self._safe_rollback()
                        raise ValueError(
                            f"JSONL 第 {lineno} 行解析失败：该行不是合法的 JSON"
                            f"（{exc.msg}）。JSONL 要求**每行一个完整 JSON 对象**，"
                            "不能跨行换行、行尾不能有多余逗号。"
                        ) from exc
        elif file_type == "csv":
            # 原实现用 pandas 只为读一个 CSV，却引入 pandas + pyarrow 约 120MB
            # 依赖。标准库 csv 足以覆盖，故改用 stdlib。
            text = _read_text_with_fallback(file_path, file_type)
            data = [dict(row) for row in csv.DictReader(io.StringIO(text, newline=""))]
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

        # P3-2：JSON 顶层必须是数组。旧实现直接 ``for item in data`` 迭代，
        # 若顶层是对象（``{"instruction": ...}`` 忘了用数组包裹），迭代出来的是
        # **键名（str）**，于是报「解析到类型 str」——真实顶层类型是 object，
        # 报错了对象，用户照着自己代码看会一头雾水。更糟的是顶层对象会被 len()
        # 数成键数（非 0），A1 空文件校验也拦不住。
        # 这里只把假话说成真话：报出真实顶层类型与修正方向，**不**静默包成单条记录。
        if file_type == "json" and not isinstance(data, list):
            self._safe_rollback()
            top_kind = (
                "对象（object）" if isinstance(data, dict)
                else type(data).__name__
            )
            raise ValueError(
                "JSON 文件的顶层结构不是数组：解析到的顶层类型是 {kind}，"
                "无法逐条提取样本。请用数组包裹记录"
                "（形如 [{{'instruction': ..., 'output': ...}}, ...]），"
                "或改用 .jsonl（每行一条记录）。".format(kind=top_kind)
            )

        # A1：文件里没有任何有效记录（0 字节 / 仅空行 / CSV 只有表头）时，
        # 旧实现会「正常」返回 0，静默落库一个 0 样本的空数据集，错误暴露过晚。
        # 这里前置拒绝，交由路由层映射为 400。
        if len(data) == 0:
            self._safe_rollback()
            raise ValueError(
                "文件中没有任何有效记录：接受的格式为 "
                "JSON / JSONL / CSV，且至少需包含一条记录（空文件、仅空行、"
                "或 CSV 只有表头的文件会被拒绝）。"
            )

        # ---- 第一步：先把整批数据解析成待入库的字段（**不碰 Session**）----
        # 关键顺序：任何校验都必须发生在 self.db.add() 之前。旧实现「先 add
        # 再校验」，A2 抛错时 pending 对象仍挂在 Session 上；路由 delete_dataset
        # 因 autoflush=False 看不到它们（DELETE 影响 0 行），随后的 commit 却把它们
        # 真正 INSERT，于是留下 dataset_id 悬空的孤儿 annotation，并被**下一个
        # 数据集**继承（0 样本数据集对外报 pending=3）。先校验后落库可根除。
        prepared: List[Dict[str, Any]] = []
        content_count = 0
        for item in data:
            if not isinstance(item, dict):
                # 行本身不是对象（数字 / 字符串 / 数组 / null）——无法提取字段。
                self._safe_rollback()
                raise ValueError(
                    "文件中存在非对象记录：每一行/每条记录必须是 JSON 对象"
                    "（形如 {{'instruction': ..., 'output': ...}}），"
                    "但解析到类型 {kind}。".format(kind=type(item).__name__)
                )

            instruction = self._require_scalar(
                *_resolve_field(item, "instruction", "question"))
            input_text = self._require_scalar(
                *_resolve_field(item, "input", "context"))
            output_text = self._require_scalar(
                *_resolve_field(item, "output", "answer"))

            # 三者任一含「可见字符」才算可识别内容（零宽字符/BOM 不算）。
            has_content = any(
                self._has_visible_text(value)
                for value in (instruction, input_text, output_text)
            )
            if has_content:
                content_count += 1

            # 源数据自带答案即视为已标注。原实现一律标记 pending，
            # 导致 export_to_training_format（只导 completed）导出空文件，
            # 微调拿到 0 条样本。
            status = "completed" if self._has_visible_text(output_text) else "pending"

            prepared.append({
                "instruction": instruction,
                "input_text": input_text,
                "output_text": output_text,
                "raw_data": item,
                "status": status,
            })

        # A2：记录条数 > 0，但没有一条含可识别的内容字段 —— 说明用户用了平台
        # 不认识的键名（例如 {"text": ..., "label": ...}）。整体拒绝，不做部分导入，
        # 避免落库一堆「字段全为空」的假样本后对外谎报 total_samples。
        if len(prepared) > 0 and content_count == 0:
            self._safe_rollback()
            actual_keys = sorted(data[0].keys())
            raise ValueError(
                "没有任何记录包含可识别的内容字段：解析成功 {total} 条，但每条的 "
                "instruction / input / output 均为空，无法作为有效样本入库。"
                "平台接受的内容字段为：instruction（或 question）、input（或 context）、"
                "output（或 answer）。第一条记录实际出现的键名为：{actual}。"
                "请将文本放入 instruction（或 question）、输入放入 input（或 context）、"
                "答案放入 output（或 answer）。".format(total=len(prepared), actual=actual_keys)
            )

        # ---- 第二步：全部校验通过后，才真正落库 ----
        count = 0
        for record in prepared:
            self.db.add(Annotation(
                dataset_id=dataset_id,
                instruction=record["instruction"],
                input_text=record["input_text"],
                output_text=record["output_text"],
                raw_data=record["raw_data"],
                status=record["status"],
            ))
            count += 1

        dataset.total_samples = count
        dataset.file_path = file_path
        self.db.commit()

        dest_path = self.storage_path / f"dataset_{dataset_id}.json"
        with open(dest_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return count

    def get_dataset(self, dataset_id: int) -> Optional[Dataset]:
        return self.db.query(Dataset).filter(Dataset.id == dataset_id).first()

    def list_datasets(self, skip: int = 0, limit: int = 100) -> List[Dataset]:
        return self.db.query(Dataset).offset(skip).limit(limit).all()

    def delete_dataset(self, dataset_id: int) -> bool:
        dataset = self.db.query(Dataset).filter(Dataset.id == dataset_id).first()
        if dataset:
            self.db.query(Annotation).filter(Annotation.dataset_id == dataset_id).delete()
            self.db.delete(dataset)
            self.db.commit()
            return True
        return False

    def get_annotations(self, dataset_id: int, skip: int = 0, limit: int = 100) -> List[Annotation]:
        return self.db.query(Annotation).filter(
            Annotation.dataset_id == dataset_id
        ).offset(skip).limit(limit).all()

    def export_to_training_format(self, dataset_id: int, output_path: str = None) -> str:
        """导出已标注样本为训练用 jsonl。没有可用样本时抛 ValueError。"""
        dataset = self.get_dataset(dataset_id)
        if dataset is None:
            raise ValueError(f"Dataset {dataset_id} not found")

        annotations = self.db.query(Annotation).filter(
            Annotation.dataset_id == dataset_id,
            Annotation.status == "completed"
        ).all()

        training_data = []
        for ann in annotations:
            # 这里读的是 SQLite TEXT 列，``0`` 落库即被存成文本 ``'0'``，读回来是
            # ``str`` 而非 ``int 0``，因此 ``or ""`` 不会触发短路——当前不构成缺陷
            # （已用探针确认：ORM 值 ``'0'``、type ``str``）。但它与曾咬人的
            # fake-missing 是同一形态，故一并收敛到统一判定，避免列类型/ORM 映射
            # 变化后复发。
            if not has_visible_content(ann.output_text):
                continue
            training_data.append({
                "instruction": ann.instruction,
                # 取默认值语义（无 input 时给空串），不是判空语义，保持原样。
                "input": ann.input_text or "",
                "output": ann.output_text
            })

        if not training_data:
            raise ValueError(
                f"数据集 {dataset_id} 中没有已标注（status=completed 且 output 非空）"
                "的样本，无法导出训练数据。请先完成标注或导入自带答案的数据。"
            )

        if output_path is None:
            output_path = str(self.storage_path / f"training_data_{dataset_id}.jsonl")

        with open(output_path, "w", encoding="utf-8") as f:
            for item in training_data:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

        return output_path
