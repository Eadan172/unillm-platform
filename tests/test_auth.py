"""鉴权中间件与 Token 管理的测试。

覆盖：
- 缺失 / 无效 Token -> 401（统一错误体含 ``detail`` + ``error_code``）；
- 双请求头（``Authorization: Bearer`` 与 ``X-API-Token``）均可通过；
- 公开路径（``/health``）不鉴权；
- ``OPTIONS`` 预检不被鉴权拦截；
- **鉴权开关逐请求生效**（不得在中间件构造时快照）；
- Token 自动生成并持久化到 ``api_token_file``。
"""

from __future__ import annotations

import pytest

from app.config import settings
from app.core import security


@pytest.fixture
def auth_on(monkeypatch):
    """打开鉴权并固定一个已知 Token。"""
    monkeypatch.setattr(settings.app, "auth_enabled", True)
    monkeypatch.setattr(settings.app, "api_token", "test-token")
    security.reset_token_cache()
    yield
    security.reset_token_cache()


class TestAuthRequired:
    def test_missing_token_returns_401(self, client, auth_on):
        response = client.get("/api/data/list")
        assert response.status_code == 401
        body = response.json()
        assert body["error_code"] == "UNAUTHORIZED"
        assert body["detail"] == "未提供访问令牌"
        assert "hint" in body

    def test_invalid_token_returns_401(self, client, auth_on):
        response = client.get(
            "/api/data/list", headers={"Authorization": "Bearer wrong-token"}
        )
        assert response.status_code == 401
        assert response.json()["detail"] == "访问令牌无效"

    def test_bearer_header_allows(self, client, auth_on):
        response = client.get(
            "/api/data/list", headers={"Authorization": "Bearer test-token"}
        )
        assert response.status_code == 200
        assert response.json() == []

    def test_x_api_token_header_allows(self, client, auth_on):
        response = client.get("/api/data/list", headers={"X-API-Token": "test-token"})
        assert response.status_code == 200

    def test_v1_paths_are_protected(self, client, auth_on):
        assert client.get("/v1/models").status_code == 401
        assert (
            client.get(
                "/v1/models", headers={"Authorization": "Bearer test-token"}
            ).status_code
            == 200
        )

    def test_verify_endpoint_requires_valid_token(self, client, auth_on):
        assert client.get("/api/auth/verify").status_code == 401
        ok = client.get(
            "/api/auth/verify", headers={"Authorization": "Bearer test-token"}
        )
        assert ok.status_code == 200
        body = ok.json()
        assert body["valid"] is True
        assert body["auth_enabled"] is True


class TestPublicPaths:
    def test_health_is_public(self, client, auth_on):
        assert client.get("/health").status_code == 200

    def test_options_preflight_is_exempt(self, client, auth_on):
        # 预检请求不带 Token，绝不能被鉴权拦成 401
        response = client.options("/api/data/list")
        assert response.status_code != 401


class TestAuthSwitch:
    def test_disabled_by_default_in_tests(self, client):
        # conftest 关闭了鉴权，本地开发/测试无需 Token
        assert client.get("/api/data/list").status_code == 200

    def test_switch_is_read_per_request(self, client, monkeypatch):
        """中间件必须逐请求读取开关，不得在构造时快照。

        同一个 TestClient 会话内切换开关，两次结果必须不同。
        """
        monkeypatch.setattr(settings.app, "api_token", "switch-token")
        security.reset_token_cache()

        monkeypatch.setattr(settings.app, "auth_enabled", True)
        assert client.get("/api/data/list").status_code == 401

        monkeypatch.setattr(settings.app, "auth_enabled", False)
        assert client.get("/api/data/list").status_code == 200

        monkeypatch.setattr(settings.app, "auth_enabled", True)
        assert (
            client.get(
                "/api/data/list",
                headers={"Authorization": "Bearer switch-token"},
            ).status_code
            == 200
        )


class TestTokenResolution:
    def test_configured_token_wins(self, monkeypatch):
        monkeypatch.setattr(settings.app, "api_token", "configured")
        security.reset_token_cache()
        assert security.resolve_token() == "configured"

    def test_token_auto_generated_and_persisted(self, tmp_path, monkeypatch):
        token_file = tmp_path / ".api_token"
        monkeypatch.setattr(settings.app, "api_token", "")
        monkeypatch.setattr(settings.app, "api_token_file", str(token_file))
        security.reset_token_cache()

        token = security.resolve_token()
        assert token
        assert token_file.exists()
        assert token_file.read_text(encoding="utf-8").strip() == token

        # 清空缓存后重新解析应读到同一个持久化 Token（而非重新生成）
        security.reset_token_cache()
        assert security.resolve_token() == token

    def test_verify_token_constant_time_compare(self, monkeypatch):
        monkeypatch.setattr(settings.app, "api_token", "abc123")
        security.reset_token_cache()
        assert security.verify_token("abc123") is True
        assert security.verify_token("abc124") is False
        assert security.verify_token("") is False
        assert security.verify_token(None) is False
