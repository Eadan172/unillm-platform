#!/usr/bin/env python
"""把项目源码汇总成单个 Markdown，便于归档到 ima 知识库。

ima 连接器的入库 MIME 对照表只覆盖 pdf/doc/ppt/xls/csv/md/txt/png/jpg/webp/
mp3/m4a/wav/html/epub/aac，**不含 .py / .yaml / .ini / .jsonl / .gitignore**。
为确保源码可被完整归档与检索，这里把它们汇总进一个 .md 文档。

输出位置说明：产物写入 ``build/archive/``（已被 .gitignore 忽略）。
它是由源码**派生**的临时归档件，不进入版本管理 —— 任何时候都能重新生成，
源头始终是源码本身。需要归档时运行本脚本，再取 ``build/archive/`` 下的文件即可。
"""

from datetime import datetime
from pathlib import Path
import re
import subprocess

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT_ROOT / "build" / "archive" / "unillm-platform_源码全文.md"

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
    # ---- 0.3.0 新增/关键模块（旧清单遗漏，重传时必须补上）----
    ("契约核心 app/core/values.py", "app/core/values.py"),
    ("安全鉴权 app/core/security.py", "app/core/security.py"),
    ("错误契约 app/core/errors.py", "app/core/errors.py"),
    ("Web 控制台 app/web/index.html", "app/web/index.html"),
    ("Dockerfile", "Dockerfile"),
    ("docker-compose.yml", "docker-compose.yml"),
    ("打包脚本 scripts/pack_source.py", "scripts/pack_source.py"),
    ("测试 tests/test_auth.py", "tests/test_auth.py"),
    ("测试 tests/test_errors.py", "tests/test_errors.py"),
    ("测试 tests/test_input_validation.py", "tests/test_input_validation.py"),
    ("测试 tests/test_scalar_contract.py", "tests/test_scalar_contract.py"),
    ("测试 tests/test_evaluation_references.py", "tests/test_evaluation_references.py"),
    ("测试 tests/test_security_hardening.py", "tests/test_security_hardening.py"),
    # ---- 原有条目 ----
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


def _detect_version() -> str:
    """从 app/config.py 读取真实应用版本，读不到时返回 unknown。

    旧实现把版本号与验证状态**硬编码**在头部表格里，于是即使应用已升到 0.3.0，
    重新生成的快照仍然宣称 0.2.0、9 个测试文件 53 个用例 —— 派生物比源头还陈旧，
    上传到知识库后会直接误导读者。这里改为从唯一源头推导。
    """
    config_path = PROJECT_ROOT / "app" / "config.py"
    if not config_path.exists():
        return "unknown"
    match = re.search(
        r'^\s*version\s*:\s*str\s*=\s*["\']([^"\']+)["\']',
        config_path.read_text(encoding="utf-8"),
        re.MULTILINE,
    )
    return match.group(1) if match else "unknown"


def _count_tests() -> str:
    """统计测试文件数与用例数。

    说明：``def test_`` 静态计数会**低估**真实用例数，因为参数化测试
    （``@pytest.mark.parametrize``）在运行时展开成多条。本函数只给出规模量级，
    真实执行结果以 ``docs/QA-REPORT.md`` 为准。
    """
    tests_dir = PROJECT_ROOT / "tests"
    if not tests_dir.is_dir():
        return "unknown"
    files = sorted(tests_dir.glob("test_*.py"))
    total = 0
    for f in files:
        total += len(re.findall(r"^\s*def test_", f.read_text(encoding="utf-8", errors="replace"), re.MULTILINE))
    return f"{len(files)} 个测试文件 / {total} 个测试函数"


def _git_short_sha() -> str:
    """取当前 HEAD 短 SHA；非 git 环境返回 unknown。"""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=10,
        )
        return out.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


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
        f"| 交付版本 | {_detect_version()} |",
        f"| 提交 | `{_git_short_sha()}` |",
        f"| 测试规模 | {_count_tests()} |",
        f"| 生成时间 | {datetime.now().strftime('%Y-%m-%d %H:%M')} |",
        "",
        "> 上述版本号与提交由脚本从源码与 git 实时推导，不硬编码。",
        "> 「测试规模」是源码中 `def test_` 的**静态**计数，参数化用例会展开成更多条，",
        "> 故该数字低于真实执行数；**真实执行结果**（含通过数）以 `docs/QA-REPORT.md` 为准。",
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

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(lines), encoding="utf-8")
    total = sum((PROJECT_ROOT / p).read_text(encoding="utf-8", errors="replace").count("\n") + 1
                for _, p in present)
    print(f"已生成: {OUTPUT.relative_to(PROJECT_ROOT)}")
    print(f"收录文件数: {len(present)}")
    print(f"收录源码总行数: {total}")
    print(f"输出大小: {OUTPUT.stat().st_size / 1024:.1f} KB")


if __name__ == "__main__":
    main()
