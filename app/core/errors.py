"""统一错误响应契约与全局异常处理器。

统一结构（**必须始终包含 ``detail`` 键**，既有测试依赖它）::

    {"detail": "...", "error_code": "BAD_REQUEST", "hint": null}

覆盖三类异常：
1. ``StarletteHTTPException``（含 FastAPI ``HTTPException``）—— 保留原状态码与原 ``detail``；
2. ``RequestValidationError``（422）—— 生成中文摘要，不把 Pydantic 英文原文抛给用户；
3. 未捕获异常（500）—— 固定文案，完整堆栈只进服务端日志，绝不外泄。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Optional

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger("unillm.errors")

# HTTP 状态码 -> 机器可读错误码
_STATUS_TO_CODE: Dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "TOO_MANY_REQUESTS",
    500: "INTERNAL_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
}

# 校验错误位置前缀的中文名
_LOCATION_NAMES: Dict[str, str] = {
    "body": "请求体",
    "query": "查询参数",
    "path": "路径参数",
    "header": "请求头",
    "cookie": "Cookie",
}

# Pydantic 错误类型 -> 中文描述
_TYPE_NAMES: Dict[str, str] = {
    "missing": "缺失必填项",
    "string_type": "应为字符串",
    "int_parsing": "应为整数",
    "int_type": "应为整数",
    "float_parsing": "应为数字",
    "float_type": "应为数字",
    "bool_parsing": "应为布尔值",
    "bool_type": "应为布尔值",
    "list_type": "应为列表",
    "dict_type": "应为对象",
    "json_invalid": "JSON 格式错误",
    "value_error": "取值不合法",
    "type_error": "类型不正确",
    "enum": "取值不在允许范围内",
    "greater_than": "取值过小",
    "less_than": "取值过大",
}


def error_body(
    detail: str,
    error_code: Optional[str] = None,
    hint: Optional[str] = None,
) -> Dict[str, Any]:
    """构造统一错误响应体。``detail`` 键始终存在。"""
    return {"detail": detail, "error_code": error_code, "hint": hint}


def _describe_location(loc: Iterable[Any]) -> str:
    """把 Pydantic 的 ``loc`` 元组翻译成中文位置描述。"""
    items: List[str] = [str(part) for part in loc]
    if not items:
        return "请求"
    prefix = _LOCATION_NAMES.get(items[0], items[0])
    tail = ".".join(items[1:])
    return f"{prefix}.{tail}" if tail else prefix


def humanize_validation(errors: Iterable[Dict[str, Any]]) -> str:
    """把 Pydantic 校验错误列表汇总成一句中文摘要。"""
    fragments: List[str] = []
    for err in errors or []:
        location = _describe_location(err.get("loc", ()))
        err_type = str(err.get("type", ""))
        description = _TYPE_NAMES.get(err_type, str(err.get("msg", "取值不合法")))
        fragments.append(f"{location}：{description}")
    if not fragments:
        return "请求参数校验失败"
    return "请求参数校验失败（" + "；".join(fragments) + "）"


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """保留原状态码与原 ``detail``，补充机器可读 ``error_code``。"""
    raw_detail = getattr(exc, "detail", None)
    if isinstance(raw_detail, str):
        detail = raw_detail
    elif raw_detail is None:
        detail = "请求失败"
    else:
        detail = str(raw_detail)
    code = _STATUS_TO_CODE.get(exc.status_code)
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code,
        content=error_body(detail, code),
        headers=headers,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """422：给出中文摘要，避免把 Pydantic 英文原文直接暴露给用户。"""
    detail = humanize_validation(exc.errors())
    return JSONResponse(
        status_code=422,
        content=error_body(detail, "VALIDATION_ERROR", "请检查请求体字段的类型与必填项"),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """500：固定文案，完整堆栈只写入服务端日志。"""
    logger.exception("未捕获异常 [%s %s]", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=error_body(
            "服务器内部错误",
            "INTERNAL_ERROR",
            "请查看服务端日志以获取详细信息",
        ),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """注册三类全局异常处理器（覆盖 FastAPI 默认实现）。"""
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
