# UniLLM Platform - 统一多模态大模型平台

<p align="center">
  <a href="https://github.com/your-username/unillm-platform"><img alt="GitHub Repo" src="https://img.shields.io/badge/GitHub-Repo-blue?logo=github"></a>
  <a href="https://github.com/your-username/unillm-platform/stargazers"><img alt="GitHub Stars" src="https://img.shields.io/github/stars/your-username/unillm-platform"></a>
  <a href="https://github.com/your-username/unillm-platform/fork"><img alt="GitHub Forks" src="https://img.shields.io/github/forks/your-username/unillm-platform"></a>
  <a href="https://github.com/your-username/unillm-platform/blob/main/LICENSE"><img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg"></a>
</p>

## 📖 项目简介

**UniLLM Platform** 是一个**一站式大模型开发平台**，支持从数据接入 → 标注 → 微调 → 评测 → 推理的全流程闭环。该平台专为个人开发环境设计，可在单卡 GPU 上运行完整的模型开发流程。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          平台核心能力                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   📥 数据接入    →    📝 数据标注    →    🎯 模型微调                       │
│   (CSV/JSON/API)     (人工/自动)         (LoRA/SFT)                         │
│                                                                             │
│         ↓                                                                   │
│                                                                             │
│   📊 模型评测    →    🚀 模型推理    →    🔌 API服务                        │
│   (多维度指标)       (vLLM高性能)         (OpenAI兼容)                       │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## ✨ 核心特性

| 特性 | 说明 |
|------|------|
| 🔧 **数据管理** | 支持 CSV/JSON/JSONL 格式导入，自动解析并存储 |
| 📝 **数据标注** | 文本标注任务管理，支持多人协作标注 |
| 🚀 **模型推理** | 基于 vLLM 的高性能推理，OpenAI API 兼容 |
| 🎯 **模型微调** | LoRA 参数高效微调，单卡可运行 |
| 📊 **模型评测** | 多维度评测指标（Perplexity、Accuracy、Latency） |
| 🔌 **RESTful API** | 完整的 FastAPI 接口，自动生成文档 |

## 🛠️ 技术栈

```
┌─────────────────────────────────────────────────────────────────┐
│                    技术栈总览                            │
├─────────────────────────────────────────────────────────────────┤
│  Web框架:     FastAPI + Uvicorn                         │
│  推理引擎:    vLLM (PagedAttention)                     │
│  微调框架:    PEFT + Transformers                       │
│  数据库:      SQLite + SQLAlchemy                       │
│  数据处理:    Pandas + PyArrow                          │
│  配置管理:    Pydantic + YAML                           │
└─────────────────────────────────────────────────────────────────┘
```

## 📦 快速开始

### 环境要求

- Python 3.9+
- CUDA 11.8+ (GPU 推理/微调)
- 16GB+ RAM (最低)
- 24GB+ VRAM (7B 模型微调)

### 安装

```bash
# 1. 克隆仓库
git clone https://github.com/your-username/unillm-platform.git
cd unillm-platform

# 2. 安装依赖
pip install -r requirements.txt

# 3. 启动服务
python -m app.main
```

### 访问服务

启动后访问：

- **API 文档 (Swagger UI)**: http://localhost:8000/docs
- **API 文档 (ReDoc)**: http://localhost:8000/redoc
- **健康检查**: http://localhost:8000/health

## 📚 使用示例

### 1. 数据导入

```python
import httpx

BASE_URL = "http://localhost:8000"

# 导入数据集
with open("your_data.jsonl", "rb") as f:
    response = httpx.post(
        f"{BASE_URL}/api/data/import",
        params={"name": "my_dataset", "description": "我的数据集"},
        files={"file": f}
    )
dataset_id = response.json()["id"]
print(f"数据集ID: {dataset_id}")
```

### 2. 数据标注

```python
# 创建标注任务
response = httpx.post(
    f"{BASE_URL}/api/annotation/task",
    json={
        "name": "标注任务1",
        "dataset_id": dataset_id,
        "annotation_type": "text"
    }
)

# 获取待标注数据
response = httpx.get(f"{BASE_URL}/api/annotation/task/{task_id}/next")

# 提交标注结果
response = httpx.post(
    f"{BASE_URL}/api/annotation/submit",
    params={"annotation_id": annotation_id},
    json={
        "output_text": "这是标注结果",
        "annotator": "user1"
    }
)
```

### 3. 模型微调

