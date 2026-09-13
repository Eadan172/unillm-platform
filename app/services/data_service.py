import csv
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.core.values import INVISIBLE_CHARS, has_visible_content
from app.models.database import Annotation, Dataset

# 兼容旧引用：零宽 / 不可见字符常量统一由 app.core.values 定义。
_INVISIBLE_CHARS = INVISIBLE_CHARS


def _resolve_field(item, primary, alias):
    """返回 ``(实际使用的键名, 值)``，优先 primary、回退 alias，都没有则为默认空串。

    保留旧实现 ``item.get(primary, item.get(alias, ""))`` 的语义：primary 键存在
    时即使值为 None 也取 None（不回退 alias）。回显实际键名是为了让校验错误能
    准确指出用户写的到底是哪个字段。
    """
    if primary in item:
        return primary, item[primary]
    if alias in item:
        return alias, item[alias]
    return primary, ""


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
        """把内容字段值收敛为可安全写入 TEXT 列的标量（**仅限空值与布尔**）。

        - ``None`` -> ``""``（``Annotation.instruction`` 为 ``nullable=False``，
          空值语义明确，属于正常兜底，不算「假成功」）
        - ``bool`` -> ``"true"``/``"false"``（避免被存成 ``'True'``/``'False'``）
        - ``str`` / ``int`` / ``float`` -> 原样返回

        注意：``list`` / ``dict`` 等非标量**不在此处收敛**。早期实现用
        ``json.dumps`` 把它们转成字符串后照常入库并返回 200「成功 N 条」，
        等于用一个看似正常的返回值掩盖真实的格式错误——属于静默存垃圾，
        与本项目「不造假、不谎报」原则相悖。这类值一律交由
        :meth:`_require_scalar` 显式拒绝。
        """
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return value
        return value

    @staticmethod
    def _require_scalar(field_name: str, value: Any) -> Any:
        """校验字段值为标量；非标量直接抛 ``ValueError``（路由映射为 400）。

        错误消息点明**哪个字段**、**实际是什么类型**，并给出修正方向，避免用户
        看到「类型不对」却不知道该改哪里。不使用 ``str()`` / ``json.dumps`` 强行
        收敛——那会把格式错误变成一条看似成功入库的垃圾样本。
        """
        value = DataService._coerce_scalar(value)
        if isinstance(value, (str, int, float, bool)) or value is None:
            return value
        raise ValueError(
            "字段 '{field}' 的值类型不受支持：内容字段只能是标量"
            "（字符串 / 数字 / 布尔 / 空值），实际为 {actual_type}。"
            "请将该字段改为字符串后再导入（例如把列表拼接为一段文本，"
            "或改用多条记录表达）。".format(
                field=field_name, actual_type=type(value).__name__
            )
        )

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
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        elif file_type == "jsonl":
            data = []
            with open(file_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        data.append(json.loads(line))
        elif file_type == "csv":
            # 原实现用 pandas 只为读一个 CSV，却引入 pandas + pyarrow 约 120MB
            # 依赖。标准库 csv 足以覆盖，故改用 stdlib。
            with open(file_path, "r", encoding="utf-8-sig", newline="") as f:
                data = [dict(row) for row in csv.DictReader(f)]
        else:
            raise ValueError(f"Unsupported file type: {file_type}")

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
