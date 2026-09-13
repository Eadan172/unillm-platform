"""鉴权探针与平台信息端点。

- ``GET /api/auth/verify``：受保护的登录探针。能到达这里即代表 Token 有效。
- ``GET /api/info``：原根路径 ``/`` 的 JSON 信息迁移目标（受保护）。
  登录页不展示版本号，因此本端点归入受保护范围。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.config import settings

router = APIRouter(prefix="/api", tags=["Auth & Info"])


@router.get("/auth/verify")
async def verify_auth():
    """登录探针：请求经鉴权中间件放行即视为校验通过。"""
    return {"valid": True, "auth_enabled": bool(settings.app.auth_enabled)}


@router.get("/info")
async def api_info():
    """平台元信息（受保护）。"""
    return {
        "name": settings.app.name,
        "version": settings.app.version,
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "console": "/console/",
        "auth_enabled": bool(settings.app.auth_enabled),
    }
