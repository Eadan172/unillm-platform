"""上传安全与 API 契约测试。

对应修复：
- 文件类型校验前置（原实现先落盘、先建数据集，最后才校验扩展名）
- 文件名净化，阻断路径穿越
- 解析失败时回滚已落盘文件与数据库记录
- 导出接口在无样本/数据集不存在时给出正确状态码
"""

import json
from pathlib import Path

import pytest

from app.api.routes.data import _safe_filename
from app.config import settings


class TestSafeFilename:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("data.jsonl", "data.jsonl"),
            ("../../etc/passwd.json", "passwd.json"),
            ("..\\..\\windows\\evil.csv", "evil.csv"),
            ("sub/dir/file.jsonl", "file.jsonl"),
            ("训练数据.csv", "训练数据.csv"),
            ("weird name!.jsonl", "weird_name_.jsonl"),
        ],
    )
    def test_sanitizes_dangerous_names(self, raw, expected):
        assert _safe_filename(raw) == expected

    @pytest.mark.parametrize("raw", ["", "..", ".", "../..", "/", "///"])
    def test_rejects_unusable_names(self, raw):
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            _safe_filename(raw)
        assert exc.value.status_code == 400


class TestUploadValidation:
    def _upload(self, client, filename, content=b'{"instruction":"a","output":"b"}\n'):
        return client.post(
            "/api/data/import",
            params={"name": "ds"},
            files={"file": (filename, content, "application/octet-stream")},
        )

    def test_unsupported_extension_rejected_before_persisting(self, client):
        response = self._upload(client, "malware.exe")
        assert response.status_code == 400
        # 关键：不得留下孤儿数据集，也不得把文件写进存储目录
        assert client.get("/api/data/list").json() == []
        dataset_dir = Path(settings.storage.datasets_path)
        assert not (dataset_dir / "malware.exe").exists()

    def test_no_extension_rejected(self, client):
        assert self._upload(client, "README").status_code == 400

    def test_path_traversal_cannot_escape_storage_dir(self, client):
        response = self._upload(client, "../../../evil.jsonl")
        assert response.status_code == 200, response.text

        dataset_dir = Path(settings.storage.datasets_path).resolve()
        written = list(dataset_dir.glob("*.jsonl"))
        assert len(written) == 1
        # 文件必须落在存储目录内
        assert written[0].resolve().parent == dataset_dir
        assert written[0].name == "evil.jsonl"

    def test_malformed_jsonl_rolls_back_everything(self, client):
        response = self._upload(client, "broken.jsonl", b"{not valid json}\n")
        assert response.status_code == 400
        assert client.get("/api/data/list").json() == []
        assert not list(Path(settings.storage.datasets_path).glob("broken.jsonl"))

    def test_csv_import_without_pandas(self, client):
        """CSV 分支已从 pandas 改为标准库 csv。"""
        csv_bytes = (
            "instruction,input,output\n"
            "1+1=?,,\u0032\n"
            "首都,,北京\n"
        ).encode("utf-8")
        response = self._upload(client, "qa.csv", csv_bytes)
        assert response.status_code == 200, response.text
        assert response.json()["total_samples"] == 2

        dataset_id = response.json()["id"]
        exported = client.get(f"/api/data/{dataset_id}/export")
        assert exported.status_code == 200
        rows = [
            json.loads(line)
            for line in Path(exported.json()["output_path"]).read_text("utf-8").splitlines()
        ]
        assert len(rows) == 2
        assert rows[0]["output"] == "2"


class TestDatasetContracts:
    def test_missing_dataset_returns_404(self, client):
        assert client.get("/api/data/99999").status_code == 404
        assert client.delete("/api/data/99999").status_code == 404
        assert client.get("/api/data/99999/export").status_code == 404

    def test_export_without_labelled_samples_returns_400(self, client):
        """导入一份没有答案的数据 => 无法导出训练数据，必须明确报错。"""
        payload = ('{"instruction":"没有答案"}\n').encode("utf-8")
        created = client.post(
            "/api/data/import",
            params={"name": "unlabeled"},
            files={"file": ("u.jsonl", payload, "application/json")},
        ).json()

        response = client.get(f"/api/data/{created['id']}/export")
        assert response.status_code == 400
        assert "没有已标注" in response.json()["detail"]

    def test_delete_removes_dataset(self, client, sample_jsonl):
        with open(sample_jsonl, "rb") as handle:
            dataset = client.post(
                "/api/data/import",
                params={"name": "to-delete"},
                files={"file": ("s.jsonl", handle, "application/json")},
            ).json()

        assert client.delete(f"/api/data/{dataset['id']}").status_code == 200
        assert client.get(f"/api/data/{dataset['id']}").status_code == 404
        assert client.get("/api/data/list").json() == []
