"""输入校验回归测试（本次新增的平台边界校验）。

覆盖本次修复的三处平台输入校验缺陷：

- **A1 空文件/仅空行**：``import_data_from_file`` 解析结果为空时旧实现会
  「正常」返回 0，落库一个 0 样本的空数据集且接口返回 200。现在必须 400。
- **A2 无可识别内容字段**：旧实现只识别 ``instruction/question``、``input/context``、
  ``output/answer``；若提交方用 ``{text, label}`` 这类不认识的键名，三个 get 全部命中
  默认值，于是静默入库一堆「字段全空」的壳记录，却对外谎报 ``total_samples`` 正常。
  现在必须整体拒绝（不做部分导入），并在消息里回显首条实际键名。
- **A3 评测关联模型校验**：``POST /api/evaluate/create`` 传不存在的 ``model_id``
  旧实现返回 200；现在应与同资源读接口语义一致，返回 404。

约定：``conftest`` 默认 ``auth_enabled=False``，无需 Token；每个用例前会自动清库与清存储目录。
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import settings
from app.core.values import has_visible_content, is_missing
from app.models.database import get_engine


def _upload(client, filename: str, content: bytes, name: str = "ds"):
    return client.post(
        "/api/data/import",
        params={"name": name},
        files={"file": (filename, content, "application/octet-stream")},
    )


def _dataset_list(client):
    return client.get("/api/data/list").json()


def _table_counts() -> dict:
    """直读数据库，拿到 datasets / annotations / 孤儿行数量。

    仅断言 ``datasets`` 表不足以发现「拒绝后残留孤儿 annotation」这类缺陷
    （见 QA-VERIFY-2 的 F-1）。这里同时核对 annotations 表与 LEFT JOIN 孤儿。
    """
    with get_engine().connect() as conn:
        datasets = conn.execute(text("SELECT COUNT(*) FROM datasets")).scalar()
        annotations = conn.execute(text("SELECT COUNT(*) FROM annotations")).scalar()
        orphans = conn.execute(
            text(
                "SELECT COUNT(*) FROM annotations a "
                "LEFT JOIN datasets d ON a.dataset_id = d.id WHERE d.id IS NULL"
            )
        ).scalar()
    return {"datasets": datasets, "annotations": annotations, "orphans": orphans}


def _annotation_rows() -> list:
    """直读 annotations 表，返回 ``(instruction, output_text, status)`` 列表。

    用于断言「数值 0 这种合法 falsy 值没有被误判为空」——只看 HTTP 状态码和
    ``total_samples`` 是不够的，``output=0`` 的缺陷恰恰是接口返回 200 却把行标成
    ``pending``（对外谎报「没有已标注的样本」）。必须看到 status 本身。
    """
    with get_engine().connect() as conn:
        return [
            (row[0], row[1], row[2])
            for row in conn.execute(
                text(
                    "SELECT instruction, output_text, status FROM annotations "
                    "ORDER BY id"
                )
            )
        ]


class TestEmptyFileRejected:
    """A1：空文件 / 仅空行 / 只有表头的 CSV 一律 400，且不留孤儿数据集。"""

    def test_zero_byte_jsonl_rejected(self, client):
        response = _upload(client, "empty.jsonl", b"")
        assert response.status_code == 400, response.text
        assert "没有任何有效记录" in response.json()["detail"]
        # 不得留下 0 样本的空数据集
        assert _dataset_list(client) == []

    def test_only_blank_lines_jsonl_rejected(self, client):
        response = _upload(client, "blank.jsonl", b"\n\n   \n\t\n")
        assert response.status_code == 400, response.text
        assert "没有任何有效记录" in response.json()["detail"]
        assert _dataset_list(client) == []

    def test_csv_with_only_header_rejected(self, client):
        response = _upload(client, "header_only.csv", b"instruction,input,output\n")
        assert response.status_code == 400, response.text
        assert _dataset_list(client) == []


class TestUnrecognizedFieldsRejected:
    """A2：字段名对不上（如 {text,label}）时整体拒绝，不静默入库空壳记录。"""

    def test_text_label_format_rejected_with_actual_keys_echoed(self, client):
        payload = "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"text": "位置很好，出门就是地铁", "label": 1},
                {"text": "隔音差到没法睡", "label": 0},
            ]
        ).encode("utf-8")

        response = _upload(client, "case.jsonl", payload)
        assert response.status_code == 400, response.text

        detail = response.json()["detail"]
        assert "没有任何记录包含可识别的内容字段" in detail
        # 回显首条实际键名，便于用户定位
        assert "['label', 'text']" in detail
        # 给出接受的字段名与修正方向
        assert "instruction" in detail and "output" in detail
        # 关键：整批拒绝，不留任何壳数据集
        assert _dataset_list(client) == []

    def test_all_empty_values_rejected(self, client):
        payload = b'{"instruction":"","input":"","output":""}\n'
        response = _upload(client, "blank_fields.jsonl", payload)
        assert response.status_code == 400, response.text
        assert "没有任何记录包含可识别的内容字段" in response.json()["detail"]
        assert _dataset_list(client) == []

    def test_valid_rows_still_import(self, client):
        """正向对照：含可识别字段的记录必须照常导入（校验不能误伤）。"""
        payload = b'{"instruction":"1+1=?","output":"2"}\n'
        response = _upload(client, "ok.jsonl", payload)
        assert response.status_code == 200, response.text
        assert response.json()["total_samples"] == 1
        assert len(_dataset_list(client)) == 1


class TestEvaluationCreateValidatesModel:
    """A3：评测 create 必须校验 model_id 指向的模型存在。"""

    def test_nonexistent_model_id_returns_404(self, client):
        response = client.post(
            "/api/evaluate/create",
            json={"model_id": 888888, "eval_name": "bad", "metrics": ["exact_match"]},
        )
        assert response.status_code == 404, response.text
        assert response.json()["error_code"] == "NOT_FOUND"
        # 不得创建出一条指向不存在模型的评测
        assert client.get("/api/evaluate/list").json() == []

    def test_existing_model_id_still_creates(self, client):
        model = client.post("/api/model/register", params={"name": "eval-target"}).json()
        response = client.post(
            "/api/evaluate/create",
            json={"model_id": model["id"], "eval_name": "ok", "metrics": ["exact_match"]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["model_id"] == model["id"]


class TestRejectedImportLeavesNoOrphans:
    """QA-VERIFY-2 F-1：导入被拒后不得在 annotations 表留下孤儿行。

    旧实现「先 self.db.add() 再校验」，抛出 ValueError 时 pending 对象仍在
    Session 中；delete_dataset 因 autoflush=False 看不到它们（DELETE 影响 0 行），
    随后 commit 却把它们 INSERT 进去 —— 于是留下 dataset_id 悬空的孤儿行，
    并被**下一个数据集**继承（0 样本数据集对外报 pending=3）。
    """

    def test_a2_reject_leaves_no_orphan_annotations(self, client):
        payload = "\n".join(
            json.dumps(row, ensure_ascii=False)
            for row in [
                {"text": "很好", "label": 1},
                {"text": "很差", "label": 0},
                {"text": "一般", "label": 1},
            ]
        ).encode("utf-8")
        response = _upload(client, "case.jsonl", payload)
        assert response.status_code == 400, response.text

        counts = _table_counts()
        assert counts["datasets"] == 0
        assert counts["annotations"] == 0, counts
        assert counts["orphans"] == 0, counts

    def test_next_dataset_does_not_inherit_phantom_pending(self, client):
        """拒绝后新建数据集，其标注进度必须为 total=0/pending=0。"""
        _upload(client, "case.jsonl", b'{"text":"a","label":1}\n')

        new_ds = client.post(
            "/api/data/create", json={"name": "fresh", "description": "x"}
        ).json()
        task = client.post(
            "/api/annotation/task",
            json={"name": "t", "dataset_id": new_ds["id"], "annotation_type": "text"},
        ).json()
        progress = client.get(
            f"/api/annotation/task/{task['id']}/progress"
        ).json()
        assert progress["total"] == 0, progress
        assert progress["pending"] == 0, progress

    def test_zero_byte_import_leaves_no_rows(self, client):
        response = _upload(client, "empty.jsonl", b"")
        assert response.status_code == 400, response.text
        assert _table_counts() == {"datasets": 0, "annotations": 0, "orphans": 0}


class TestNonScalarFieldValuesRejected:
    """QA-VERIFY-2 F-2：内容字段值为数组/对象时必须 400，且不留任何副作用。

    旧实现把 list/dict 直接写入 Text 列，commit 时 sqlite3 抛 ProgrammingError，
    路由兜底 except 又因 Session 失效二次抛错 → 500 + 孤儿数据集 + 磁盘残留。

    中途曾改成 ``json.dumps`` 收敛为可读文本后照常入库（HTTP 200）——但那只是把
    「500 崩溃」换成了「200 存垃圾」：用一个看似成功的返回值掩盖真实的格式错误，
    与本项目「不造假、不谎报」原则相悖。**最终选择显式拒绝**：类型错误必须直说，
    错误消息里点明字段名与实际类型，用户才知道该改哪里。

    另注：``None`` 不属于此类。``Annotation.instruction`` 为 ``nullable=False``，
    空值语义明确、有唯一合理解释，故 ``None -> ""`` 的兜底保留（见下方对应用例）。
    """

    def _leftover_files(self) -> list:
        """返回存储目录下残留的文件名（导入失败必须一个都不留）。"""
        return sorted(p.name for p in Path(settings.storage.datasets_path).glob("*"))

    def test_list_value_is_rejected_with_type_hint(self, client):
        """字段值是数组：400，且回显字段名 instruction 与类型 list。"""
        response = _upload(client, "arr.jsonl", b'{"instruction":[1]}\n')
        assert response.status_code == 400, response.text

        body = response.text
        assert "instruction" in body, body
        assert "list" in body, body
        # 给出修正方向，而不是只说「类型不对」
        assert "字符串" in body, body

        # 关键：拒绝路径必须零副作用
        assert _table_counts() == {"datasets": 0, "annotations": 0, "orphans": 0}
        assert _dataset_list(client) == []
        assert self._leftover_files() == [], self._leftover_files()

    def test_object_value_is_rejected_with_type_hint(self, client):
        """字段值是对象：400，且回显字段名 instruction 与类型 dict。"""
        response = _upload(client, "obj.jsonl", b'{"instruction":{"a":1}}\n')
        assert response.status_code == 400, response.text

        body = response.text
        assert "instruction" in body, body
        assert "dict" in body, body

        assert _table_counts() == {"datasets": 0, "annotations": 0, "orphans": 0}
        assert _dataset_list(client) == []
        assert self._leftover_files() == [], self._leftover_files()

    def test_alias_field_rejected_with_actual_key_name(self, client):
        """走别名（input）时，消息里回显的应是用户实际写的键名 input。"""
        response = _upload(
            client, "alias.jsonl", b'{"instruction":"x","input":[1,2]}\n'
        )
        assert response.status_code == 400, response.text
        assert "input" in response.text, response.text
        assert "list" in response.text, response.text
        assert _table_counts() == {"datasets": 0, "annotations": 0, "orphans": 0}

    def test_null_value_still_accepted(self, client):
        """None 与 list/dict 是两类问题：空值兜底保留，正常入库。"""
        response = _upload(
            client, "null.jsonl", b'{"instruction":null,"output":"2"}\n'
        )
        assert response.status_code == 200, response.text
        assert response.json()["total_samples"] == 1
        assert _table_counts() == {"datasets": 1, "annotations": 1, "orphans": 0}

    def test_non_dict_row_still_rejected_cleanly(self, client):
        response = _upload(client, "num.jsonl", b"123\n")
        assert response.status_code == 400, response.text
        assert _table_counts() == {"datasets": 0, "annotations": 0, "orphans": 0}


class TestInvisibleOnlyContentRejected:
    """QA-VERIFY-2 P3：零宽字符 / BOM 字符不能冒充「有内容」。"""

    def test_zero_width_space_only_rejected(self, client):
        response = _upload(
            client, "zw.jsonl", '{"instruction":"\u200b"}\n'.encode("utf-8")
        )
        assert response.status_code == 400, response.text
        assert _table_counts() == {"datasets": 0, "annotations": 0, "orphans": 0}

    def test_bom_char_only_rejected(self, client):
        response = _upload(
            client, "bom.jsonl", '{"instruction":"\ufeff"}\n'.encode("utf-8")
        )
        assert response.status_code == 400, response.text
        assert _table_counts()["annotations"] == 0


class TestNumericZeroIsRealContent:
    """数值 0 是合法内容，不是「缺失」（既有缺陷，本次发现并修复）。

    旧实现 ``_has_visible_text`` 写的是 ``str(value or "").strip()``，
    其中 ``0 or ""`` 求值为 ``""``，于是数值 ``0`` / ``0.0`` 被判成「没有内容」。
    后果有两个，且都违反本项目「绝不把缺失伪装成 0、也绝不把 0 当成缺失」的原则：

    1. ``{"instruction": ..., "output": 0}`` —— 合法答案 0（如情感二分类的「差评」）
       会被标成 ``status=pending``，整个数据集导不出训练数据，而 ``/export`` 对外
       解释是「没有已标注的样本」，是一个**虚假的状态**；
    2. ``{"instruction": 0}`` 单独一条会因「无可识别内容」报 400，而同类型同语义的
       ``{"instruction": 42}`` 却是 200 —— 仅因数值不同而结果相反。

    修法：显式区分 ``None`` 与 falsy 的 0（``value is None`` 先判），不再用
    ``or ""`` 兜底。
    """

    def test_numeric_zero_output_is_completed_and_exportable(self, client):
        """output=0：必须 completed，且 /export 能导出这 1 行。"""
        response = _upload(
            client,
            "zero_out.jsonl",
            '{"instruction":"判断情感","output":0}\n'.encode("utf-8"),
        )
        assert response.status_code == 200, response.text
        assert response.json()["total_samples"] == 1

        rows = _annotation_rows()
        assert rows == [("判断情感", "0", "completed")], rows

        exported = client.get(f"/api/data/{response.json()['id']}/export")
        assert exported.status_code == 200, exported.text
        output_path = Path(exported.json()["output_path"])
        lines = [
            ln
            for ln in output_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        assert len(lines) == 1, lines
        assert json.loads(lines[0])["output"] == "0", lines[0]

    def test_float_zero_output_is_completed_and_exportable(self, client):
        """output=0.0：同样必须 completed 且可导出。"""
        response = _upload(
            client,
            "zero_float.jsonl",
            '{"instruction":"判断情感","output":0.0}\n'.encode("utf-8"),
        )
        assert response.status_code == 200, response.text

        rows = _annotation_rows()
        assert rows == [("判断情感", "0.0", "completed")], rows

        exported = client.get(f"/api/data/{response.json()['id']}/export")
        assert exported.status_code == 200, exported.text

    def test_numeric_zero_instruction_accepted_like_42(self, client):
        """instruction=0 必须与 instruction=42 行为一致（都 200）。

        这是本缺陷最刺眼的一面：同类型同语义，仅因数值不同而 200/400 相反。
        """
        zero = _upload(client, "zero_instr.jsonl", b'{"instruction":0}\n')
        assert zero.status_code == 200, zero.text
        assert zero.json()["total_samples"] == 1
        assert _annotation_rows() == [("0", "", "pending")], _annotation_rows()

    def test_numeric_42_instruction_still_accepted(self, client):
        """对照组：``instruction=42`` 仍应是 200（防止放宽 0 时改过头）。"""
        response = _upload(client, "n42.jsonl", b'{"instruction":42}\n')
        assert response.status_code == 200, response.text
        assert response.json()["total_samples"] == 1

    def test_nonzero_numeric_output_still_completed(self, client):
        """回归对照：output=1（非 0）行为不能被本次修复改变。"""
        response = _upload(
            client,
            "one_out.jsonl",
            '{"instruction":"判断情感","output":1}\n'.encode("utf-8"),
        )
        assert response.status_code == 200, response.text
        assert _annotation_rows() == [("判断情感", "1", "completed")], _annotation_rows()

    def test_null_instruction_still_accepted(self, client):
        """防止修 None 时把兜底改坏：None 仍应走 ``""`` 兜底而非报错。

        （同类断言在 ``TestNonScalarFieldValuesRejected::test_null_value_still_accepted``
        已有一份，这里再锁一次是因为本次改动正好动到了 None 的判定分支。）
        """
        response = _upload(
            client, "null_instr.jsonl", b'{"instruction":null,"output":"2"}\n'
        )
        assert response.status_code == 200, response.text
        assert _annotation_rows() == [("", "2", "completed")], _annotation_rows()

    def test_blank_strings_still_rejected_after_fix(self, client):
        """反向回归："" 与纯空白仍必须判为无内容，不能因放宽 0 而误收。"""
        for filename, body in (
            ("blank_empty.jsonl", b'{"instruction":"","input":"","output":""}\n'),
            ("blank_spaces.jsonl", b'{"instruction":"   "}\n'),
            ("blank_zero_width.jsonl", '{"instruction":"\u200b"}\n'.encode("utf-8")),
        ):
            response = _upload(client, filename, body)
            assert response.status_code == 400, response.text
            assert _table_counts() == {"datasets": 0, "annotations": 0, "orphans": 0}


class TestFalsyValuesAreRealContent:
    """把「有没有内容」的判定收拢到 ``app.core.values`` 单一入口。

    项目里曾散落 6 处 ``or ""`` 形态的 falsy 判定，其中 2 处真实咬人（导入状态、
    评测样本剔除）。本类锁定公共判定函数的语义，并端到端锁住评测链路不再丢样本。

    区分标准：表达式的结果被用来**判断有没有内容**（危险，必须走
    ``has_visible_content``），还是被用来**取默认值**（安全，保持 ``or ""``）。
    """

    # ---- is_missing：只有 None 算缺失 ----

    def test_is_missing_only_true_for_none(self):
        assert is_missing(None) is True
        for value in (0, 0.0, False, "", "0", " ", [], {}, 42):
            assert is_missing(value) is False, value

    # ---- has_visible_content：0 / 0.0 / False 都是真实内容 ----

    def test_falsy_zero_is_visible_content(self):
        """核心断言：数值 0 是真实内容。"""
        assert has_visible_content(0) is True
        assert has_visible_content(0.0) is True
        assert has_visible_content(False) is True

    def test_zero_variants_and_truthy_values_are_content(self):
        for value in (0, 0.0, False, 1, -1, 0.5, "0", "x", " 0 ", [1], {"a": 1}, 42):
            assert has_visible_content(value) is True, value

    def test_missing_and_blank_are_not_content(self):
        assert has_visible_content(None) is False
        assert has_visible_content("") is False
        assert has_visible_content("   ") is False
        assert has_visible_content("\t\n") is False
        assert has_visible_content("\u200b") is False
        assert has_visible_content("\ufeff") is False
        assert has_visible_content(" \u200b ") is False

    # ---- P1-a 端到端：评测不得静默剔除 output=0 的样本 ----

    def test_evaluation_keeps_falsy_zero_samples(self, client):
        """test_data 里 output 为 0 / 1 / 0 时，三条都必须进入评测。

        旧实现 ``item.get("output") or item.get("answer") or ""`` 会把 output=0
        的样本静默 continue 掉，评测跑在被悄悄改小的测试集上——指标数字看起来
        正常，但结论是错的。
        """
        model = client.post("/api/model/register", params={"name": "falsy-eval"}).json()
        response = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "eval_name": "falsy-zero",
                "metrics": ["exact_match"],
            },
        )
        assert response.status_code == 200, response.text
        eval_id = response.json()["id"]

        run = client.post(
            f"/api/evaluate/{eval_id}/run",
            json={
                "test_data": [
                    {"instruction": "判断情感", "output": 0},
                    {"instruction": "判断情感", "output": 1},
                    {"instruction": "判断情感", "output": 0},
                ]
            },
        )
        assert run.status_code == 200, run.text

        # 样本数落在 results.exact_match.total —— 三条都必须被纳入
        payload = run.json()
        assert payload["results"]["exact_match"]["total"] == 3, payload

        persisted = client.get(f"/api/evaluate/{eval_id}/result")
        assert persisted.status_code == 200, persisted.text
        assert persisted.json()["results"]["exact_match"]["total"] == 3, persisted.json()

    def test_evaluation_all_zero_labels_is_not_empty(self, client):
        """全部标签都是 0 的评测集不得被判成「没有可用的评测数据」。

        旧实现（**代码推导，非实测**）：``item.get("output") or item.get("answer")
        or ""`` 中 ``0 or ...`` 短路成 ``""``，两条 output=0 的样本被全部
        ``continue`` 掉 ⇒ ``samples`` 为空 ⇒ run 抛「没有可用的评测数据」。

        更正记录：本用例注释早期写的是「修复前实测 run 400」，那条观察**成因
        不是 falsy 短路**——当时探针把 ``test_data`` 误传给了 ``/create``（该端点
        不接收此字段），``/run`` 无 body 才导致 400。已撤回该表述，改为纯代码推导。
        """
        model = client.post("/api/model/register", params={"name": "all-zero"}).json()
        response = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "eval_name": "all-zero",
                "metrics": ["exact_match"],
            },
        )
        assert response.status_code == 200, response.text
        eval_id = response.json()["id"]
        run = client.post(
            f"/api/evaluate/{eval_id}/run",
            json={
                "test_data": [
                    {"instruction": "a", "output": 0},
                    {"instruction": "b", "output": 0},
                ]
            },
        )
        assert run.status_code == 200, run.text
        payload = run.json()
        assert payload["results"]["exact_match"]["total"] == 2, payload

    def test_evaluation_accepts_answer_alias_with_zero(self, client):
        """answer 别名取值为 0 时同样必须被纳入。"""
        model = client.post("/api/model/register", params={"name": "alias-zero"}).json()
        response = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "eval_name": "alias-zero",
                "metrics": ["exact_match"],
            },
        )
        assert response.status_code == 200, response.text
        eval_id = response.json()["id"]
        run = client.post(
            f"/api/evaluate/{eval_id}/run",
            json={
                "test_data": [
                    {"instruction": "a", "answer": 0},
                    {"instruction": "b", "answer": 1},
                ]
            },
        )
        assert run.status_code == 200, run.text
        assert run.json()["results"]["exact_match"]["total"] == 2, run.json()

    def test_evaluation_still_skips_genuinely_missing_reference(self, client):
        """反向回归：真正没有参考答案的样本仍应被跳过（不能因放宽 0 而误收）。"""
        model = client.post("/api/model/register", params={"name": "missing-ref"}).json()
        response = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "eval_name": "missing-ref",
                "metrics": ["exact_match"],
            },
        )
        assert response.status_code == 200, response.text
        eval_id = response.json()["id"]
        run = client.post(
            f"/api/evaluate/{eval_id}/run",
            json={
                "test_data": [
                    {"instruction": "a", "output": ""},
                    {"instruction": "b", "output": "   "},
                    {"instruction": "c", "output": None},
                    {"instruction": "d", "output": 0},
                ]
            },
        )
        assert run.status_code == 200, run.text
        # 前三条无有效参考答案被剔除，只有 output=0 那条被保留
        assert run.json()["results"]["exact_match"]["total"] == 1, run.json()

    # ---- annotation submit：数字 0 到不了路由，字符串 "0" 必须放行 ----

    def test_annotation_submit_string_zero_accepted(self, client):
        """字符串 "0" 是合法答案，必须放行（不得被当成空答案拒绝）。"""
        ds = client.post("/api/data/create", json={"name": "ann"}).json()
        client.post(
            "/api/data/import",
            params={"name": "ann-src"},
            files={"file": ("d.jsonl", b'{"instruction":"x"}\n', "application/octet-stream")},
        )
        with get_engine().connect() as conn:
            ann_id = conn.execute(text("SELECT id FROM annotations LIMIT 1")).scalar()
        assert ann_id is not None

        response = client.post(
            "/api/annotation/submit",
            params={"annotation_id": ann_id},
            json={"output_text": "0"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["output_text"] == "0"

    def test_annotation_submit_numeric_zero_rejected_at_schema(self, client):
        """数字 0 在 Pydantic 入口即被拒（422），根本到不了路由判空。

        这解释了为何 annotation.py 那处 ``or ""`` 未构成缺陷——记录在此，
        防止后人误以为它是靠路由判空拦下的。
        """
        response = client.post(
            "/api/annotation/submit",
            params={"annotation_id": 1},
            json={"output_text": 0},
        )
        assert response.status_code == 422, response.text

