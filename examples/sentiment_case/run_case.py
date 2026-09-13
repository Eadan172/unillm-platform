#!/usr/bin/env python
"""UniLLM Platform 端到端测试案例：情感二分类闭环复现脚本。

本脚本对**一个已经在运行的服务实例**执行完整 5 步闭环，每步都打印可核对的
真实响应关键字段，最后输出一张指标汇总表。它不启动服务、不修改平台任何代码，
只通过公开 HTTP 接口操作，因此可以安全地对任意实例重复运行。

5 步闭环：
    [1/5] 导入数据集     POST /api/data/import            （train.jsonl / test.jsonl）
    [2/5] 创建标注任务   POST /api/annotation/task
    [3/5] 注册模型       POST /api/model/register         （name=sentiment-case-mock）
    [4/5] 批量推理       POST /v1/completions             （逐条对 test_without_label.jsonl 推理）
    [5/5] 运行评测       POST /api/evaluate/create + /{id}/run

设计要点
--------
- **绝不造假**：所有数字都来自服务端真实响应；脚本不推测、不补默认值。
- **诚实标注**：若 /health 返回 ``degraded=true``（说明当前是 mock 占位后端），
  脚本会在汇总表上方打印醒目提示，提醒读者本次验证的是**链路可用性**，
  而非模型效果，避免把 mock 的低准确率误读成"平台算错了"。
- **幂等友好**：重复运行时自动复用同名数据集/模型，并打印它所做的选择。
- **错误可读**：任何非 2xx 响应都会打印服务端返回的 ``detail / error_code / hint``。

用法：
    python examples/sentiment_case/run_case.py
    python examples/sentiment_case/run_case.py --base-url http://127.0.0.1:8000 --token <token>

零额外依赖：仅使用标准库 + 已装依赖 httpx（与项目现有依赖一致）。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import httpx
except ImportError:  # pragma: no cover - 明确的依赖提示，而不是裸异常
    print("缺少依赖 httpx，请先执行: pip install -r requirements.txt")
    raise SystemExit(2)

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

CASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CASE_DIR.parent.parent
TRAIN_FILE = CASE_DIR / "train.jsonl"
TEST_FILE = CASE_DIR / "test.jsonl"
TEST_UNLABELED_FILE = CASE_DIR / "test_without_label.jsonl"
TOKEN_FILE = PROJECT_ROOT / "data" / ".api_token"

# 与 config.yaml 的默认模型名（Qwen/Qwen2.5-7B-Instruct）刻意不同，避免撞名
CASE_MODEL_NAME = "sentiment-case-mock"
CASE_TRAIN_DATASET = "sentiment-case-train"
CASE_TEST_DATASET = "sentiment-case-test"

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
REQUEST_TIMEOUT = 60.0

# 评测请求的指标口径：EM + 字符级 F1 + 实测延迟
CASE_METRICS = ["exact_match", "token_f1", "latency"]


class CaseError(Exception):
    """案例执行过程中的可读错误（携带服务端错误契约三字段）。"""

    def __init__(self, step: str, message: str, detail: str = "",
                 error_code: str = "", hint: str = ""):
        super().__init__(message)
        self.step = step
        self.detail = detail
        self.error_code = error_code
        self.hint = hint


# ---------------------------------------------------------------------------
# 工具
# ---------------------------------------------------------------------------

def load_token_from_file(path: Path) -> str:
    """从 ``data/.api_token`` 读取自动生成的 Token；不存在则返回空串。"""
    try:
        if path.exists():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def read_jsonl(path: Path) -> List[Dict[str, Any]]:
    """读取 JSONL 文件，跳过空行。文件不存在时抛出可读错误。"""
    if not path.exists():
        raise CaseError("前置检查", f"找不到案例数据文件: {path}")
    records: List[Dict[str, Any]] = []
    with open(path, "r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                records.append(json.loads(stripped))
            except json.JSONDecodeError as exc:
                raise CaseError(
                    "前置检查", f"第 {line_no} 行不是合法 JSON: {path.name}"
                ) from exc
    if not records:
        raise CaseError("前置检查", f"数据文件为空: {path.name}")
    return records


# 案例数据的原始字段为 {"text", "label"}，而平台导入接口只识别
# instruction/question、input/context、output/answer 这 6 个内容字段。
# 若不转换，平台会（正确地）拒绝导入「无任何可识别内容字段」的文件。
# 因此这里做一次显式映射，把案例格式转成平台标准字段后再上传。
CASE_INSTRUCTION = "下面这条酒店评论是好评（1）还是差评（0）？只回答 0 或 1。"


def to_platform_records(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """把案例的 ``{text, label}`` 记录映射为平台的 ``{instruction, input, output}``。

    映射规则（显式、可复现）：
      - ``input`` = 原始 ``text``（评论原文）
      - ``output`` = ``str(label)``（标签转成字符串 "0"/"1"，作为参考答案）
      - ``instruction`` = 固定任务指令 ``CASE_INSTRUCTION``

    转换在内存中进行，不改动磁盘上的案例 jsonl（保持案例原始格式不变，便于
    替换为官方 ChnSentiCorp 数据）。
    """
    converted: List[Dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if "text" not in row or "label" not in row:
            raise CaseError(
                "第 1 步 · 格式转换",
                f"第 {index} 条记录缺少 text/label 字段，无法转换：{sorted(row.keys())}",
            )
        converted.append({
            "instruction": CASE_INSTRUCTION,
            "input": row["text"],
            "output": str(row["label"]),
        })
    return converted


def records_to_jsonl_bytes(records: List[Dict[str, Any]]) -> bytes:
    """把记录列表序列化为 JSONL 字节流（UTF-8 无 BOM）。"""
    text = "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n"
    return text.encode("utf-8")


def describe_error(response: "httpx.Response") -> Tuple[str, str, str, str]:
    """从错误响应中解析统一错误契约 ``{detail, error_code, hint}``。

    返回 (message, detail, error_code, hint)。解析失败时回退为原始响应文本。
    """
    detail = ""
    error_code = ""
    hint = ""
    try:
        body = response.json()
        if isinstance(body, dict):
            detail = str(body.get("detail", "") or "")
            error_code = str(body.get("error_code", "") or "")
            hint = str(body.get("hint", "") or "")
    except Exception:
        detail = (response.text or "")[:300]

    message = detail or f"HTTP {response.status_code}"
    if error_code:
        message = f"[{error_code}] {message}"
    return message, detail, error_code, hint


def request_json(
    client: "httpx.Client",
    method: str,
    url: str,
    step: str,
    **kwargs: Any,
) -> Dict[str, Any]:
    """发起请求并解析 JSON；非 2xx 抛出携带错误契约的 ``CaseError``。"""
    try:
        response = client.request(method, url, **kwargs)
    except httpx.RequestError as exc:
        raise CaseError(
            step,
            f"无法连接服务端（{exc.__class__.__name__}）：请确认服务已在运行",
            hint="示例：python -m uvicorn app.main:app --host 127.0.0.1 --port 8000",
        ) from exc

    if response.status_code >= 400:
        message, detail, error_code, hint = describe_error(response)
        raise CaseError(step, message, detail, error_code, hint)

    try:
        return response.json()
    except Exception as exc:
        raise CaseError(
            step, f"服务端返回的不是 JSON：{response.text[:200]}"
        ) from exc


def find_dataset(client: "httpx.Client", name: str) -> Optional[Dict[str, Any]]:
    """按名称查找已存在的数据集；用于幂等复用。"""
    listing = request_json(client, "GET", "/api/data/list", "幂等检查",
                           params={"limit": 200})
    if isinstance(listing, list):
        for item in listing:
            if item.get("name") == name:
                return item
    return None


def find_model(client: "httpx.Client", name: str) -> Optional[Dict[str, Any]]:
    """按名称查找已注册的模型；用于幂等复用。"""
    listing = request_json(client, "GET", "/api/model/list", "幂等检查",
                           params={"limit": 200})
    if isinstance(listing, list):
        for item in listing:
            if item.get("name") == name:
                return item
    return None


# ---------------------------------------------------------------------------
# 5 步闭环
# ---------------------------------------------------------------------------

def step1_import_datasets(
    client: "httpx.Client",
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """[1/5] 导入 train / test 两个数据集（幂等：同名则复用）。

    注意：磁盘上的案例数据是 ``{text, label}`` 格式，而平台导入接口只识别
    ``instruction/input/output`` 等标准字段。这里在内存中做一次显式映射
    （见 ``to_platform_records``），再以平台格式上传，避免入库空壳记录。
    """
    print("\n[STEP 1/5] 导入数据集  POST /api/data/import")
    print("  · 格式转换：案例原始 {text,label} → 平台标准 {instruction,input,output}")
    print(f"      input=评论原文, output=str(label), instruction='{CASE_INSTRUCTION}'")
    results: Dict[str, Dict[str, Any]] = {}

    for dataset_name, file_path in (
        (CASE_TRAIN_DATASET, TRAIN_FILE),
        (CASE_TEST_DATASET, TEST_FILE),
    ):
        existing = find_dataset(client, dataset_name)
        if existing is not None:
            print(f"  · 数据集 '{dataset_name}' 已存在 → 复用 "
                  f"(id={existing.get('id')}, total_samples={existing.get('total_samples')})")
            results[dataset_name] = existing
            continue

        source_rows = read_jsonl(file_path)
        platform_rows = to_platform_records(source_rows)
        payload = records_to_jsonl_bytes(platform_rows)

        dataset = request_json(
            client,
            "POST",
            "/api/data/import",
            "第 1 步 · 导入数据集",
            params={"name": dataset_name, "description": "情感二分类案例（示例数据）"},
            files={"file": (f"{file_path.stem}_platform.jsonl", payload,
                            "application/jsonl")},
        )
        print(f"  · 导入 '{dataset_name}' → id={dataset.get('id')}, "
              f"total_samples={dataset.get('total_samples')}, "
              f"source_type={dataset.get('source_type')}")
        results[dataset_name] = dataset

    return results[CASE_TRAIN_DATASET], results[CASE_TEST_DATASET]


def verify_task_content(
    client: "httpx.Client", task_id: int, expected: str
) -> None:
    """核对标注任务下的首条记录含真实内容（instruction/input 非空），打印证据。

    这条核验专门针对 A2 修复的问题：字段名对不上时会把「字段全空」的空壳记录
    入库，表面 total_samples 正常。这里通过任务 items 拉取真实记录确认非空。
    """
    items = request_json(
        client, "GET", f"/api/annotation/task/{task_id}/items", "第 2 步 · 内容核验",
        params={"limit": 1},
    )
    if not isinstance(items, list) or not items:
        raise CaseError(
            "第 2 步 · 内容核验",
            f"任务 {task_id} 下没有任何记录，导入结果为空壳",
        )
    first = items[0]
    has_content = any(
        str(first.get(field) or "").strip()
        for field in ("instruction", "input_text", "output_text")
    )
    if not has_content:
        raise CaseError(
            "第 2 步 · 内容核验",
            f"任务 {task_id} 首条记录 instruction/input/output 全为空，字段映射失败",
        )
    preview = str(first.get("input_text") or "")[:30]
    print(f"  · 内容核验 '{expected}': 首条 input 非空 → {preview!r}, "
          f"output={first.get('output_text')!r}, status={first.get('status')!r}")


def step2_create_annotation_task(
    client: "httpx.Client", train_dataset_id: int
) -> Dict[str, Any]:
    """[2/5] 为 train 数据集创建标注任务（幂等：同名任务已存在则复用）。"""
    print("\n[STEP 2/5] 创建标注任务  POST /api/annotation/task")
    task_name = "sentiment-case-annotation"

    tasks = request_json(client, "GET", "/api/annotation/task/list", "幂等检查",
                         params={"limit": 200})
    if isinstance(tasks, list):
        for task in tasks:
            if task.get("name") == task_name and task.get("dataset_id") == train_dataset_id:
                print(f"  · 任务 '{task_name}' 已存在 → 复用 (id={task.get('id')}, "
                      f"total_items={task.get('total_items')})")
                verify_task_content(client, int(task["id"]), CASE_TRAIN_DATASET)
                return task

    task = request_json(
        client,
        "POST",
        "/api/annotation/task",
        "第 2 步 · 创建标注任务",
        json={
            "name": task_name,
            "dataset_id": train_dataset_id,
            "description": "情感二分类标注任务（label: 0=差评 / 1=好评）",
            "annotation_type": "text",
        },
    )
    print(f"  · 创建任务 → id={task.get('id')}, name={task.get('name')}, "
          f"total_items={task.get('total_items')}, status={task.get('status')}")

    progress = request_json(client, "GET", f"/api/annotation/task/{task.get('id')}/progress",
                            "第 2 步 · 查询进度")
    print(f"  · 任务进度 → total={progress.get('total')}, "
          f"completed={progress.get('completed')}, pending={progress.get('pending')}, "
          f"progress={progress.get('progress')}%")

    verify_task_content(client, int(task["id"]), CASE_TRAIN_DATASET)
    return task


def step3_register_model(client: "httpx.Client") -> Dict[str, Any]:
    """[3/5] 注册模型（幂等：同名则复用）。"""
    print("\n[STEP 3/5] 注册模型  POST /api/model/register")
    existing = find_model(client, CASE_MODEL_NAME)
    if existing is not None:
        print(f"  · 模型 '{CASE_MODEL_NAME}' 已注册 → 复用 (id={existing.get('id')})")
        return existing

    model = request_json(
        client,
        "POST",
        "/api/model/register",
        "第 3 步 · 注册模型",
        params={
            "name": CASE_MODEL_NAME,
            "model_type": "base",
            "base_model": "Qwen/Qwen2.5-7B-Instruct",
            "description": "端到端测试案例使用的占位模型（无 GPU 时走 mock 后端）",
        },
    )
    print(f"  · 注册成功 → id={model.get('id')}, name={model.get('name')}, "
          f"model_type={model.get('model_type')}, is_loaded={model.get('is_loaded')}")

    backend = request_json(client, "GET", "/api/model/backend", "第 3 步 · 后端状态")
    print(f"  · 当前推理后端 → backend={backend.get('backend')}, "
          f"is_real_model={backend.get('is_real_model')}, "
          f"current_model={backend.get('current_model')}")
    return model


def step4_run_inference(
    client: "httpx.Client", unlabeled: List[Dict[str, Any]]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """[4/5] 逐条调用 /v1/completions 推理，返回 (预测列表, 评测用 test_data)。

    评测样本使用 ``input``（评论原文）与 ``output``（真实标签字符串）字段，
    与服务端 ``EvaluateService.resolve_samples`` 的字段解析约定一致。
    """
    print("\n[STEP 4/5] 批量推理  POST /v1/completions")
    predictions: List[Dict[str, Any]] = []
    eval_samples: List[Dict[str, Any]] = []

    truth_by_text = {row["text"]: int(row["label"]) for row in read_jsonl(TEST_FILE)}

    for index, item in enumerate(unlabeled, start=1):
        text = str(item.get("text", ""))
        prompt = (
            "请判断下面这条酒店评论是好评还是差评，只回答 1（好评）或 0（差评）。\n"
            f"评论：{text}\n回答："
        )
        body = request_json(
            client,
            "POST",
            "/v1/completions",
            "第 4 步 · 推理",
            json={"model": CASE_MODEL_NAME, "prompt": prompt, "max_tokens": 64,
                  "temperature": 0.7, "top_p": 0.9, "stream": False},
        )
        prediction = body["choices"][0]["text"]
        backend = body.get("backend")
        predictions.append({
            "text": text,
            "prediction": prediction,
            "backend": backend,
            "latency_ms": None,
        })
        # 有真实标签的样本才参与指标计算
        if text in truth_by_text:
            eval_samples.append({"input": text, "output": str(truth_by_text[text])})

    print(f"  · 共推理 {len(predictions)} 条样本，backend={predictions[0]['backend']}")
    preview = predictions[0]["prediction"]
    print(f"  · 第 1 条预测（截断 120 字）: {preview[:120]!r}")
    print(f"  · 可参与评测（含真实标签）样本数: {len(eval_samples)}")
    if predictions[0]["backend"] == "mock":
        print("  · 注意：backend=mock，输出为确定性占位文本，非模型输出")
    return predictions, eval_samples


def step5_run_evaluation(
    client: "httpx.Client",
    model_id: int,
    test_dataset_id: int,
    eval_samples: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """[5/5] 创建评测并运行，返回 results 字典。"""
    print("\n[STEP 5/5] 运行评测  POST /api/evaluate/create + /{id}/run")
    evaluation = request_json(
        client,
        "POST",
        "/api/evaluate/create",
        "第 5 步 · 创建评测",
        json={
            "model_id": model_id,
            "dataset_id": test_dataset_id,
            "eval_name": "sentiment-case-eval",
            "metrics": CASE_METRICS,
        },
    )
    eval_id = evaluation.get("id")
    print(f"  · 创建评测 → id={eval_id}, status={evaluation.get('status')}, "
          f"requested_metrics={(evaluation.get('metrics') or {}).get('requested')}")

    run = request_json(
        client,
        "POST",
        f"/api/evaluate/{eval_id}/run",
        "第 5 步 · 运行评测",
        json={"test_data": eval_samples},
    )
    results = run.get("results", {})
    print(f"  · 运行结果 → status={run.get('status')}, "
          f"sample_count={results.get('sample_count')}, "
          f"backend={results.get('backend')}, "
          f"backend_is_real_model={results.get('backend_is_real_model')}")
    return results


# ---------------------------------------------------------------------------
# 汇总输出
# ---------------------------------------------------------------------------

def print_summary(
    degraded: bool, health: Dict[str, Any], results: Dict[str, Any]
) -> None:
    """打印最终指标汇总表；degraded 时在表上方给出醒目提示。"""
    line = "=" * 68
    print("\n" + line)
    if degraded:
        print("⚠  重要提示：本次运行在 mock（占位）后端上进行")
        print("   当前 backend = "
              f"{health.get('inference_backend')}，degraded = true。")
        print("   下方指标衡量的是【平台链路是否可用】（数据→推理→评测），")
        print("   而不是模型效果——mock 后端输出固定占位文本，准确率低是预期行为，")
        print("   请勿把此处的 Exact Match / F1 当作任何真实模型的性能。")
        print(line)
    print("情感二分类案例 · 指标汇总")
    print(line)

    em = results.get("exact_match") or {}
    f1 = results.get("token_f1") or {}
    latency = results.get("latency") or {}
    ppl = results.get("perplexity")

    rows = [
        ("样本数 (sample_count)", str(results.get("sample_count", "—"))),
        ("Exact Match",
         f"{em.get('value', '—')}  ({em.get('correct', '?')}/{em.get('total', '?')})"),
        ("Char-F1 (token_f1)", f"{f1.get('value', '—')}  (unit={f1.get('unit', '—')})"),
        ("延迟 min", f"{latency.get('min_ms', '—')} ms"),
        ("延迟 avg", f"{latency.get('avg_ms', '—')} ms"),
        ("延迟 p50", f"{latency.get('p50_ms', '—')} ms"),
        ("延迟 p95", f"{latency.get('p95_ms', '—')} ms"),
        ("延迟 max", f"{latency.get('max_ms', '—')} ms"),
    ]
    if ppl is None:
        rows.append(("Perplexity", "未请求 / 无数据"))
    elif ppl.get("available") is False:
        rows.append(("Perplexity", f"不可用（{ppl.get('reason', '未知原因')}）"))
    else:
        rows.append(("Perplexity", str(ppl.get("value"))))

    width = max(len(name) for name, _ in rows)
    for name, value in rows:
        print(f"  {name.ljust(width)} : {value}")
    print(line)


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="UniLLM Platform 情感二分类端到端案例复现脚本"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL,
                        help=f"服务地址（默认 {DEFAULT_BASE_URL}）")
    parser.add_argument("--token", default=None,
                        help="访问 Token；默认从 data/.api_token 自动读取")
    args = parser.parse_args()

    token = args.token
    token_source = "--token 参数"
    if not token:
        token = load_token_from_file(TOKEN_FILE)
        token_source = f"{TOKEN_FILE}"
    if not token:
        print("错误：未提供 Token，且无法从 data/.api_token 读取。")
        print("      请用 --token 指定，或确认服务已启动并生成过 Token。")
        return 2

    base_url = args.base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {token}"}

    print("=" * 68)
    print("UniLLM Platform · 情感二分类端到端案例")
    print(f"  服务地址   : {base_url}")
    print(f"  Token 来源 : {token_source}")
    print(f"  案例目录   : {CASE_DIR}")
    print("=" * 68)

    try:
        with httpx.Client(base_url=base_url, headers=headers,
                          timeout=REQUEST_TIMEOUT) as client:
            # 前置：读取健康状态，判断是否降级
            health = request_json(client, "GET", "/health", "前置健康检查")
            degraded = bool(health.get("degraded"))
            print(f"\n[前置] GET /health → status={health.get('status')}, "
                  f"backend={health.get('inference_backend')}, "
                  f"degraded={degraded}, "
                  f"registered_models={health.get('registered_models')}")

            train, test = step1_import_datasets(client)
            task = step2_create_annotation_task(client, int(train["id"]))
            model = step3_register_model(client)

            unlabeled = read_jsonl(TEST_UNLABELED_FILE)
            _, eval_samples = step4_run_inference(client, unlabeled)

            results = step5_run_evaluation(
                client, int(model["id"]), int(test["id"]), eval_samples
            )
    except CaseError as exc:
        print("\n" + "-" * 68)
        print(f"执行失败于：{exc.step}")
        print(f"  错误信息 detail      : {exc.detail or str(exc)}")
        print(f"  错误码   error_code  : {exc.error_code or '(无)'}")
        print(f"  建议     hint        : {exc.hint or '(无)'}")
        print("-" * 68)
        return 1

    print_summary(degraded, health, results)
    print("\n案例执行完成：5 步全通。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
