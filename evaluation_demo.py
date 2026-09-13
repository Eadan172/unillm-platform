#!/usr/bin/env python
"""UniLLM Platform 真实评测演示（非交互）。

本脚本替换了原仓库里的两个演示脚本：

- ``evaluation_auto.py``：195 行 ``print`` 硬编码了 "Accuracy 0.72 / Perplexity 12.50
  / Latency 280ms"，却冠以"评测报告"标题，还据此给出"医药健康领域需优化、
  电商客服可用"的业务结论。它不连服务、不调接口、不跑模型，是纯编造。
- 旧 ``evaluation_demo.py``：所谓"模拟评测演示"同样在打印上面那组假数字；
  仅有的"真实流程"还用 ``input()`` 交互，且拿到结果后只打印一句
  "结果将在后台计算"，不展示任何真实指标。

现在这个脚本只做一件事：**连上正在运行的服务，跑一遍真实评测，把服务
返回的真实数字原样打印出来**。跑不通就明确报错，绝不填占位数字。

用法：
    1. 另开一个终端启动服务：
           python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
    2. 运行本脚本：
           python evaluation_demo.py
       （可用 --base-url 指向其它地址）

注意：未安装 vLLM 时推理走 mock 后端，指标会非常低 —— 这是**真实结果**，
说明被测的不是真模型。响应里的 backend 字段会明确标注这一点。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import httpx
except ImportError:
    print("缺少依赖 httpx，请先执行: pip install -r requirements.txt")
    raise SystemExit(2)

PROJECT_ROOT = Path(__file__).resolve().parent
SAMPLE_DATA = PROJECT_ROOT / "data" / "datasets" / "sample_data.jsonl"


def _bar(value: float, warn: bool = False) -> str:
    """把 0~1 的指标画成进度条，只用于视觉呈现，不参与任何判断。"""
    filled = max(0, min(10, round(value * 10)))
    return "█" * filled + "░" * (10 - filled) + ("  (低)" if warn else "")


def main() -> int:
    parser = argparse.ArgumentParser(description="UniLLM Platform 真实评测演示")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="服务地址")
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    print("=" * 70)
    print("UniLLM Platform 真实评测演示")
    print(f"服务地址: {base_url}")
    print("=" * 70)

    if not SAMPLE_DATA.exists():
        print(f"找不到样例数据: {SAMPLE_DATA}")
        return 2

    with httpx.Client(base_url=base_url, timeout=60.0) as client:
        # --- 0) 连通性与后端真实性 ---
        print("\n[步骤 0] 检查服务连通性")
        try:
            health = client.get("/health").json()
        except Exception as exc:
            print(f"无法连接服务（{type(exc).__name__}）。请先启动：")
            print("  python -m uvicorn app.main:app --host 127.0.0.1 --port 8000")
            return 1
        print(f"  ✓ 服务正常，版本 {health.get('version')}")
        print(f"  · 推理后端: {health.get('inference_backend')}")
        if health.get("degraded"):
            print("  ! 当前为降级模式（mock 后端），下面的指标不代表任何真实模型能力")

        # --- 1) 导入测试数据 ---
        print("\n[步骤 1] 导入测试数据")
        with open(SAMPLE_DATA, "rb") as f:
            resp = client.post(
                "/api/data/import",
                params={"name": "评测演示数据", "description": "evaluation_demo.py 导入"},
                files={"file": (SAMPLE_DATA.name, f, "application/jsonl")},
            )
        if resp.status_code != 200:
            print(f"  ✗ 导入失败: HTTP {resp.status_code} {resp.text[:200]}")
            return 1
        dataset = resp.json()
        dataset_id = dataset["id"]
        print(f"  ✓ 数据集 id={dataset_id}，样本数={dataset.get('total_samples')}")

        # --- 2) 注册模型 ---
        print("\n[步骤 2] 注册待评测模型")
        resp = client.post(
            "/api/model/register",
            params={"name": "demo-model", "base_model": "Qwen/Qwen2.5-7B-Instruct"},
        )
        if resp.status_code != 200:
            print(f"  ✗ 注册失败: HTTP {resp.status_code} {resp.text[:200]}")
            return 1
        model_id = resp.json()["id"]
        print(f"  ✓ 模型 id={model_id}")

        # --- 3) 创建评测任务 ---
        print("\n[步骤 3] 创建评测任务")
        resp = client.post(
            "/api/evaluate/create",
            json={
                "model_id": model_id,
                "dataset_id": dataset_id,
                "eval_name": "真实评测演示",
                "metrics": ["exact_match", "token_f1", "latency", "perplexity"],
            },
        )
        if resp.status_code != 200:
            print(f"  ✗ 创建失败: HTTP {resp.status_code} {resp.text[:200]}")
            return 1
        eval_id = resp.json()["id"]
        print(f"  ✓ 评测任务 id={eval_id}")

        # --- 4) 运行评测（同步返回真实结果） ---
        print("\n[步骤 4] 运行评测")
        resp = client.post(f"/api/evaluate/{eval_id}/run")
        if resp.status_code != 200:
            print(f"  ✗ 运行失败: HTTP {resp.status_code} {resp.text[:300]}")
            return 1
        results = resp.json()["results"]

        # --- 5) 原样展示服务返回的指标 ---
        print("\n" + "=" * 70)
        print("评测结果（以下数值全部由服务端实际计算得出）")
        print("=" * 70)
        print(f"  样本数      : {results.get('sample_count')}")
        print(f"  推理后端    : {results.get('backend')}")
        print(f"  真实模型    : {results.get('backend_is_real_model')}")

        em = results.get("exact_match")
        if em:
            print(f"\n  Exact Match : {em['value']:.4f}  {_bar(em['value'], em['value'] < 0.5)}")
            print(f"    命中/总数 : {em['correct']}/{em['total']}")

        f1 = results.get("token_f1")
        if f1:
            print(f"\n  Char-F1     : {f1['value']:.4f}  {_bar(f1['value'], f1['value'] < 0.5)}")

        lat = results.get("latency")
        if lat:
            print(f"\n  Latency     : avg={lat['avg_ms']:.3f}ms  "
                  f"p50={lat['p50_ms']:.3f}ms  p95={lat['p95_ms']:.3f}ms  "
                  f"min={lat['min_ms']:.3f}ms  max={lat['max_ms']:.3f}ms")

        ppl = results.get("perplexity")
        if ppl:
            if ppl.get("available"):
                print(f"\n  Perplexity  : {ppl['value']:.4f}")
            else:
                print(f"\n  Perplexity  : 不可用 —— {ppl.get('reason')}")

        print("\n--- 完整 JSON ---")
        print(json.dumps(results, ensure_ascii=False, indent=2))

        print("\n" + "=" * 70)
        if not results.get("backend_is_real_model"):
            print("结论：本次评测跑在 mock 后端上，指标低是**预期且真实**的结果，")
            print("      它衡量的不是模型能力。要评测真实模型，请安装 GPU 依赖：")
            print("      pip install -r requirements-gpu.txt")
        else:
            print("结论：本次评测由真实模型产出，指标可用于横向比较。")
        print("=" * 70)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