```python
# 注册模型
response = httpx.post(
    f"{BASE_URL}/api/model/register",
    params={
        "name": "my_model",
        "base_model": "Qwen/Qwen2.5-7B-Instruct"
    }
)
model_id = response.json()["id"]

# 创建微调任务
response = httpx.post(
    f"{BASE_URL}/api/finetune/create",
    json={
        "model_id": model_id,
        "dataset_id": dataset_id,
        "job_name": "微调任务1",
        "method": "lora"
    }
)
job_id = response.json()["id"]

# 启动微调
response = httpx.post(f"{BASE_URL}/api/finetune/{job_id}/start")

# 查询微调状态
response = httpx.get(f"{BASE_URL}/api/finetune/{job_id}/status")
```

### 4. 模型推理

```python
# 加载模型
response = httpx.post(
    f"{BASE_URL}/api/model/load",
    json={"model_name": "Qwen/Qwen2.5-7B-Instruct"}
)

# 对话推理 (OpenAI 兼容)
response = httpx.post(
    f"{BASE_URL}/v1/chat/completions",
    json={
        "model": "Qwen/Qwen2.5-7B-Instruct",
        "messages": [
            {"role": "user", "content": "你好，请介绍一下自己"}
        ],
        "max_tokens": 512
    }
)
print(response.json()["choices"][0]["message"]["content"])
```

## 🏗️ 项目结构

```
unillm-platform/
├── app/
│   ├── __init__.py
│   ├── main.py                    # FastAPI 入口
│   ├── config.py                  # 配置管理
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes/
│   │       ├── data.py            # 数据管理 API
│   │       ├── annotation.py      # 标注 API
│   │       ├── model.py           # 模型管理 API
│   │       ├── inference.py       # 推理 API (OpenAI 兼容)
│   │       ├── finetune.py        # 微调 API
│   │       └── evaluate.py        # 评测 API
│   ├── services/
│   │   ├── __init__.py
│   │   ├── data_service.py        # 数据服务
│   │   ├── annotation_service.py  # 标注服务
│   │   ├── model_service.py       # 模型服务
│   │   ├── inference_service.py   # 推理服务
│   │   ├── finetune_service.py    # 微调服务
│   │   └── evaluate_service.py    # 评测服务
│   ├── models/
│   │   ├── __init__.py
│   │   ├── database.py            # 数据库模型
│   │   └── schemas.py             # Pydantic 模型
│   └── utils/
│       └── __init__.py
├── data/
│   └── datasets/
│       └── sample_data.jsonl      # 示例数据
├── docs/
│   └── 评测分析报告.md
├── requirements.txt
├── config.yaml
├── .gitignore
└── README.md
```

## 📊 应用场景

### 医药健康领域

| 场景 | 说明 |
|------|------|
| **智能问诊助手** | 24/7 提供初步问诊服务 |
| **用药咨询机器人** | 提供用药指导和药物相互作用分析 |
| **健康管理顾问** | 个性化健康建议和康复计划 |
| **医学文献助手** | 文献检索、摘要和研究趋势分析 |

### 电商领域

| 场景 | 说明 |
|------|------|
| **智能客服助手** | 7x24 小时自动回复，解决 80% 常见问题 |
| **商品推荐顾问** | 个性化商品推荐和搭配建议 |
| **营销文案生成** | 自动生成高质量商品描述和促销文案 |
| **评价分析系统** | 情感分析和问题提取 |

### 其他领域

- **金融**：智能投顾、客服问答、风险评估
- **教育**：智能辅导、作业批改、知识问答
- **法律**：法律问答、合同审查、案例检索

## 🤝 贡献指南

欢迎提交 Issue 和 Pull Request！

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

## 🙏 致谢

- [vLLM](https://github.com/vllm-project/vllm) - 高性能推理引擎
- [PEFT](https://github.com/huggingface/peft) - 参数高效微调
- [FastAPI](https://fastapi.tiangolo.com/) - Web 框架
- [Transformers](https://huggingface.co/docs/transformers) - 模型库

## 📞 联系方式

如有问题或建议，欢迎通过以下方式联系：

- GitHub Issues: [提交问题](https://github.com/your-username/unillm-platform/issues)
- Email: your-email@example.com

---

**如果本项目对您有帮助，请给个 Star ⭐ 支持一下！**

---

## 🚀 下一步

- 查看 [评测分析报告.md](docs/评测分析报告.md) 了解评测详情
- 运行 `python evaluation_auto.py` 进行评测演示
- 准备领域数据，开始您的大模型落地之旅！
