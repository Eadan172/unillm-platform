"""统一错误契约的测试。

覆盖：
- 既有 ``HTTPException`` 的 ``detail`` 被逐字保留，并补上 ``error_code``；
- 422 校验错误给中文摘要，不是 Pydantic 英文原文；
- 未捕获异常返回 500 固定文案，**不泄露** 堆栈与内部信息。
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from starlette.testclient import TestClient

from app.core.errors import error_body, humanize_validation, register_exception_handlers


class _Item(BaseModel):
    """校验用请求模型。必须定义在模块级，原因见 ``TestValidationHumanized`` 注释。"""

    count: int


@pytest.fixture
def boom_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/bad")
    async def bad_request():
        raise HTTPException(status_code=400, detail="没有可用的数据样本")

    @app.get("/missing")
    async def missing():
        raise HTTPException(status_code=404, detail="Dataset not found")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("secret-internal-detail-should-not-leak")

    return app


@pytest.fixture
def boom_client(boom_app: FastAPI) -> TestClient:
    # raise_server_exceptions=False：让全局 500 处理器真正产出响应
    return TestClient(boom_app, raise_server_exceptions=False)


class TestHttpExceptionContract:
    def test_detail_preserved_and_error_code_added(self, boom_client):
        response = boom_client.get("/bad")
        assert response.status_code == 400
        body = response.json()
        assert body["detail"] == "没有可用的数据样本"
        assert body["error_code"] == "BAD_REQUEST"
        assert "hint" in body

    def test_404_maps_to_not_found(self, boom_client):
        response = boom_client.get("/missing")
        assert response.status_code == 404
        body = response.json()
        assert body["detail"] == "Dataset not found"
        assert body["error_code"] == "NOT_FOUND"


class TestUnhandledException:
    def test_returns_500_without_leaking_traceback(self, boom_client):
        response = boom_client.get("/boom")
        assert response.status_code == 500
        body = response.json()
        assert body["detail"] == "服务器内部错误"
        assert body["error_code"] == "INTERNAL_ERROR"
        # 内部异常文本与堆栈绝不能出现在响应中
        assert "secret-internal-detail-should-not-leak" not in response.text
        assert "Traceback" not in response.text


class TestValidationHumanized:
    # 注意：请求模型必须是**模块级**定义，不能写在测试函数内部。
    # 本模块启用了 ``from __future__ import annotations``，函数内定义的类会让
    # 注解变成字符串（ForwardRef），而 Pydantic 在**模块**命名空间里解析它，
    # 于是抛 ``PydanticUndefinedAnnotation: name 'Item' is not defined``，
    # 表现为路由注册阶段就报错（与断言无关，测试会直接 error）。
    def test_missing_field_is_humanized(self, boom_app: FastAPI):
        @boom_app.post("/items")
        async def create_item(item: _Item):  # pragma: no cover - 仅注册路由
            return {"ok": True}

        client = TestClient(boom_app)
        response = client.post("/items", json={})
        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert "请求参数校验失败" in body["detail"]
        assert "缺失必填项" in body["detail"]

    def test_wrong_type_is_humanized(self, boom_app: FastAPI):
        @boom_app.post("/typed")
        async def create_typed(item: _Item):  # pragma: no cover
            return {"ok": True}

        client = TestClient(boom_app)
        response = client.post("/typed", json={"count": "不是数字"})
        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert "请求参数校验失败" in body["detail"]
        # 不得直接把 Pydantic 英文原文抛给用户
        assert "Input should be" not in body["detail"]


class TestHelpers:
    def test_error_body_shape(self):
        assert error_body("x") == {"detail": "x", "error_code": None, "hint": None}

    def test_humanize_empty(self):
        assert humanize_validation([]) == "请求参数校验失败"


class TestRealAppErrorContract:
    def test_body_validation_maps_to_chinese(self, client):
        """真实端点的请求体校验必须返回中文摘要（location=请求体）。"""
        response = client.post("/api/data/create", json={})
        assert response.status_code == 422
        body = response.json()
        assert body["error_code"] == "VALIDATION_ERROR"
        assert "请求体" in body["detail"]
        assert "缺失必填项" in body["detail"]

    def test_export_without_samples_keeps_detail(self, client):
        """既有 /export 的 400 detail 必须原样保留（三处断言依赖）。"""
        created = client.post(
            "/api/data/import",
            params={"name": "unlabeled-contract"},
            files={"file": ("u.jsonl", b'{"instruction":"x"}\n', "application/json")},
        ).json()
        response = client.get(f"/api/data/{created['id']}/export")
        assert response.status_code == 400
        body = response.json()
        assert "没有已标注" in body["detail"]
        assert body["error_code"] == "BAD_REQUEST"
