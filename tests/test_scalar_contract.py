"""标量契约回归测试（P2-A / P2-B / P3-1 / P3-2）。

覆盖本轮获批的四项改动：

- **P2-A 评测侧缺标量守卫**：``test_data`` 里 ``output`` / ``answer`` /
  ``instruction`` / ``input`` 的值为数组或对象时，旧实现会把它 ``str()`` 成
  Python repr（``"[]"``、``"{'a': 1}"``，甚至不是合法 JSON）拿去算指标。
  必须与导入侧口径一致 —— 显式 400，且不得静默跳过、不得强转。
- **P2-B 非有限浮点**：``NaN`` / ``Infinity`` / ``-Infinity`` 能被 ``json.loads``
  与 ``pandas.to_json`` 产出，是 ``float`` 实例却非法；放行后 SQLite 会存成 NULL，
  产出 ``status='completed'`` 但 ``output_text IS NULL`` 的自相矛盾状态。
  必须 400 且零副作用。
- **P3-1 空列表不回退**：``test_data=[]`` 是「就用这 0 条」的明确意图，
  不得静默改用 ``dataset_id``。
- **P3-2 顶层结构报真话**：``.json`` 文件顶层是对象时报错必须说 ``object``，
  而不是迭代出键名后谎报「解析到类型 str」。

约定：``conftest`` 默认 ``auth_enabled=False``；每个用例前自动清库与清存储目录。
"""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.config import settings
from app.core.values import (
    coerce_scalar,
    has_visible_content,
    is_missing,
    require_scalar,
    resolve_field,
)
from app.models.database import get_engine


# --------------------------------------------------------------------------
# 辅助：计数与磁盘
# --------------------------------------------------------------------------

def _counts() -> dict:
    """直读数据库，拿到四张表计数与孤儿标注行数。"""
    with get_engine().connect() as conn:
        return {
            "datasets": conn.execute(text("SELECT COUNT(*) FROM datasets")).scalar(),
            "annotations": conn.execute(text("SELECT COUNT(*) FROM annotations")).scalar(),
            "annotation_tasks": conn.execute(
                text("SELECT COUNT(*) FROM annotation_tasks")
            ).scalar(),
            "orphans": conn.execute(
                text(
                    "SELECT COUNT(*) FROM annotations a "
                    "LEFT JOIN datasets d ON a.dataset_id = d.id WHERE d.id IS NULL"
                )
            ).scalar(),
        }


def _empty_counts() -> dict:
    return {"datasets": 0, "annotations": 0, "annotation_tasks": 0, "orphans": 0}


def _leftover_files() -> list:
    return sorted(p.name for p in Path(settings.storage.datasets_path).glob("*"))


def _upload(client, filename: str, content: bytes, name: str = "ds"):
    return client.post(
        "/api/data/import",
        params={"name": name},
        files={"file": (filename, content, "application/octet-stream")},
    )


def _model(client, name="scalar-target"):
    return client.post("/api/model/register", params={"name": name}).json()


def _run_with_test_data(client, eval_id: int, test_data):
    return client.post(
        f"/api/evaluate/{eval_id}/run", json={"test_data": test_data}
    )


def _run_with_raw_body(client, eval_id: int, body: bytes):
    """绕过 httpx 的 ``allow_nan=False``，直接发原始 JSON 字节。

    ``httpx`` 在 ``json=`` 路径上会用 ``allow_nan=False`` 编码，而
    ``json.dumps`` 默认 ``allow_nan=True`` 会产出裸 ``NaN`` / ``Infinity`` ——
    这正是服务端接到的真实报文（``json.loads`` 默认接受它们）。
    """
    return client.post(
        f"/api/evaluate/{eval_id}/run",
        content=body,
        headers={"content-type": "application/json"},
    )


def _create_eval(client, model_id: int, dataset_id: int = None, name="scalar"):
    payload = {"model_id": model_id, "eval_name": name, "metrics": ["exact_match"]}
    if dataset_id is not None:
        payload["dataset_id"] = dataset_id
    return client.post("/api/evaluate/create", json=payload)


