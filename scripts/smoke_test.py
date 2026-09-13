#!/usr/bin/env python
"""UniLLM Platform 端到端冒烟验证。

与 tests/ 下的 pytest 用例不同，本脚本启动的是**真实的 uvicorn 进程**，
通过 HTTP 打全链路，用来证明"服务真的能被启动并对外提供服务"，而不只是
在 TestClient 的内存桩里通过。

流程：
    1. 以子进程方式启动 uvicorn（独立端口，独立临时数据目录）
    2. 轮询 /health 直到服务就绪（或超时失败）
    3. 依次调用：建数据集 -> 上传数据 -> 建模型 -> 聊天补全 -> 建评测 -> 跑评测
    4. 校验关键返回值（backend=mock、指标为真实计算值、延迟 > 0）
    5. 关闭服务并输出 PASS/FAIL 汇总

用法：
    python scripts/smoke_test.py
    python scripts/smoke_test.py --port 8123

退出码 0 表示全部通过，非 0 表示存在失败项。
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 冒烟专用固定 Token（与子进程环境变量一致）
SMOKE_TOKEN = "smoke-token"

try:
    import httpx
except ImportError:  # pragma: no cover
    print("缺少依赖 httpx，请先执行: pip install -r requirements.txt")
    raise SystemExit(2)


class SmokeFailure(Exception):
    """标记一个明确的失败点。"""


_CHECKS: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _CHECKS.append((name, ok, detail))
    mark = "PASS" if ok else "FAIL"
    line = f"  [{mark}] {name}"
    if detail:
        line += f" -- {detail}"
    print(line, flush=True)


def wait_for_health(base_url: str, timeout: float = 40.0) -> dict:
    """轮询 /health，直到服务就绪。"""
    deadline = time.time() + timeout
    last_error = ""
    while time.time() < deadline:
        try:
            resp = httpx.get(f"{base_url}/health", timeout=3.0)
            if resp.status_code == 200:
                return resp.json()
            last_error = f"HTTP {resp.status_code}"
        except Exception as exc:  # 连接被拒是正常现象，服务还没起来
            last_error = type(exc).__name__
        time.sleep(0.5)
    raise SmokeFailure(f"服务在 {timeout}s 内未就绪（最后错误: {last_error}）")


def start_server(port: int, data_dir: Path) -> subprocess.Popen:
    """启动真实 uvicorn 子进程。"""
    env = os.environ.copy()
    # 用临时目录承载数据库与存储，避免污染项目里的 data/
    env["UNILLM_DATABASE__PATH"] = str(data_dir / "smoke.db")
    env["UNILLM_STORAGE__DATASETS_PATH"] = str(data_dir / "datasets")
    env["UNILLM_STORAGE__ANNOTATIONS_PATH"] = str(data_dir / "annotations")
    env["UNILLM_STORAGE__MODELS_PATH"] = str(data_dir / "models")
    env["UNILLM_STORAGE__LOGS_PATH"] = str(data_dir / "logs")
    env["UNILLM_APP__DEBUG"] = "false"
    # 固定一个团队 Token：/api/* 与 /v1/* 需要它，/health 公开无需它
    env["UNILLM_APP__API_TOKEN"] = SMOKE_TOKEN
    env["UNILLM_APP__AUTH_ENABLED"] = "true"

    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--log-level",
            "warning",
        ],
        cwd=str(PROJECT_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def run_flow(base_url: str, sample_jsonl: Path, data_dir: Path) -> None:
    """跑通全链路并逐项校验。"""
    # --- 0) 鉴权：无 Token 访问受保护端点必须 401；公开端点仍需可访问 ---
    anon = httpx.get(f"{base_url}/api/data/list", timeout=10.0)
    check(
        "无 Token 访问受保护端点返回 401",
        anon.status_code == 401,
        f"status={anon.status_code}",
    )
    anon_health = httpx.get(f"{base_url}/health", timeout=10.0)
    check(
        "公开端点 /health 无需 Token 即可访问",
        anon_health.status_code == 200,
        f"status={anon_health.status_code}",
    )

    with httpx.Client(
        base_url=base_url,
        timeout=30.0,
        headers={"Authorization": f"Bearer {SMOKE_TOKEN}"},
    ) as client:
        # --- 1) 健康检查暴露真实状态 ---
        health = client.get("/health").json()
        check("GET /health 返回 200 且含后端信息", "inference_backend" in health,
              f"backend={health.get('inference_backend')}")
        check("health.degraded 与后端真实性一致",
              health.get("degraded") == (not health.get("inference_backend_is_real_model")),
              f"degraded={health.get('degraded')}")
        check("health 报出真实注册模型数（初始为 0）", health.get("registered_models") == 0,
              f"registered_models={health.get('registered_models')}")

        # --- 2) 上传数据（import 一步完成"建数据集 + 导入"） ---
        payload = sample_jsonl.read_bytes()
        up = client.post(
            "/api/data/import",
            params={"name": "smoke-dataset", "description": "冒烟验证用数据集"},
            files={"file": ("sample_data.jsonl", payload, "application/jsonl")},
        )
        if up.status_code != 200:
            raise SmokeFailure(f"导入数据失败: {up.status_code} {up.text}")
        dataset = up.json()
        check("POST /api/data/import 导入数据成功", dataset.get("total_samples", 0) > 0,
              f"dataset_id={dataset.get('id')} total_samples={dataset.get('total_samples')}")

        # --- 3) 注册模型 ---
        md = client.post("/api/model/register", params={
            "name": "smoke-model",
            "base_model": "Qwen/Qwen2.5-7B-Instruct",
        })
        if md.status_code != 200:
            raise SmokeFailure(f"注册模型失败: {md.status_code} {md.text}")
        model = md.json()
        check("POST /api/model/register 注册模型成功", bool(model.get("id")),
              f"id={model.get('id')}")

        # --- 4) 推理（OpenAI 兼容） ---
        chat = client.post("/v1/chat/completions", json={
            "model": "smoke-model",
            "messages": [{"role": "user", "content": "1+1=?"}],
            "max_tokens": 32,
        })
        if chat.status_code != 200:
            raise SmokeFailure(f"聊天补全失败: {chat.status_code} {chat.text}")
        body = chat.json()
        text = body["choices"][0]["message"]["content"]
        check("POST /v1/chat/completions 返回可用补全", bool(text.strip()),
              f"backend={body.get('backend')}")
        check("推理响应显式标注 backend（不冒充真实模型）",
              body.get("backend") in {"mock", "vllm", "scripted"},
              f"backend={body.get('backend')}")
        if body.get("backend") == "mock":
            check("mock 后端输出带 [MOCK] 前缀，可被识别为占位",
                  text.startswith("[MOCK]"), f"text={text[:40]!r}")

        # --- 5) 评测：指标必须是真实计算的 ---
        ev = client.post("/api/evaluate/create", json={
            "model_id": model["id"],
            "dataset_id": dataset["id"],
            "eval_name": "smoke-eval",
            "metrics": ["exact_match", "token_f1", "latency"],
        })
        if ev.status_code != 200:
            raise SmokeFailure(f"建评测失败: {ev.status_code} {ev.text}")
        evaluation = ev.json()

        run = client.post(f"/api/evaluate/{evaluation['id']}/run")
        if run.status_code != 200:
            raise SmokeFailure(f"跑评测失败: {run.status_code} {run.text}")
        results = run.json()["results"]

        check("POST /api/evaluate/{id}/run 产出评测结果",
              results.get("sample_count", 0) > 0,
              f"sample_count={results.get('sample_count')}")
        check("评测结果为真实计算值（非硬编码 0.72）",
              results.get("exact_match", {}).get("value") in (0.0, 1.0),
              f"exact_match={results.get('exact_match', {}).get('value')}")
        check("延迟为实测值（> 0）",
              results.get("latency", {}).get("avg_ms", 0) > 0,
              f"avg_ms={results.get('latency', {}).get('avg_ms')}")

        # --- 6) 上传安全：非法扩展名必须被拒 ---
        bad = client.post(
            "/api/data/import",
            params={"name": "evil-dataset"},
            files={"file": ("evil.exe", b"MZ\x90\x00", "application/octet-stream")},
        )
        check("上传非法扩展名被拒绝（HTTP 4xx）", 400 <= bad.status_code < 500,
              f"status={bad.status_code}")

        # --- 7) 路径穿越文件名必须被净化 ---
        trav = client.post(
            "/api/data/import",
            params={"name": "traversal-dataset"},
            files={"file": ("../../evil.jsonl", payload, "application/jsonl")},
        )
        # 被净化后应正常导入；若被拒也接受，但绝不能真的写到 datasets 目录之外
        escaped = [
            p for p in (
                data_dir / "evil.jsonl",
                PROJECT_ROOT / "evil.jsonl",
                PROJECT_ROOT.parent / "evil.jsonl",
            )
            if p.exists()
        ]
        check("路径穿越文件名未逃出数据目录",
              trav.status_code in (200, 400) and not escaped,
              f"status={trav.status_code} escaped={[str(p) for p in escaped]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="UniLLM Platform 端到端冒烟验证")
    parser.add_argument("--port", type=int, default=8123, help="服务监听端口")
    parser.add_argument("--timeout", type=float, default=40.0, help="等待就绪的秒数")
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    sample_jsonl = PROJECT_ROOT / "data" / "datasets" / "sample_data.jsonl"
    if not sample_jsonl.exists():
        print(f"找不到样例数据: {sample_jsonl}")
        return 2

    print("=" * 68)
    print("UniLLM Platform 端到端冒烟验证（真实 uvicorn 进程）")
    print(f"  项目根目录: {PROJECT_ROOT}")
    print(f"  服务地址:   {base_url}")
    print("=" * 68)

    server: subprocess.Popen | None = None
    exit_code = 0
    # Windows 上关闭进程后 SQLite 文件句柄可能仍被短暂占用，
    # 因此不用 TemporaryDirectory 上下文（其清理会直接抛错），改为手动忽略清理失败。
    data_dir = Path(tempfile.mkdtemp(prefix="unillm-smoke-"))
    try:
        print(f"\n[1/2] 启动 uvicorn 子进程（数据目录: {data_dir}）")
        server = start_server(args.port, data_dir)

        try:
            health = wait_for_health(base_url, args.timeout)
            print(f"      服务已就绪: {json.dumps(health, ensure_ascii=False)}")
        except SmokeFailure as exc:
            print(f"      服务启动失败: {exc}")
            if server.poll() is not None:
                out = server.stdout.read() if server.stdout else ""
                print("      --- 子进程输出 ---")
                print(out[-3000:])
            return 1

        print("\n[2/2] 执行全链路断言")
        try:
            run_flow(base_url, sample_jsonl, data_dir)
        except SmokeFailure as exc:
            check("全链路执行完成", False, str(exc))
    finally:
        if server and server.poll() is None:
            server.terminate()
            try:
                server.wait(timeout=10)
            except subprocess.TimeoutExpired:
                server.kill()
                server.wait(timeout=5)
            print("\n服务已关闭。")
        shutil.rmtree(data_dir, ignore_errors=True)

    passed = sum(1 for _, ok, _ in _CHECKS if ok)
    failed = [name for name, ok, _ in _CHECKS if not ok]
    total = len(_CHECKS)

    print("\n" + "=" * 68)
    print(f"结果: {passed}/{total} 项通过")
    if failed:
        print("失败项:")
        for name in failed:
            print(f"  - {name}")
        exit_code = 1
    else:
        print("全部通过：真实服务可启动，且数据->推理->评测链路可用。")
    print("=" * 68)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
