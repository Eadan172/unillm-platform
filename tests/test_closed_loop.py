"""端到端闭环测试：数据 → 标注 → 导出 → 模型注册/加载 → 推理 → 评测。

这是"项目确实可运行"的可复现证据。全部通过 HTTP 接口调用，
不依赖 GPU、不下载任何模型权重。
"""

import json
from pathlib import Path

import pytest

from app.api.deps import reset_inference_service
from app.services.inference_service import InferenceService, ScriptedBackend


def _import_dataset(client, sample_jsonl: Path, name: str = "闭环测试数据"):
    with open(sample_jsonl, "rb") as handle:
        response = client.post(
            "/api/data/import",
            params={"name": name, "description": "端到端测试"},
            files={"file": ("sample.jsonl", handle, "application/json")},
        )
    assert response.status_code == 200, response.text
    return response.json()


class TestHealth:
    def test_health_reports_real_state_not_hardcoded_zero(self, client):
        payload = client.get("/health").json()
        assert payload["status"] == "healthy"
        # 原实现把 models_loaded 写死为 0；现在它来自数据库
        assert payload["registered_models"] == 0
        assert payload["models_loaded"] == 0
        # 未装 vLLM 时必须如实声明处于降级状态
        assert payload["inference_backend"] == "mock"
        assert payload["inference_backend_is_real_model"] is False
        assert payload["degraded"] is True
        assert "unillm-test-" in payload["database"]