# --------------------------------------------------------------------------
# 纯函数层：values.py 的契约
# --------------------------------------------------------------------------

class TestValuesModuleContract:
    def test_is_missing_only_none(self):
        assert is_missing(None) is True
        for value in (0, 0.0, False, "", [], {}, float("nan")):
            assert is_missing(value) is False, value

    def test_has_visible_content_zero_is_content(self):
        assert has_visible_content(0) is True
        assert has_visible_content(0.0) is True
        assert has_visible_content(False) is True

    def test_has_visible_content_blank_is_not_content(self):
        assert has_visible_content(None) is False
        assert has_visible_content("") is False
        assert has_visible_content("   ") is False
        assert has_visible_content("\u200b") is False
        assert has_visible_content("\ufeff") is False

    def test_has_visible_content_is_presence_not_type_guard(self):
        """刻意锁定这一事实：``[]`` / ``{}`` 会被判定为**有内容**。

        它只回答「有没有内容」，不回答「类型合不合法」。类型必须另走
        ``require_scalar``。把这条写成断言，是为了防止后人误以为拿
        ``has_visible_content`` 当类型守卫就够了（P2-A 正是这么漏的）。
        """
        assert has_visible_content([]) is True
        assert has_visible_content({}) is True

    def test_coerce_scalar_only_handles_none_and_bool(self):
        assert coerce_scalar(None) == ""
        assert coerce_scalar(True) == "true"
        assert coerce_scalar(False) == "false"
        assert coerce_scalar(0) == 0
        assert coerce_scalar("0") == "0"
        # 非标量原样返回，不收敛
        assert coerce_scalar([1]) == [1]
        assert coerce_scalar({"a": 1}) == {"a": 1}

    def test_require_scalar_accepts_scalars(self):
        for value in ("x", "0", 0, 0.0, 1, 3.5, True, False, None):
            require_scalar("output", value)  # 不抛即通过

    def test_require_scalar_accepts_normal_float(self):
        assert require_scalar("output", 0.0) == 0.0
        assert require_scalar("output", -1.5) == -1.5

    @pytest.mark.parametrize(
        "value,kind", [([], "list"), ([1], "list"), ({"a": 1}, "dict"), ("_set_", "set")]
    )
    def test_require_scalar_rejects_non_scalar_with_type_hint(self, value, kind):
        if value == "_set_":
            value = {1, 2}
        with pytest.raises(ValueError) as excinfo:
            require_scalar("output", value)
        message = str(excinfo.value)
        assert "output" in message
        assert kind in message, message
        assert "字符串" in message, message

    @pytest.mark.parametrize(
        "value", [float("nan"), float("inf"), float("-inf")]
    )
    def test_require_scalar_rejects_non_finite_float(self, value):
        with pytest.raises(ValueError) as excinfo:
            require_scalar("output", value)
        message = str(excinfo.value)
        assert "output" in message
        assert "float" in message
        assert repr(value) in message, message

    def test_resolve_field_prefers_primary_and_echoes_actual_key(self):
        assert resolve_field({"instruction": "a", "question": "b"}, "instruction", "question") == (
            "instruction",
            "a",
        )
        assert resolve_field({"question": "b"}, "instruction", "question") == ("question", "b")
        assert resolve_field({}, "instruction", "question") == ("instruction", "")

    def test_resolve_field_present_but_none_does_not_fall_back(self):
        """**默认档（导入侧）**：键存在且值为 None 时不回退别名，保留旧 ``item.get`` 语义。

        注意：本条**只覆盖默认档**。评测侧走的是显式开启的一档——
        ``resolve_field(..., fallback_when_none=True)``，其行为由下面
        ``test_resolve_field_opt_in_falls_back_when_none`` 覆盖。
        """
        assert resolve_field({"output": None, "answer": 1}, "output", "answer") == (
            "output",
            None,
        )


# --------------------------------------------------------------------------
# P2-A：评测侧标量守卫
# --------------------------------------------------------------------------

