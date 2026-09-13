"""评测参考答案的「falsy 合法值」回归测试。

覆盖 P1：内联 ``test_data`` 里参考答案为数值 ``0`` 的样本会被静默丢弃。

旧实现（``app/services/evaluate_service.py::resolve_samples``）::

    reference = item.get("output") or item.get("answer") or ""
    if not str(reference).strip():
        continue  # 没有参考答案的样本无法参与指标计算

数值 ``0`` 是 falsy，``0 or ... or ""`` 得到 ``""``，于是一条**带合法答案 0**
的样本被当成「没有参考答案」静默 ``continue`` 掉。用户传 4 条样本、平台只评测 2 条
却照常报出 ``exact_match``，且不解释为什么少了 2 条——不报错、数字合理、结论错误。

本案例的情感标签正是 0/1，所以这是最容易踩到的取值。

注意：只有内联 ``test_data`` 受影响。走 ``dataset_id`` 时 ``ann.output_text`` 从
TEXT 列读回来是字符串 ``'0'``（truthy），不受影响——这也是案例包没踩到的原因
（案例包映射 label 时转成了 ``str``）。
"""

import pytest

from app.api.deps import reset_inference_service
from app.services.inference_service import InferenceService, ScriptedBackend


def _model(client, name="eval-repo-target"):
    return client.post("/api/model/register", params={"name": name}).json()


def _create_eval(client, model_id: int, name="内联 falsy"):
    response = client.post(
        "/api/evaluate/create",
        json={
            "model_id": model_id,
            "eval_name": name,
            "metrics": ["exact_match"],
        },
    )
    assert response.status_code == 200, response.text
    return response.json()


def _script_predictions(predictions):
    """注入确定性后端，让预测值完全可控。"""
    service = InferenceService()
    service.set_backend(ScriptedBackend(list(predictions)))
    reset_inference_service(service)


def _run(client, eval_id: int, test_data):
    return client.post(f"/api/evaluate/{eval_id}/run", json={"test_data": test_data})


class TestFalsyReferencesAreRealAnswers:
    """数值 0 / 0.0 / False 是合法参考答案，必须参与指标计算。"""

    def test_mixed_int_zero_and_one_counts_all_four_samples(self, client):
        """核心用例：2 条 output=0 + 2 条 output=1 ⇒ 样本数必须是 4。

        预测值脚本化为全 "0"，因此正确答案是带 0 的那两条 ⇒ EM = 2/4 = 0.5。
        修复前实测：sample_count=2、EM=0.0（一半数据被静默丢弃）。
        """
        model = _model(client)
        created = _create_eval(client, model["id"])
        _script_predictions(["0", "0", "0", "0"])

        response = _run(
            client,
            created["id"],
            [
                {"instruction": "判断情感", "output": 0},
                {"instruction": "判断情感", "output": 0},
                {"instruction": "判断情感", "output": 1},
                {"instruction": "判断情感", "output": 1},
            ],
        )
        assert response.status_code == 200, response.text
        results = response.json()["results"]

        assert results["sample_count"] == 4, results
        assert results["exact_match"] == {
            "value": 0.5,
            "correct": 2,
            "total": 4,
        }, results

    def test_all_int_zero_answers_evaluate_instead_of_400(self, client):
        """全部 output=0 时不得报「没有可用的评测数据」，而是正常评测出 EM=1.0。"""
        model = _model(client)
        created = _create_eval(client, model["id"])
        _script_predictions(["0", "0"])

        response = _run(
            client,
            created["id"],
            [
                {"instruction": "判断情感", "output": 0},
                {"instruction": "判断情感", "output": 0},
            ],
        )
        assert response.status_code == 200, response.text
        results = response.json()["results"]

        assert results["sample_count"] == 2, results
        assert results["exact_match"]["value"] == 1.0, results
        assert results["exact_match"]["total"] == 2, results

    def test_float_zero_reference_is_kept(self, client):
        """output=0.0（float）同样不能被丢弃。"""
        model = _model(client)
        created = _create_eval(client, model["id"])
        _script_predictions(["0.0"])

        response = _run(
            client,
            created["id"],
            [{"instruction": "判断情感", "output": 0.0}],
        )
        assert response.status_code == 200, response.text
        results = response.json()["results"]
        assert results["sample_count"] == 1, results
        assert results["exact_match"]["value"] == 1.0, results

    def test_answer_alias_with_zero_is_kept(self, client):
        """走 ``answer`` 别名且值为 0 时也不能被丢弃。"""
        model = _model(client)
        created = _create_eval(client, model["id"])
        _script_predictions(["0"])

        response = _run(
            client,
            created["id"],
            [{"instruction": "判断情感", "answer": 0}],
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"]["sample_count"] == 1


class TestTrulyMissingReferencesStillSkipped:
    """反向回归：真正没有参考答案的样本仍必须跳过（不能为了修 0 而放行空值）。"""

    @pytest.mark.parametrize(
        "sample",
        [
            {"instruction": "判断情感"},
            {"instruction": "判断情感", "output": None},
            {"instruction": "判断情感", "answer": None},
            {"instruction": "判断情感", "output": ""},
            {"instruction": "判断情感", "output": "   "},
            {"instruction": "判断情感", "output": "\u200b"},
        ],
    )
    def test_sample_without_reference_is_skipped(self, client, sample):
        """仅 1 条无答案样本 ⇒ 没有可用样本，仍应 400 且带既有消息。"""
        model = _model(client)
        created = _create_eval(client, model["id"])
        _script_predictions(["0"])

        response = _run(client, created["id"], [sample])
        assert response.status_code == 400, response.text
        assert "没有可用的评测数据" in response.text, response.text

    def test_mixed_missing_and_present_keeps_only_present(self, client):
        """2 条有答案 + 2 条无答案 ⇒ 只评测 2 条（无答案的确实该跳过）。"""
        model = _model(client)
        created = _create_eval(client, model["id"])
        _script_predictions(["0", "0"])

        response = _run(
            client,
            created["id"],
            [
                {"instruction": "判断情感", "output": 0},
                {"instruction": "判断情感", "output": 1},
                {"instruction": "判断情感", "output": None},
                {"instruction": "判断情感"},
            ],
        )
        assert response.status_code == 200, response.text
        results = response.json()["results"]
        assert results["sample_count"] == 2, results
        assert results["exact_match"]["value"] == 0.5, results
