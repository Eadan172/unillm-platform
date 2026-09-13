"""访问令牌解析、校验与持久化，以及全局鉴权中间件。

设计要点（务必保持）
--------------------
1. **逐请求读取开关**：``AuthMiddleware.dispatch`` 每次请求都读取
   ``settings.app.auth_enabled``，**绝不**在中间件构造时把它快照成实例属性。
   测试夹具会在运行时把它改为 ``False``；一旦快照了初始值，所有接口都会 401。
2. **OPTIONS 一律放行**：CORS 预检不带 Token，必须在鉴权之前被放行；
   本模块额外对 ``OPTIONS`` 直接放行，作为中间件顺序之外的双保险。
3. **常量时间比较**：使用 ``secrets.compare_digest`` 避免时序侧信道。
4. **零新增依赖**：全部基于标准库 + starlette（既有依赖）。
"""

from __future__ import annotations

import logging
import secrets
from pathlib import Path
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.config import PROJECT_ROOT, settings
from app.core.errors import error_body

logger = logging.getLogger("unillm.security")

# 需要鉴权的路径前缀。命中其一即视为受保护。
PROTECTED_PREFIXES = ("/api/", "/v1/")

# 进程内 Token 缓存（避免每个请求都读盘）。
_token_cache: Optional[str] = None


def is_protected_path(path: str) -> bool:
    """判断路径是否受鉴权保护（``/api/*`` 与 ``/v1/*``）。"""
    return path.startswith(PROTECTED_PREFIXES)


def extract_token(request: Request) -> Optional[str]:
    """从请求头提取 Token：优先 ``Authorization: Bearer``，其次 ``X-API-Token``。"""
    authorization = request.headers.get("authorization", "")
    if authorization:
        scheme, _, credentials = authorization.partition(" ")
        if scheme.lower() == "bearer" and credentials.strip():
            return credentials.strip()

    fallback = request.headers.get("x-api-token", "")
    if fallback and fallback.strip():
        return fallback.strip()
    return None


def _token_file_path() -> Path:
    """Token 落盘路径：相对路径锚定项目根。"""
    raw = Path(settings.app.api_token_file)
    return raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()


def _persist_token(path: Path, token: str) -> None:
    """把自动生成的 Token 写入磁盘，并尽力收紧文件权限。

    Windows 不支持 POSIX 权限位，``chmod`` 会失败；这不影响服务运行，
    因此全部用 ``try/except`` 包住，绝不让权限设置失败中断启动。
    """
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(token, encoding="utf-8")
    except OSError as exc:  # 磁盘只读等极端情况：不影响服务运行
        logger.warning("无法持久化 API Token 到 %s：%s", path, exc)
        return
    try:
        path.chmod(0o600)
    except OSError:
        # Windows 无 POSIX 权限位；忽略即可。
        pass


def resolve_token() -> str:
    """返回当前生效的 Token：配置优先，其次读盘，最后生成并持久化。"""
    global _token_cache
    if _token_cache:
        return _token_cache

    configured = (settings.app.api_token or "").strip()
    if configured:
        _token_cache = configured
        return _token_cache

    path = _token_file_path()
    if path.exists():
        try:
            existing = path.read_text(encoding="utf-8").strip()
        except OSError:
            existing = ""
        if existing:
            _token_cache = existing
            return _token_cache

    generated = secrets.token_urlsafe(32)
    _token_cache = generated
    _persist_token(path, generated)
    return generated


def ensure_token() -> str:
    """启动时确保 Token 存在并醒目打印。返回当前 Token。"""
    token = resolve_token()
    print_token_banner(token)
    return token


def verify_token(candidate: Optional[str]) -> bool:
    """常量时间比较候选 Token 与期望 Token。"""
    if not candidate:
        return False
    expected = resolve_token()
    if not expected:
        return False
    return secrets.compare_digest(str(candidate), str(expected))


def reset_token_cache() -> None:
    """清空进程内缓存。仅供测试使用（改配置后需要重新解析）。"""
    global _token_cache
    _token_cache = None


def print_token_banner(token: str) -> None:
    """在启动日志中醒目打印 Token，方便部署者转告同事。"""
    border = "=" * 76
    print(border, flush=True)
    print("  UniLLM Platform · 访问令牌（控制台登录用）", flush=True)
    print(f"  Token: {token}", flush=True)
    print(
        "  提示：可用环境变量 UNILLM_APP__API_TOKEN 覆盖；"
        "设置 UNILLM_APP__AUTH_ENABLED=false 可关闭鉴权（本地开发）。",
        flush=True,
    )
    print(border, flush=True)


class AuthMiddleware(BaseHTTPMiddleware):
    """对 ``/api/*`` 与 ``/v1/*`` 做统一 Token 鉴权。"""

    async def dispatch(self, request: Request, call_next):
        # ① 逐请求读取开关 —— 绝不缓存到实例属性（测试会在运行时改它）
        if not settings.app.auth_enabled:
            return await call_next(request)

        # ② CORS 预检直接放行（不带 Token）
        if request.method == "OPTIONS":
            return await call_next(request)

        # ③ 非保护路径放行（/console、/health、/docs 等）
        if not is_protected_path(request.url.path):
            return await call_next(request)

        # ④ 校验 Token
        token = extract_token(request)
        if token is None:
            return JSONResponse(
                status_code=401,
                content=error_body(
                    "未提供访问令牌",
                    "UNAUTHORIZED",
                    "请在请求头携带 Authorization: Bearer <token>（或 X-API-Token）",
                ),
            )
        if not verify_token(token):
            return JSONResponse(
                status_code=401,
                content=error_body(
                    "访问令牌无效",
                    "UNAUTHORIZED",
                    "请确认 Token 与控制台部署配置一致",
                ),
            )
        return await call_next(request)
