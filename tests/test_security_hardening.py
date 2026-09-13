"""安全加固与契约回归测试（QA 独立验证补充）。

本文件由 QA 独立编写，用于覆盖既有 ``test_auth.py`` / ``test_errors.py``
**未覆盖**的对抗性场景与跨文件契约：

1. 鉴权绕过尝试（大小写 / 双斜杠 / 路径穿越 / URL 编码 / 尾斜杠）；
2. 请求头伪造组合；
3. 公开面（``/docs``、``/openapi.json``、``/console``）不泄露业务数据；
4. 导出下载的 ``Content-Disposition`` 头注入防护；
5. ``/export`` 与 ``/export/download`` 错误语义一致性；
6. 扩展错误码（405 / 413）仍含统一三键；
7. 配置三处版本一致；``.gitignore`` / ``.dockerignore`` 密钥排除。

约定：``conftest`` 默认 ``auth_enabled=False``，需要鉴权的用例自行用
``auth_on`` 夹具打开并固定 Token。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import PROJECT_ROOT, settings
from app.core import security

API_TOKEN = "hardening-token"


@pytest.fixture
def auth_on(monkeypatch):
    """打开鉴权并固定一个已知 Token（与既有 test_auth 保持一致）。"""
    monkeypatch.setattr(settings.app, "auth_enabled", True)
    monkeypatch.setattr(settings.app, "api_token", API_TOKEN)
    security.reset_token_cache()
    yield
    security.reset_token_cache()


def _bearer(token: str = API_TOKEN) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _import_labeled(client, name: str) -> dict:
    """导入一份自带答案的数据集（导入后即为已标注状态）。"""
    payload = json.dumps({"instruction": "1+1=?", "output": "2"}, ensure_ascii=False)
    response = client.post(
        "/api/data/import",
        params={"name": name},
        files={"file": ("data.jsonl", payload.encode("utf-8"), "application/json")},
        headers=_bearer(),
    )
    assert response.status_code == 200, response.text
    return response.json()


class TestAuthBypassAttempts:
    """受保护路径的绕过尝试：绝不允许返回 200（放行）。"""

    @pytest.mark.parametrize(
        "label,path",
        [
            ("大小写", "/API/data/list"),
            ("大小写混合", "/Api/data/list"),
            ("路径穿越", "/api/../api/data/list"),
            ("console 穿越", "/console/../api/data/list"),
            ("双斜杠", "//api/data/list"),
            ("尾斜杠", "/api/data/list/"),
            ("百分号编码", "/%61pi/data/list"),
            ("斜杠编码", "/api%2Fdata/list"),
        ],
    )
    def test_no_bypass_returns_200(self, client, auth_on, label, path):
        response = client.get(path)
        assert response.status_code in (401, 404), (
            f"{label} {path} 意外放行：{response.status_code} {response.text[:120]}"
        )

    @pytest.mark.parametrize(
        "path",
        [
            "/v1/models",
            "/api/model/list",
            "/api/evaluate/list",
            "/api/finetune/list",
            "/api/auth/verify",
            "/api/info",
            "/api/model/backend",
        ],
    )
    def test_protected_endpoints_require_token(self, client, auth_on, path):
        assert client.get(path).status_code == 401
        assert client.get(path, headers=_bearer()).status_code == 200


class TestHeaderForgery:
    """请求头伪造组合。"""

    @pytest.mark.parametrize(
        "label,headers",
        [
            ("空 Bearer", {"Authorization": "Bearer "}),
            ("缺 Bearer 前缀", {"Authorization": API_TOKEN}),
            ("仅 Bearer 关键字", {"Authorization": "Bearer"}),
            ("错误 X-API-Token", {"X-API-Token": "wrong"}),
            ("空 X-API-Token", {"X-API-Token": ""}),
            ("错误 Authorization", {"Authorization": "Bearer wrong"}),
            # Authorization 优先：即使 X-API-Token 正确，错误的 Authorization 仍拒绝
            ("坏 Auth + 好 X-API-Token", {"Authorization": "Bearer wrong", "X-API-Token": API_TOKEN}),
        ],
    )
    def test_forged_headers_rejected(self, client, auth_on, label, headers):
        assert client.get("/api/data/list", headers=headers).status_code == 401, label

    def test_x_api_token_used_when_authorization_absent(self, client, auth_on):
        response = client.get("/api/data/list", headers={"X-API-Token": API_TOKEN})
        assert response.status_code == 200


class TestPublicSurface:
    """公开面只暴露接口结构，不含任何业务数据或密钥。"""

    @pytest.mark.parametrize(
        "path", ["/docs", "/redoc", "/openapi.json", "/console/", "/health"]
    )
    def test_public_paths_reachable_without_token(self, client, auth_on, path):
        assert client.get(path).status_code == 200

    def test_openapi_leaks_no_secrets(self, client, auth_on):
        raw = client.get("/openapi.json").text
        for secret in (API_TOKEN, ".api_token", "unillm.db", "password"):
            assert secret.lower() not in raw.lower(), f"openapi 泄露敏感串：{secret}"

    def test_root_redirects_to_console(self, client, auth_on):
        response = client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.headers["location"] == "/console/"


class TestDownloadHeaderInjection:
    """导出下载的 Content-Disposition 头注入防护。"""

    @pytest.mark.parametrize(
        "raw_name",
        [
            'evil";X-Injected: 1',
            "line1\nline2\r\nContent-Length: 0",
            "../../etc/passwd",
            "a/b/c",
            "中文数据集名",
            "A" * 300,
            'quote"name',
        ],
    )
    def test_content_disposition_sanitized(self, client, auth_on, raw_name):
        dataset = _import_labeled(client, raw_name)
        response = client.get(
            f"/api/data/{dataset['id']}/export/download", headers=_bearer()
        )
        assert response.status_code == 200
        disposition = response.headers.get("content-disposition", "")
        # 头值不得含裸换行 / 制表符，且引号必须成对（防头注入）
        assert "\n" not in disposition and "\r" not in disposition
        assert disposition.count('"') % 2 == 0

    def test_download_and_export_share_error_semantics(self, client, auth_on):
        unlabeled = client.post(
            "/api/data/import",
            params={"name": "unlabeled"},
            files={"file": ("u.jsonl", b'{"instruction":"x"}\n', "application/json")},
            headers=_bearer(),
        ).json()
        export = client.get(f"/api/data/{unlabeled['id']}/export", headers=_bearer())
        download = client.get(
            f"/api/data/{unlabeled['id']}/export/download", headers=_bearer()
        )
        assert export.status_code == download.status_code == 400
        assert export.json()["detail"] == download.json()["detail"]

    def test_legacy_export_still_returns_json(self, client, auth_on):
        dataset = _import_labeled(client, "legacy-export")
        response = client.get(f"/api/data/{dataset['id']}/export", headers=_bearer())
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "success"
        assert Path(body["output_path"]).exists()


class TestExtendedErrorContract:
    """405 / 413 也必须返回含 detail 的统一错误体。"""

    def test_405_has_unified_body(self, client, auth_on):
        response = client.request("DELETE", "/v1/models", headers=_bearer())
        assert response.status_code == 405
        body = response.json()
        assert set(("detail", "error_code", "hint")) <= set(body)
        assert body["error_code"] == "METHOD_NOT_ALLOWED"

    def test_413_has_unified_body(self, client, auth_on):
        from app.api.routes import data as data_route

        original = data_route.MAX_UPLOAD_BYTES
        data_route.MAX_UPLOAD_BYTES = 10
        try:
            response = client.post(
                "/api/data/import",
                params={"name": "too-big"},
                files={"file": ("big.jsonl", b"x" * 200, "application/json")},
                headers=_bearer(),
            )
        finally:
            data_route.MAX_UPLOAD_BYTES = original
        assert response.status_code == 413
        body = response.json()
        assert set(("detail", "error_code", "hint")) <= set(body)
        assert body["error_code"] == "PAYLOAD_TOO_LARGE"

    def test_validation_detail_is_chinese(self, client, auth_on):
        response = client.post("/api/data/create", json={}, headers=_bearer())
        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "请求参数校验失败" in detail
        assert "Input should be" not in detail

    def test_cors_preflight_not_blocked_by_auth(self, client, auth_on):
        response = client.options(
            "/api/data/list",
            headers={
                "Origin": "https://example.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        assert response.status_code != 401
        assert response.headers.get("access-control-allow-origin")


class TestConfigIntegrity:
    """版本一致性与密钥排除的跨文件契约。"""

    def test_version_consistent_across_sources(self):
        import yaml

        from app.main import app as fastapi_app

        yaml_version = yaml.safe_load(
            (PROJECT_ROOT / "config.yaml").read_text(encoding="utf-8")
        )["app"]["version"]
        assert settings.app.version == yaml_version == fastapi_app.version == "0.3.0"

    def test_gitignore_ignores_api_token(self):
        text = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
        assert "data/.api_token" in text

    def test_dockerignore_excludes_runtime_data(self):
        text = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")
        lines = {line.strip() for line in text.splitlines()}
        assert ".git" in lines
        assert "__pycache__" in lines
        assert "data" in lines  # 覆盖 data/.api_token（密钥）
        assert "logs" in lines
