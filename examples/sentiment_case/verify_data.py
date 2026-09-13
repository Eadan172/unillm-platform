#!/usr/bin/env python
"""V1 数据文件真实性核验脚本（QA 独立编写，用于证伪而非确认）。

对 ``examples/sentiment_case/`` 下的三个 JSONL 做机器化校验，避免目测遗漏：

1. 编码：UTF-8 无 BOM（前 3 字节 != EF BB BF）。
2. 逐行合法 JSON；字段集合恰为 {text} 或 {text, label}。
3. label ∈ {0,1} 且为 int。
4. 条数与正负分布：train 20（10/10）、test 10（5/5）、unlabeled 10。
5. **unlabeled 与 test 逐行文本完全一致**（否则推理→评测对不上）。
6. train/test/unlabeled 三者内部与之间无重复文本；无 train/test 交叉泄漏。
7. 文本长度分布（min/max/avg），并做"模板句"粗检：
   - 完全重复行数；
   - 出现次数 >= 2 的 4-gram 占比（句法雷同的量化信号）。

用法：
    python examples/sentiment_case/verify_data.py
    退出码 0 = 全部通过；1 = 存在失败项。
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
FILES = {
    "train": CASE_DIR / "train.jsonl",
    "test": CASE_DIR / "test.jsonl",
    "unlabeled": CASE_DIR / "test_without_label.jsonl",
}

FAILURES: list[str] = []


def check(condition: bool, ok_msg: str, fail_msg: str) -> bool:
    if condition:
        print(f"  [PASS] {ok_msg}")
        return True
    print(f"  [FAIL] {fail_msg}")
    FAILURES.append(fail_msg)
    return False


def load_jsonl(path: Path) -> list[dict]:
    """读 JSONL，返回 (记录列表)；同时把编码/JSON 问题记入 FAILURES。"""
    raw = path.read_bytes()
    if raw[:3] == b"\xef\xbb\xbf":
        FAILURES.append(f"{path.name}: 含 UTF-8 BOM")
        print(f"  [FAIL] {path.name}: 含 UTF-8 BOM（应为无 BOM）")
    else:
        print(f"  [PASS] {path.name}: UTF-8 无 BOM")

    records = []
    for line_no, line in enumerate(raw.decode("utf-8").splitlines(), start=1):
        if not line.strip():
            FAILURES.append(f"{path.name}: 第 {line_no} 行为空行")
            print(f"  [FAIL] {path.name}: 第 {line_no} 行为空行")
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError as exc:
            FAILURES.append(f"{path.name}: 第 {line_no} 行非法 JSON ({exc})")
            print(f"  [FAIL] {path.name}: 第 {line_no} 行非法 JSON")
    print(f"  [INFO] {path.name}: 解析出 {len(records)} 条记录")
    return records


def ngrams(text: str, n: int = 4) -> list[str]:
    return [text[i:i + n] for i in range(len(text) - n + 1)]


def main() -> int:
    print("=" * 72)
    print("V1 数据文件真实性核验 · verify_data.py")
    print("=" * 72)

    data: dict[str, list[dict]] = {}
    for key, path in FILES.items():
        print(f"\n--- 读取 {path.name} ---")
        if not path.exists():
            FAILURES.append(f"{path.name} 不存在")
            print(f"  [FAIL] {path.name} 不存在")
            return 1
        data[key] = load_jsonl(path)

    # ---- 字段与 label 合法性 ----
    for key, records in data.items():
        print(f"\n--- 字段与 label 校验: {key} ({len(records)} 条) ---")
        expected_fields = {"text"} if key == "unlabeled" else {"text", "label"}
        for i, rec in enumerate(records, start=1):
            if set(rec.keys()) != expected_fields:
                FAILURES.append(f"{key} 第 {i} 条字段={sorted(rec)} 期望={sorted(expected_fields)}")
            if key != "unlabeled":
                lab = rec.get("label")
                if not isinstance(lab, int) or isinstance(lab, bool) or lab not in (0, 1):
                    FAILURES.append(f"{key} 第 {i} 条 label={lab!r} 非法")
                if not isinstance(rec.get("text"), str):
                    FAILURES.append(f"{key} 第 {i} 条 text 非字符串")
        check(
            not any(key in f for f in FAILURES),
            f"{key}: 字段集合与 label 取值全部合法",
            f"{key}: 存在字段/label 非法项（见上）",
        )

    # ---- 条数与分布 ----
    print("\n--- 条数与标签分布 ---")
    check(len(data["train"]) == 20, "train 共 20 条", f"train 条数={len(data['train'])} != 20")
    check(len(data["test"]) == 10, "test 共 10 条", f"test 条数={len(data['test'])} != 10")
    check(len(data["unlabeled"]) == 10, "unlabeled 共 10 条",
          f"unlabeled 条数={len(data['unlabeled'])} != 10")

    for key in ("train", "test"):
        pos = sum(1 for r in data[key] if r.get("label") == 1)
        neg = sum(1 for r in data[key] if r.get("label") == 0)
        exp = (10, 10) if key == "train" else (5, 5)
        check((pos, neg) == exp, f"{key}: 好评(1)={pos} 差评(0)={neg}（期望 {exp}）",
              f"{key}: 正负分布 {pos}/{neg} != 期望 {exp}")

    # ---- unlabeled 与 test 逐行一致 ----
    print("\n--- unlabeled 与 test 逐行一致性（关键） ---")
    test_texts = [r["text"] for r in data["test"]]
    unl_texts = [r["text"] for r in data["unlabeled"]]
    check(test_texts == unl_texts,
          "unlabeled 与 test 逐行文本完全一致（顺序也一致）",
          "unlabeled 与 test 文本不一致或顺序不同 —— 推理→评测会对不上")

    # ---- 重复与交叉泄漏 ----
    print("\n--- 重复文本 / train-test 交叉泄漏 ---")
    for key in ("train", "test", "unlabeled"):
        texts = [r["text"] for r in data[key]]
        dup = [t for t, c in Counter(texts).items() if c > 1]
        check(not dup, f"{key}: 文件内无重复文本", f"{key}: 文件内存在重复文本 {dup[:2]}")

    train_set, test_set = set(test_texts), set(test_texts)
    overlap = set(r["text"] for r in data["train"]) & set(test_texts)
    check(not overlap, "train 与 test 无交叉泄漏", f"train/test 交叉泄漏: {list(overlap)[:2]}")

    # ---- 文本长度分布 ----
    print("\n--- 文本长度分布（字符数，含标点） ---")
    for key in ("train", "test"):
        lens = [len(r["text"]) for r in data[key]]
        print(f"  {key}: min={min(lens)} max={max(lens)} avg={statistics.mean(lens):.1f} "
              f"median={statistics.median(lens)}")
    all_lens = [len(r["text"]) for r in data["train"] + data["test"]]
    check(min(all_lens) >= 8, f"最短文本 {min(all_lens)} 字 >= 8",
          f"存在过短文本（{min(all_lens)} 字），疑似占位/空样本")
    check(statistics.mean(all_lens) >= 20, f"平均长度 {statistics.mean(all_lens):.1f} 字 >= 20",
          f"平均长度偏低 {statistics.mean(all_lens):.1f}，疑似模板句")

    # ---- 模板句粗检：4-gram 重复率 ----
    print("\n--- 模板句粗检（4-gram 重复率） ---")
    counter: Counter[str] = Counter()
    total_grams = 0
    for r in data["train"] + data["test"]:
        grams = ngrams(r["text"], 4)
        counter.update(grams)
        total_grams += len(grams)
    repeated = sum(c for g, c in counter.items() if c >= 2)
    ratio = repeated / total_grams if total_grams else 0.0
    print(f"  4-gram 总数={total_grams}, 重复出现的 4-gram 覆盖数={repeated}, 占比={ratio:.3f}")
    check(ratio < 0.15, f"4-gram 重复占比 {ratio:.3f} < 0.15（句式不雷同）",
          f"4-gram 重复占比 {ratio:.3f} >= 0.15，疑似模板句/套话")

    # ---- 汇总 ----
    print("\n" + "=" * 72)
    if FAILURES:
        print(f"V1 结论: FAIL（{len(FAILURES)} 项不合格）")
        for f in FAILURES:
            print(f"  - {f}")
        return 1
    print("V1 结论: PASS（全部校验通过）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
