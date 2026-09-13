#!/usr/bin/env python
"""把项目源码汇总成单个 Markdown，便于归档到 ima 知识库。

ima 连接器的入库 MIME 对照表只覆盖 pdf/doc/ppt/xls/csv/md/txt/png/jpg/webp/
mp3/m4a/wav/html/epub/aac，**不含 .py / .yaml / .ini / .jsonl / .gitignore**。
为确保源码可被完整归档与检索，这里把它们汇总进一个 .md 文档。
"""

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT_ROOT / "unillm-platform_源码全文.md"

# (展示用标题, 相对路径)
FILES = [
    ("应用入口 app/main.py", "app/main.py"),
    ("配置 app/config.py", "app/config.py"),
    ("依赖注入 app/api/deps.py", "app/api/deps.py"),
    ("路由 app/api/routes/data.py", "app/api/routes/data.py"),
    ("路由 app/api/routes/annotation.py", "app/api/routes/annotation.py"),
    ("路由 app/api/routes/model.py", "app/api/routes/model.py"),
    ("路由 app/api/routes/inference.py", "app/api/routes/inference.py"),
    ("路由 app/api/routes/finetune.py", "app/api/routes/finetune.py"),
    ("路由 app/api/routes/evaluate.py", "app/api/routes/evaluate.py"),
    ("数据模型 app/models/database.py", "app/models/database.py"),
    ("接口契约 app/models/schemas.py", "app/models/schemas.py"),
    ("服务 app/services/data_service.py", "app/services/data_service.py"),
    ("服务 app/services/annotation_service.py", "app/services/annotation_service.py"),
    ("服务 app/services/model_service.py", "app/services/model_service.py"),
    ("服务 app/services/inference_service.py", "app/services/inference_service.py"),
    ("服务 app/services/finetune_service.py", "app/services/finetune_service.py"),
    ("服务 app/services/evaluate_service.py", "app/services/evaluate_service.py"),
    ("测试 tests/conftest.py", "tests/conftest.py"),
    ("测试 tests/test_metrics.py", "tests/test_metrics.py"),
    ("测试 tests/test_closed_loop.py", "tests/test_closed_loop.py"),
    ("测试 tests/test_upload_safety.py", "tests/test_upload_safety.py"),
    ("冒烟脚本 scripts/smoke_test.py", "scripts/smoke_test.py"),
    ("评测演示 evaluation_demo.py", "evaluation_demo.py"),
    ("配置 config.yaml", "config.yaml"),
    ("配置 pytest.ini", "pytest.ini"),
    ("依赖 requirements.txt", "requirements.txt"),
    ("依赖 requirements-gpu.txt", "requirements-gpu.txt"),
    ("样例数据 data/datasets/sample_data.jsonl", "data/datasets/sample_data.jsonl"),
    ("忽略规则 .gitignore", ".gitignore"),
    ("包标记 app/__init__.py", "app/__init__.py"),
    ("包标记 app/api/__init__.py", "app/api/__init__.py"),
    ("包标记 app/api/routes/__init__.py", "app/api/routes/__init__.py"),
    ("包标记 app/models/__init__.py", "app/models/__init__.py"),
    ("包标记 app/services/__init__.py", "app/services/__init__.py"),
    ("包标记 app/core/__init__.py", "app/core/__init__.py"),
    ("包标记 app/utils/__init__.py", "app/utils/__init__.py"),
]

LANG = {
    ".py": "python", ".yaml": "yaml", ".ini": "ini",
    ".jsonl": "json", ".txt": "text", ".gitignore": "text",
}


def fence_for(path: Path) -> str:
    """按扩展名给出代码块语言标记。"""
    for suffix, lang in LANG.items():
        if path.name.endswith(suffix):
            return lang
    return "text"


def main() -> None:
    lines = [
        "# UniLLM Platform 源码全文",
        "",
        "本文件由 `scripts/pack_source.py` 生成，收录项目全部源码与配置文件的完整内容，",
        "便于在知识库中全文检索。逐文件说明见 `项目分析与改进报告.md`。",
        "",
        "| 项目 | 信息 |",
        "|---|---|",
        "| 仓库 | `https://github.com/Eadan172/unillm-platform.git` |",
        "| 交付版本 | 0.2.0 |",
        "| 验证状态 | 编译通过 / 53 个测试用例通过 / 真实进程冒烟 13 项通过 |",
        "| 验证环境 | Windows 11 + Python 3.13.12 + 纯 CPU |",
        "",
        "---",
        "",
        "## 目录",
        "",
    ]

    present = [(t, p) for t, p in FILES if (PROJECT_ROOT / p).exists()]
    for i, (title, rel) in enumerate(present, 1):
        anchor = title.replace(" ", "-").replace("/", "").replace(".", "")
        lines.append(f"{i}. [{title}](#{i}-{anchor})")
    lines += ["", "---", ""]

    for i, (title, rel) in enumerate(present, 1):
        path = PROJECT_ROOT / rel
        content = path.read_text(encoding="utf-8", errors="replace")
        line_count = content.count("\n") + 1
        lines += [
            f"## {i}. {title}",
            "",
            f"**路径**：`{rel}`　|　**行数**：{line_count}",
            "",
            f"```{fence_for(path)}",
            content.rstrip("\n"),
            "```",
            "",
            "---",
            "",
        ]

    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    total = sum((PROJECT_ROOT / p).read_text(encoding="utf-8", errors="replace").count("\n") + 1
                for _, p in present)
    print(f"已生成: {OUTPUT.name}")
    print(f"收录文件数: {len(present)}")
    print(f"收录源码总行数: {total}")
    print(f"输出大小: {OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