class TestDataPipeline:
    def test_import_marks_pre_answered_rows_completed(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        assert dataset["total_samples"] == 3
        # 源数据自带答案 => 应直接是可导出的已标注状态
        listing = client.get("/api/data/list").json()
        assert len(listing) == 1
        assert listing[0]["total_samples"] == 3

    def test_export_produces_three_training_rows(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        response = client.get(f"/api/data/{dataset['id']}/export")
        assert response.status_code == 200, response.text
        output_path = Path(response.json()["output_path"])
        assert output_path.exists()
        rows = [json.loads(line) for line in output_path.read_text("utf-8").splitlines()]
        assert len(rows) == 3
        assert {"instruction", "input", "output"} <= set(rows[0])

    def test_annotation_task_tracks_progress(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        task = client.post(
            "/api/annotation/task",
            json={"name": "任务1", "dataset_id": dataset["id"], "annotation_type": "text"},
        ).json()
        assert task["total_items"] == 3

        progress = client.get(f"/api/annotation/task/{task['id']}/progress").json()
        assert progress["total"] == 3
        # 数据导入时已带答案，所以没有任何 pending 项
        assert progress["pending"] == 0

    def test_annotation_task_missing_dataset_returns_404(self, client):
        response = client.post(
            "/api/annotation/task", json={"name": "x", "dataset_id": 99999}
        )
        assert response.status_code == 404


class TestModelAndInference:
    def test_load_model_degrades_honestly_without_vllm(self, client):
        response = client.post(
            "/api/model/load", json={"model_name": "Qwen/Qwen2.5-7B-Instruct"}
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["status"] == "degraded"
        assert payload["backend"] == "mock"
        assert payload["degraded"] is True
        assert "vLLM" in payload["reason"]

        # 降级后端不应把自己标记成已加载的真实模型
        assert client.get("/health").json()["models_loaded"] == 0
        assert client.get("/api/model/backend").json()["is_real_model"] is False

    def test_chat_completion_is_openai_shaped_and_labelled(self, client):
        response = client.post(
            "/v1/chat/completions",
            json={
                "model": "Qwen/Qwen2.5-7B-Instruct",
                "messages": [{"role": "user", "content": "你好"}],
                "max_tokens": 32,
            },
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["object"] == "chat.completion"
        assert payload["backend"] == "mock"
        content = payload["choices"][0]["message"]["content"]
        # 占位文本必须自带标记，避免被当成真实模型输出
        assert content.startswith("[MOCK]")
        assert payload["usage"]["total_tokens"] > 0

    def test_mock_backend_is_deterministic(self, client):
        request = {
            "model": "m",
            "messages": [{"role": "user", "content": "同一个问题"}],
        }
        first = client.post("/v1/chat/completions", json=request).json()
        second = client.post("/v1/chat/completions", json=request).json()
        assert (
            first["choices"][0]["message"]["content"]
            == second["choices"][0]["message"]["content"]
        )

    def test_streaming_is_rejected_explicitly(self, client):
        response = client.post(
            "/v1/chat/completions",
            json={"model": "m", "messages": [{"role": "user", "content": "hi"}], "stream": True},
        )
        assert response.status_code == 400
        assert "stream" in response.json()["detail"]

    def test_completion_endpoint_works(self, client):
        response = client.post(
            "/v1/completions", json={"model": "m", "prompt": "写一首诗", "max_tokens": 16}
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["object"] == "text_completion"
        assert payload["backend"] == "mock"

    def test_models_list_does_not_fabricate_entries(self, client):
        payload = client.get("/v1/models").json()
        assert payload["object"] == "list"
        # 未注册模型时只剩一条"来自配置的默认名"，且被显式标注
        assert len(payload["data"]) == 1
        assert "note" in payload["data"][0]

        client.post("/api/model/register", params={"name": "real-model"})
        payload = client.get("/v1/models").json()
        assert [m["id"] for m in payload["data"]] == ["real-model"]


class TestEvaluation:
    def _setup(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        model = client.post(
            "/api/model/register",
            params={"name": "eval-model", "base_model": "Qwen/Qwen2.5-7B-Instruct"},
        ).json()
        return dataset, model

    def test_evaluation_computes_real_metrics_from_dataset(self, client, sample_jsonl):
        dataset, model = self._setup(client, sample_jsonl)
        created = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "dataset_id": dataset["id"],
                "eval_name": "闭环评测",
                "metrics": ["exact_match", "token_f1", "latency", "perplexity"],
            },
        ).json()

        response = client.post(f"/api/evaluate/{created['id']}/run")
        assert response.status_code == 200, response.text
        results = response.json()["results"]

        assert results["sample_count"] == 3
        assert results["backend"] == "mock"
        assert results["backend_is_real_model"] is False
        # mock 后端输出是确定性占位文本，与参考答案几乎不重合。
        # 断言"分数很低"而不是"恰好为 0"：占位文本可能偶然共享个别字，这是真实计算结果。
        # 关键是它绝不等于原实现里编造的 0.72。
        assert results["exact_match"]["value"] == 0.0
        assert results["token_f1"]["value"] < 0.2
        # 延迟是实测的，必须 > 0
        assert results["latency"]["avg_ms"] > 0
        assert results["latency"]["samples"] == 3
        # 未装 torch 时必须如实声明不可用，不得填占位数字
        assert results["perplexity"]["available"] is False
        assert "torch" in results["perplexity"]["reason"]

    def test_evaluation_with_correct_backend_scores_one(self, client, sample_jsonl):
        """注入确定性后端返回正确答案，验证指标确实在比对参考答案。"""
        dataset, model = self._setup(client, sample_jsonl)

        service = InferenceService()
        service.set_backend(ScriptedBackend(["2", "北京", "H2O"]))
        reset_inference_service(service)

        created = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "dataset_id": dataset["id"],
                "eval_name": "正确后端评测",
                "metrics": ["exact_match", "token_f1"],
            },
        ).json()
        results = client.post(f"/api/evaluate/{created['id']}/run").json()["results"]

        assert results["backend"] == "scripted"
        assert results["exact_match"]["value"] == 1.0
        assert results["token_f1"]["value"] == 1.0

    def test_evaluation_accepts_inline_test_data(self, client):
        model = client.post("/api/model/register", params={"name": "m2"}).json()
        created = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model["id"],
                "eval_name": "内联样本",
                "metrics": ["exact_match"],
            },
        ).json()

        service = InferenceService()
        service.set_backend(ScriptedBackend(["北京"]))
        reset_inference_service(service)

        response = client.post(
            f"/api/evaluate/{created['id']}/run",
            json={"test_data": [{"instruction": "首都", "output": "北京"}]},
        )
        assert response.status_code == 200, response.text
        assert response.json()["results"]["exact_match"]["value"] == 1.0

    def test_evaluation_without_data_fails_loudly(self, client):
        """原实现会静默返回 mock_value 并把状态标成 completed。"""
        model = client.post("/api/model/register", params={"name": "m3"}).json()
        created = client.post(
            "/api/evaluate/create",
            json={"model_id": model["id"], "eval_name": "无数据", "metrics": ["exact_match"]},
        ).json()

        response = client.post(f"/api/evaluate/{created['id']}/run")
        assert response.status_code == 400
        assert "没有可用的评测数据" in response.json()["detail"]

        summary = client.get(f"/api/evaluate/{created['id']}/result").json()
        assert summary["status"] == "failed"
        assert summary["results"]["error"]

    def test_missing_evaluation_returns_404(self, client):
        assert client.get("/api/evaluate/99999/result").status_code == 404


class TestFinetune:
    def test_job_creation_validates_references(self, client):
        assert (
            client.post(
                "/api/finetune/create",
                json={"model_id": 99999, "dataset_id": 99999, "job_name": "x"},
            ).status_code
            == 404
        )

    def test_job_fails_loudly_without_gpu_deps(self, client, sample_jsonl):
        dataset = _import_dataset(client, sample_jsonl)
        model = client.post("/api/model/register", params={"name": "ft-model"}).json()

        job = client.post(
            "/api/finetune/create",
            json={
                "model_id": model["id"],
                "dataset_id": dataset["id"],
                "job_name": "lora-job",
                "method": "lora",
            },
        ).json()

        started = client.post(f"/api/finetune/{job['id']}/start")
        assert started.status_code == 200, started.text

        import time

        status = None
        for _ in range(60):
            status = client.get(f"/api/finetune/{job['id']}/status").json()
            if status["status"] in ("failed", "completed", "cancelled"):
                break
            time.sleep(0.1)

        assert status is not None
        # 未安装 gpu 依赖时必须 failed，并给出可执行的修复提示，不得谎报 completed
        assert status["status"] == "failed"
        assert "requirements-gpu.txt" in status["error_message"]


class TestPaginationGuards:
    @pytest.mark.parametrize(
        "url",
        ["/api/data/list?skip=-1", "/api/model/list?limit=0", "/api/evaluate/list?skip=-5"],
    )
    def test_invalid_pagination_rejected(self, client, url):
        assert client.get(url).status_code == 400