class TestEvaluationScalarGuard:
    """评测侧非标量取值必须 400，且与导入侧口径一致。"""

    @pytest.mark.parametrize(
        "field,value,kind",
        [
            ("output", [], "list"),
            ("output", [1], "list"),
            ("output", {"a": 1}, "dict"),
            ("answer", [], "list"),
            ("instruction", ["a"], "list"),
            ("instruction", {"a": 1}, "dict"),
            ("input", [1, 2], "list"),
        ],
    )
    def test_non_scalar_field_rejected(self, client, field, value, kind):
        model = _model(client, name=f"guard-{field}-{kind}")
        created = _create_eval(client, model["id"], name=f"guard-{field}-{kind}")
        assert created.status_code == 200, created.text
        eval_id = created.json()["id"]

        row = {"instruction": "i", "output": "y"}
        row[field] = value
        if field == "answer":
            # 必须移除 output，否则 resolve_field 会优先命中 output（键存在），
            # 测不到 answer 这一支。
            row.pop("output")
        response = _run_with_test_data(client, eval_id, [row])

        assert response.status_code == 400, response.text
        body = response.text
        assert field in body, body
        assert kind in body, body
        # 给出修正方向
        assert "字符串" in body, body

    def test_non_scalar_rejection_has_no_import_side_effects(self, client):
        """评测侧拒绝不得触碰数据集/标注/任务表，也不留磁盘文件。"""
        model = _model(client, name="guard-side-effect")
        created = _create_eval(client, model["id"], name="guard-side-effect")
        eval_id = created.json()["id"]

        response = _run_with_test_data(
            client, eval_id, [{"instruction": "i", "output": [1]}]
        )
        assert response.status_code == 400, response.text
        counts = _counts()
        assert counts["datasets"] == 0, counts
        assert counts["annotations"] == 0, counts
        assert counts["annotation_tasks"] == 0, counts
        assert counts["orphans"] == 0, counts
        assert _leftover_files() == [], _leftover_files()

    def test_scalar_zero_still_accepted(self, client):
        """正向对照：数值 0 是合法标量，必须照常评测（不能因加守卫而误伤）。"""
        model = _model(client, name="guard-zero")
        created = _create_eval(client, model["id"], name="guard-zero")
        eval_id = created.json()["id"]

        response = _run_with_test_data(
            client,
            eval_id,
            [
                {"instruction": "判断情感", "output": 0},
                {"instruction": "判断情感", "output": 1},
            ],
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"]["exact_match"]["total"] == 2, response.json()

    def test_instruction_zero_renders_as_text_not_replaced(self, client):
        """``instruction=0`` 不得被替换成空串写进 prompt（直接查 prompt 内容）。"""
        from app.models.database import get_session_maker
        from app.services.evaluate_service import EvaluateService

        svc = EvaluateService(get_session_maker()())
        samples = svc.resolve_samples(None, [{"instruction": 0, "output": "0"}])

        assert len(samples) == 1, samples
        assert "0" in samples[0]["prompt"], samples[0]["prompt"]
        assert samples[0]["reference"] == "0", samples[0]

    def test_prompt_uses_coerced_bool_not_python_repr(self):
        """``bool`` 经收敛为 ``"true"``，不得把 Python 的 ``True`` 写进 prompt。"""
        from app.models.database import get_session_maker
        from app.services.evaluate_service import EvaluateService

        svc = EvaluateService(get_session_maker()())
        samples = svc.resolve_samples(None, [{"instruction": True, "output": "y"}])
        assert "true" in samples[0]["prompt"], samples[0]["prompt"]
        assert "True" not in samples[0]["prompt"], samples[0]["prompt"]

    def test_missing_reference_still_skipped(self, client):
        """只有「真的没有值」才跳过：None / "" / 纯空白 / 零宽字符。"""
        model = _model(client, name="guard-skip")
        created = _create_eval(client, model["id"], name="guard-skip")
        eval_id = created.json()["id"]

        response = _run_with_test_data(
            client,
            eval_id,
            [
                {"instruction": "a", "output": None},
                {"instruction": "b", "output": ""},
                {"instruction": "c", "output": "   "},
                {"instruction": "d", "output": "\u200b"},
                {"instruction": "e", "output": 0},
            ],
        )
        assert response.status_code == 200, response.text
        # 前四条无有效参考答案被跳过，仅 output=0 那条进入评测
        assert response.json()["results"]["exact_match"]["total"] == 1, response.json()

    def test_dataset_fallback_still_works_when_test_data_omitted(self, client):
        """回归：不传 test_data 时仍应回退到关联数据集。"""
        model = _model(client, name="fallback")
        dataset = client.post(
            "/api/data/create", json={"name": "fallback-ds"}
        ).json()
        uploaded = _upload(
            client,
            "fb.jsonl",
            b'{"instruction":"a","output":"0"}\n{"instruction":"b","output":"1"}\n',
        )
        assert uploaded.status_code == 200, uploaded.text
        dataset_id = uploaded.json()["id"]

        created = _create_eval(
            client, model["id"], dataset_id=dataset_id, name="fallback"
        )
        assert created.status_code == 200, created.text
        eval_id = created.json()["id"]

        response = client.post(f"/api/evaluate/{eval_id}/run")
        assert response.status_code == 200, response.text
        assert response.json()["results"]["exact_match"]["total"] == 2, response.json()


# --------------------------------------------------------------------------
# P3-1：空列表不回退
# --------------------------------------------------------------------------

class TestEmptyTestDataDoesNotFallBack:
    def test_explicit_empty_list_is_rejected_not_silently_replaced(self, client):
        """``test_data=[]`` 必须报错，不得改用 dataset_id 的数据。"""
        model = _model(client, name="empty-list")
        uploaded = _upload(
            client,
            "el.jsonl",
            b'{"instruction":"a","output":"0"}\n{"instruction":"b","output":"1"}\n',
        )
        assert uploaded.status_code == 200, uploaded.text
        dataset_id = uploaded.json()["id"]

        created = _create_eval(
            client, model["id"], dataset_id=dataset_id, name="empty-list"
        )
        assert created.status_code == 200, created.text
        eval_id = created.json()["id"]

        response = _run_with_test_data(client, eval_id, [])
        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert "空列表" in detail, detail
        # 必须告诉用户怎么才真的会回退
        assert "省略" in detail and "null" in detail, detail

    def test_explicit_null_falls_back_to_dataset(self, client):
        """显式传 null 与「省略」等价，仍应回退到数据集。"""
        model = _model(client, name="null-fallback")
        uploaded = _upload(
            client, "nf.jsonl", b'{"instruction":"a","output":"0"}\n'
        )
        dataset_id = uploaded.json()["id"]
        created = _create_eval(
            client, model["id"], dataset_id=dataset_id, name="null-fallback"
        )
        eval_id = created.json()["id"]

        response = client.post(f"/api/evaluate/{eval_id}/run", json={"test_data": None})
        assert response.status_code == 200, response.text
        assert response.json()["results"]["exact_match"]["total"] == 1, response.json()


# --------------------------------------------------------------------------
# P2-B：非有限浮点
# --------------------------------------------------------------------------

class TestNonFiniteFloatRejected:
    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
    def test_import_rejects_non_finite_float(self, client, literal):
        """``json.loads`` 接受 NaN/Infinity，导入侧必须显式 400 且零副作用。"""
        response = _upload(
            client,
            "nonfinite.jsonl",
            f'{{"instruction":"x","output":{literal}}}\n'.encode("utf-8"),
        )
        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert "output" in detail, detail
        assert "float" in detail, detail
        # 零副作用：不得落库、不得留盘
        assert _counts() == _empty_counts(), _counts()
        assert _leftover_files() == [], _leftover_files()

    def test_import_rejects_non_finite_instruction(self, client):
        response = _upload(
            client,
            "nonfinite-i.jsonl",
            b'{"instruction":NaN,"output":"y"}\n',
        )
        assert response.status_code == 400, response.text
        assert "instruction" in response.json()["detail"]
        assert _counts() == _empty_counts(), _counts()

    @pytest.mark.parametrize("literal", ["NaN", "Infinity", "-Infinity"])
    def test_evaluation_rejects_non_finite_reference(self, client, literal):
        model = _model(client, name=f"nonfinite-{literal}")
        created = _create_eval(client, model["id"], name=f"nonfinite-{literal}")
        eval_id = created.json()["id"]

        body = (
            '{"test_data": [{"instruction": "i", "output": %s}]}' % literal
        ).encode("utf-8")
        response = _run_with_raw_body(client, eval_id, body)

        assert response.status_code == 400, response.text
        assert "output" in response.json()["detail"], response.json()
        assert _counts() == _empty_counts(), _counts()
        assert _leftover_files() == [], _leftover_files()

    def test_import_accepts_finite_floats(self, client):
        """正向对照：有限浮点不得被误伤。"""
        response = _upload(
            client,
            "finite.jsonl",
            b'{"instruction":"x","output":0.5}\n',
        )
        assert response.status_code == 200, response.text
        assert response.json()["total_samples"] == 1

    def test_pandas_style_nan_payload_is_rejected_not_stored_as_null(self, client):
        """``pandas.to_json`` 会产出裸 NaN；必须 400，而不是 ``completed`` + NULL。"""
        payload = b'[{"instruction": "x", "output": NaN}]\n'
        response = _upload(client, "pandas.json", payload)
        assert response.status_code == 400, response.text
        counts = _counts()
        assert counts == _empty_counts(), counts
        # 关键：不得出现 status='completed' 但 output_text IS NULL 的矛盾行
        with get_engine().connect() as conn:
            contradictory = conn.execute(
                text(
                    "SELECT COUNT(*) FROM annotations "
                    "WHERE status = 'completed' AND output_text IS NULL"
                )
            ).scalar()
        assert contradictory == 0, contradictory


# --------------------------------------------------------------------------
# P3-2：顶层结构报真话
# --------------------------------------------------------------------------

class TestJsonTopLevelTypeReported:
    def test_top_level_object_reports_object_not_str(self, client):
        """顶层对象必须说「object」，不能迭代键名后谎报「str」。"""
        payload = json.dumps(
            {"instruction": "a", "output": "0"}, ensure_ascii=False
        ).encode("utf-8")
        response = _upload(client, "toplevel.json", payload)

        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert "数组" in detail, detail
        assert "object" in detail, detail
        # 旧实现会报「解析到类型 str」——那是键名的类型，不是顶层类型
        assert "类型 str" not in detail, detail
        assert _counts() == _empty_counts(), _counts()
        assert _leftover_files() == [], _leftover_files()

    def test_top_level_scalar_reports_its_type(self, client):
        response = _upload(client, "scalar.json", b'"just a string"\n')
        assert response.status_code == 400, response.text
        detail = response.json()["detail"]
        assert "数组" in detail, detail
        assert "str" in detail, detail
        assert _counts() == _empty_counts(), _counts()

    def test_top_level_array_still_imports(self, client):
        """正向对照：数组顶层照常导入。"""
        payload = json.dumps(
            [{"instruction": "a", "output": "0"}], ensure_ascii=False
        ).encode("utf-8")
        response = _upload(client, "arr.json", payload)
        assert response.status_code == 200, response.text
        assert response.json()["total_samples"] == 1

    def test_empty_array_still_reports_empty_file_message(self, client):
        """空数组仍走 A1「没有任何有效记录」，不被顶层校验抢走。"""
        response = _upload(client, "empty-arr.json", b"[]\n")
        assert response.status_code == 400, response.text
        assert "没有任何有效记录" in response.json()["detail"]


# --------------------------------------------------------------------------
# 回归：别名回退在「值为 None」时也必须生效（评测侧独有档）
# --------------------------------------------------------------------------

class TestAliasFallbackWhenValueIsNone:
    """``{"output": None, "answer": "x"}`` 必须回退到 ``answer``。

    这是独立 QA 用 HEAD 树做**真 A/B** 实测发现的回归：把导入侧
    「键存在即取、哪怕值为 None」的语义错误地套到评测侧之后，
    单独一条表现成 400，而**混在一批里会让 ``sample_count`` 从 2 静默降到 1**
    ——HTTP 仍是 200、EM 看起来完全正常。本项目底线点名的最坏一类。

    修法必须**按调用侧区分**，所以 ``resolve_field`` 用显式开关而非改默认语义：
    导入侧的默认档必须保持逐字不变（其错误文案的一字不变依赖于此）。
    """

    def test_resolve_field_default_keeps_import_semantics(self):
        """默认档 = 导入侧语义：primary 键存在即取，值为 None 也不回退。"""
        assert resolve_field({"output": None, "answer": 1}, "output", "answer") == (
            "output",
            None,
        )

    def test_resolve_field_opt_in_falls_back_when_none(self):
        """显式开启 = 评测侧语义：值为 None 也回退，键名回显 alias。"""
        assert resolve_field(
            {"output": None, "answer": 1}, "output", "answer", fallback_when_none=True
        ) == ("answer", 1)
        # 非 None 的 primary 仍然优先
        assert resolve_field(
            {"output": "y", "answer": "x"}, "output", "answer", fallback_when_none=True
        ) == ("output", "y")
        # primary 与 alias 都缺 -> 回显 primary + 空串
        assert resolve_field({}, "output", "answer", fallback_when_none=True) == (
            "output",
            "",
        )
        # primary 为 None 且 alias 也缺 -> 保留 primary 名与 None，
        # 便于错误消息指出用户到底写了哪个字段
        assert resolve_field(
            {"output": None}, "output", "answer", fallback_when_none=True
        ) == ("output", None)

    def test_reference_none_falls_back_to_answer(self, client):
        """单条：``output=None`` + ``answer="1"`` 必须被计入指标，而不是 400。"""
        model = _model(client, name="fallback-ref")
        created = _create_eval(client, model["id"], name="fallback-ref")
        assert created.status_code == 200, created.text

        response = _run_with_test_data(
            client,
            created.json()["id"],
            [{"instruction": "i", "output": None, "answer": "1"}],
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"]["exact_match"]["total"] == 1, response.json()

    def test_mixed_batch_does_not_silently_shrink(self, client):
        """回归判据：混合批次里的样本数**不得**静默变小（必须 2，不是 1）。"""
        model = _model(client, name="fallback-mixed")
        created = _create_eval(client, model["id"], name="fallback-mixed")
        assert created.status_code == 200, created.text

        response = _run_with_test_data(
            client,
            created.json()["id"],
            [
                {"instruction": "i", "output": None, "answer": "1"},
                {"instruction": "i", "output": "1"},
            ],
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"]["exact_match"]["total"] == 2, response.json()

    def test_input_none_falls_back_to_context(self, client):
        """``input=None`` + ``context`` 同样要回退（同一开关覆盖三个字段）。"""
        model = _model(client, name="fallback-ctx")
        created = _create_eval(client, model["id"], name="fallback-ctx")
        assert created.status_code == 200, created.text

        response = _run_with_test_data(
            client,
            created.json()["id"],
            [{"instruction": "i", "input": None, "context": "c", "output": "1"}],
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"]["exact_match"]["total"] == 1, response.json()

    def test_build_prompt_uses_the_resolved_alias_key(self):
        """prompt 侧：``resolve_samples`` 传的是**已解析**的键名，回退必须生效。

        直接测静态方法，避免依赖服务构造。
        """
        from app.services.evaluate_service import EvaluateService

        # 回退命中 alias 时，字典的键就是 alias —— prompt 必须取到值而不是空串
        prompt = EvaluateService.build_prompt({"question": "q", "context": "c"})
        assert "q" in prompt, prompt
        assert "c" in prompt, prompt

        # 键缺失且值为 None 时不得渲染成 "None"
        empty_prompt = EvaluateService.build_prompt({"instruction": None})
        assert "None" not in empty_prompt, empty_prompt

        # 数值 0 是真实内容，必须渲染成 "0"（不得被真值判断吞掉）
        zero_prompt = EvaluateService.build_prompt({"instruction": 0})
        assert "0" in zero_prompt, zero_prompt
