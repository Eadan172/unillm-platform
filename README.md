# UniLLM Platform

一站式大模型开发平台：**数据接入 → 标注 → 微调 → 评测 → 推理** 全流程闭环，
并内置一个**可登录、可离线私有化部署**的原生 HTML 控制台。

后端基于 FastAPI + SQLAlchemy(SQLite)，同时提供 **OpenAI 兼容** 的推理接口。
无 GPU 环境也能完整跑通全链路（自动降级为确定性 mock 后端，并显式标注）。

> 版本 **0.3.0** —— 本版本在既有后端能力之上，补齐了**鉴权、统一错误契约、内置控制台、
> 容器化与一键启动**，让项目从「API 项目」走向「产品」。全程**零新增第三方依赖**。

---

## 快速开始

### 1. 环境要求

- Python 3.9 – 3.13（已在 3.13.12 实测）
- 无需 GPU / CUDA（真实模型推理需额外安装 GPU 依赖，见下文）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

安装体积约 5 MB，纯 CPU 环境即可完成全流程。

> **可选：GPU 增强**
> ```bash
> pip install -r requirements-gpu.txt   # vLLM 真实推理 + PEFT LoRA 微调，需 Linux + CUDA
> ```

### 3. 启动服务

```bash
# 方式一：读取 config.yaml 的 host/port
python -m app.main

# 方式二：指定 host/port
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

或使用一键脚本（自动建虚拟环境 → 装依赖 → 启动）：

```bash
./start.sh        # Linux / macOS
start.bat         # Windows
```

启动后访问：

| 地址 | 说明 |
|---|---|
| http://127.0.0.1:8000/console/ | **内置 Web 控制台**（登录后操作全流程） |
| http://127.0.0.1:8000/docs | Swagger 交互式 API 文档 |
| http://127.0.0.1:8000/redoc | ReDoc API 文档 |
| http://127.0.0.1:8000/health | 运行时健康状态（真实状态，非固定值，公开） |
| http://127.0.0.1:8000/api/info | 平台元信息（受保护） |

根路径 `/` 会 **302 重定向** 到 `/console/`。

---

## 端到端测试案例

`examples/sentiment_case/` 提供一个可直接复现的**情感二分类**闭环案例
（20 条训练 + 10 条测试，好评/差评各半，含挑战样本），一条命令跑通
「导入数据 → 建标注任务 → 注册模型 → 推理 → 评测」全链路，并打印指标汇总表。
在 mock 后端下它会显式提示：本次验证的是**链路可用性**而非模型效果。

```bash
# 1) 启动服务
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# 2) 另开终端，跑案例
python examples/sentiment_case/run_case.py
```

用法、字段规范与实测报告见 [`examples/sentiment_case/README.md`](examples/sentiment_case/README.md)。

---

## 登录与鉴权

### Token 从哪来

访问 `/api/*` 与 `/v1/*` 需要携带团队 Token。Token 来源优先级：

1. **配置显式指定**：`config.yaml` 的 `app.api_token`，或环境变量
   `UNILLM_APP__API_TOKEN`；
2. **自动生成**：未配置时，服务启动会生成一个随机 Token，**醒目打印在启动日志**中，
   并持久化到 `data/.api_token`（首次生成时权限设为 `0600`）。

启动日志形如：

```
============================================================================
  UniLLM Platform · 访问令牌（控制台登录用）
  Token: xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  提示：可用环境变量 UNILLM_APP__API_TOKEN 覆盖；设置 UNILLM_APP__AUTH_ENABLED=false 可关闭鉴权（本地开发）。
============================================================================
```

### 控制台怎么登录

打开 `/console/` → 输入 Token → 「进入控制台」。Token 保存在浏览器 `localStorage`，
刷新保持登录；顶栏「退出登录」清除凭证。

### 请求怎么带 Token

两种请求头任选其一（前端统一用 `Authorization`）：

```bash
# Bearer
curl -H "Authorization: Bearer <token>" http://127.0.0.1:8000/api/data/list
# X-API-Token
curl -H "X-API-Token: <token>" http://127.0.0.1:8000/api/data/list
```

### 路径保护矩阵

| 路径 | 是否受保护 |
|---|---|
| `/console/*` | 公开（页面本身公开，**数据全部经鉴权 API 拉取**） |
| `/health`、`/docs`、`/redoc`、`/openapi.json` | 公开 |
| `/api/*`（含 `/api/info`、`/api/auth/verify`） | **受保护** |
| `/v1/*` | **受保护** |
| 任意路径的 `OPTIONS` 预检 | 放行（不鉴权） |

### 本地开发关闭鉴权

```bash
export UNILLM_APP__AUTH_ENABLED=false   # 关闭后 /api/*、/v1/* 全部免鉴权
```

> 关闭仅建议用于本机开发；内网共享时请保持开启并妥善保管 Token。

---

## Docker 部署

### 构建与启动

```bash
# 一行启动（首次会构建镜像）
docker compose up --build
```

启动后访问 http://127.0.0.1:8000/console/ 。

### 关键约定

- **构建需要外网**：`docker build` 会执行 `pip install` 从 PyPI 拉取依赖。
- **固定单 worker**：SQLite 单文件数据库，`docker-compose.yml` 固定 `--workers 1`，
  多 worker 会加剧写锁竞争。
- **数据卷持久化**：挂载 `./data` 与 `./logs`；自动生成的 Token 落在 `./data/.api_token`，
  若不挂载，容器重建会换新 Token。
- **Token 注入二选一**：
  ```bash
  # a) 显式注入
  UNILLM_APP__API_TOKEN=你的Token docker compose up
  # b) 留空：自动生成并打印在 `docker compose logs` 中，同时写入 ./data/.api_token
  docker compose up
  ```

### 离线构建替代方案（无外网内网环境）

`docker build` 默认需要外网。若无外网，请任选其一：

1. **预置 wheel 目录**：在有网机器上
   ```bash
   pip download -r requirements.txt -d ./wheels
   ```
   把 `wheels/` 拷入内网后，在 `Dockerfile` 中改为离线安装：
   ```dockerfile
   COPY wheels ./wheels
   RUN pip install --no-index --find-links=./wheels -r requirements.txt
   ```
2. **使用内网离线基础镜像**：将 `FROM python:3.11-slim` 换为内网镜像仓库中的等价镜像，
   并在其中预置好依赖。

---

## 控制台页面

| 页面 | 地址 | 主要能力 |
|---|---|---|
| 登录 | `/console/login.html` | Token 登录 |
| 总览 | `/console/index.html` | 环境状态、模型/数据集计数、快捷入口、服务信息 |
| 数据集 | `/console/datasets.html` | 列表 / 导入 / 新建空数据集 / 详情 / 导出下载 / 删除 |
| 标注（P1） | `/console/annotation.html` | 任务列表 / 新建 / 工作台逐条标注 / 进度 / 空答案拦截 |
| 模型 | `/console/models.html` | 列表 / 注册 / 加载（降级如实显示）/ 卸载 / 后端状态 |
| 推理试验台 | `/console/playground.html` | chat / completion 双模式、参数、**强制 backend 徽章** |
| 微调（P1） | `/console/finetune.html` | 新建（前置警告）/ 启动 / 状态轮询 / 取消（软取消）/ 失败原因 |
| 评测 | `/console/evaluate.html` | 新建 / 运行 / 结果页（**不可用指标如实呈现**）/ 内联样本 / 历史 |

**设计原则**：控制台零外部 CDN、零构建，断网可用；顶栏 / 侧栏 / 降级横幅由
`app/web/assets/layout.js` 一处注入；全站文案仅简体中文。

---

## 核心接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/auth/verify` | 登录探针（受保护） |
| GET | `/api/info` | 平台元信息（受保护） |
| POST | `/api/data/import` | 上传文件并导入为数据集（`json` / `jsonl` / `csv`） |
| POST | `/api/data/create` | 创建空数据集 |
| GET | `/api/data/list` | 数据集列表 |
| GET | `/api/data/{id}/export` | 导出为训练用 JSONL（返回服务端产物路径） |
| GET | `/api/data/{id}/export/download` | **下载**训练用 JSONL（`Content-Disposition` 附件） |
| POST | `/api/annotation/task` | 创建标注任务 |
| POST | `/api/annotation/submit` | 提交标注结果（空答案返回 400） |
| POST | `/api/model/register` | 注册模型 |
| POST | `/api/model/load` / `unload` | 加载 / 卸载模型 |
| GET | `/api/model/backend` | 查看当前推理后端及其真实性 |
| POST | `/v1/chat/completions` | OpenAI 兼容对话补全 |
| POST | `/v1/completions` | OpenAI 兼容文本补全 |
| GET | `/v1/models` | OpenAI 兼容模型列表 |
| POST | `/api/finetune/create` / `{id}/start` | 创建并启动微调任务 |
| POST | `/api/evaluate/create` / `{id}/run` | 创建并运行评测 |

### 统一错误契约

所有错误响应结构一致，且**始终包含 `detail`**：

```json
{ "detail": "人类可读信息（简体中文）", "error_code": "BAD_REQUEST", "hint": null }
```

| `error_code` | HTTP | 触发点 |
|---|---|---|
| `UNAUTHORIZED` | 401 | 缺失 / 无效 Token |
| `VALIDATION_ERROR` | 422 | 请求参数校验失败（中文摘要） |
| `BAD_REQUEST` | 400 | 既有业务校验失败（detail 原样保留） |
| `NOT_FOUND` | 404 | 资源不存在 |
| `PAYLOAD_TOO_LARGE` | 413 | 上传超限 |
| `INTERNAL_ERROR` | 500 | 未捕获异常（堆栈只进服务端日志，不外泄） |

### 支持的评测指标

| 指标 | 定义 | 实现方式 |
|---|---|---|
| `exact_match` | 归一化后完全一致的比例 | 去空白、转小写、去中英文标点后精确比对 |
| `token_f1` | 字符级 F1 的宏平均 | 按字符切分，对中英文都稳定 |
| `latency` | 端到端推理耗时 | 逐样本实测，给 min/avg/p50/p95/max |
| `perplexity` | 困惑度 | 需 `torch` + `transformers`；未安装时返回 `available: false` 并说明原因，不填占位值 |

`accuracy` 作为历史别名保留，映射为 `exact_match` + `token_f1` 两项。

---

## 配置

配置来源优先级：**显式 init 参数 > 环境变量 > `config.yaml` > 代码默认值**。

环境变量统一前缀 `UNILLM_`，嵌套层级用 `__` 分隔：

```bash
export UNILLM_DATABASE__PATH=/data/unillm.db      # 数据库路径
export UNILLM_APP__PORT=9000                       # 服务端口
export UNILLM_STORAGE__DATASETS_PATH=/data/datasets
export UNILLM_APP__AUTH_ENABLED=true               # 鉴权开关
export UNILLM_APP__API_TOKEN=your-team-token       # 团队 Token
export UNILLM_APP__API_TOKEN_FILE=./data/.api_token # 自动生成 Token 的落盘位置
export UNILLM_CONFIG_FILE=/etc/unillm/config.yaml  # 指定配置文件
```

因为所有配置都带 `UNILLM_` 前缀，系统里的 `PATH` / `PORT` / `NAME` 等同名变量
**不会**污染配置。

---

## 测试与验证

```bash
# 门 1：单元/集成测试（含鉴权、错误契约与安全加固）
python -m pytest -q

# 门 2：端到端冒烟（启动真实 uvicorn 进程，走 HTTP 全链路）
python scripts/smoke_test.py

# 门 3（可选）：前端「缺失值不落 0」逻辑 + datasets.html 静态回归检查
#   仅在校验前端逻辑时需要 node；运行产品本身不需要 node（本项目仍是零构建）
node scripts/frontend_logic_check.js
```

预期输出：`167 passed`；冒烟脚本输出 `15/15 项通过`；前端检查输出 `13/13 passed`。

> 若本机 sandbox 拦截 pytest 的退出清理（`SAFE_DELETE_BULK_REJECTED`），把临时目录移出系统 `%TEMP%` 再跑即可得到干净计数：
> `TMP=.tmp_pytest TEMP=.tmp_pytest TMPDIR=.tmp_pytest python -m pytest -q --basetemp=.tmp_pytest`

| 层次 | 覆盖内容 |
|---|---|
| `tests/test_metrics.py` | 指标单元（EM / 字符 F1 / 归一化 / 分位数） |
| `tests/test_closed_loop.py` | 健康检查、导入、注册、推理、评测、数据闭环 |
| `tests/test_upload_safety.py` | 路径穿越、非法扩展名、超限、孤儿数据回滚 |
| `tests/test_auth.py` | 鉴权开关（逐请求生效）、双请求头、401、公开路径、OPTIONS 豁免、Token 持久化 |
| `tests/test_errors.py` | `detail` 保留、`error_code` 枚举、422 中文摘要、500 不泄露堆栈 |
| `tests/test_security_hardening.py` | 鉴权与错误契约的边界/安全加固用例 |
| `tests/test_input_validation.py` | 导入输入校验（空文件 / 无可识别内容字段 → 400）、评测 `model_id` 存在性校验 |
| `scripts/smoke_test.py` | 真实进程 15 项断言（含「无 Token → 401」） |
| `scripts/frontend_logic_check.js` | 前端缺失值不落 0 逻辑 + `datasets.html` 静态回归（需 node，可选） |

---

## 目录结构

```
unillm-platform/
├── app/
│   ├── main.py                  # 应用入口、lifespan（打印 Token）、CORS、/health、/console 托管
│   ├── config.py                # 配置（YAML + 环境变量覆盖 + 鉴权字段）
│   ├── core/
│   │   ├── security.py          # Token 解析/校验/持久化 + AuthMiddleware
│   │   └── errors.py            # 统一错误体 + 三类全局异常处理器
│   ├── api/
│   │   ├── deps.py              # 统一依赖注入
│   │   └── routes/
│   │       ├── auth.py          # /api/auth/verify、/api/info
│   │       ├── data.py          # /api/data/*（含 export/download）
│   │       ├── annotation.py    # /api/annotation/*
│   │       ├── model.py         # /api/model/*
│   │       ├── inference.py     # /v1/*
│   │       ├── finetune.py      # /api/finetune/*
│   │       └── evaluate.py      # /api/evaluate/*
│   ├── models/
│   │   ├── database.py          # ORM 模型 + 进程内单例 Engine/Session
│   │   └── schemas.py           # Pydantic 请求/响应模型
│   ├── services/                # 业务逻辑（每个路由一个 service）
│   └── web/                     # 内置控制台（原生 HTML/CSS/JS，零 CDN）
│       ├── *.html               # 8 个页面
│       └── assets/              # app.css / api.js / layout.js
├── tests/                       # pytest：指标、闭环、上传安全、鉴权、错误契约
├── scripts/smoke_test.py        # 真实进程端到端冒烟
├── Dockerfile                   # 容器镜像（python:3.11-slim，单 worker）
├── docker-compose.yml           # 一键编排
├── .dockerignore                # 排除 data/（含 Token）、logs/、docs/ 等
├── start.sh / start.bat         # 一键启动（Linux/macOS 与 Windows）
├── config.yaml                  # 默认配置
├── requirements.txt             # 核心依赖（CPU）
└── requirements-gpu.txt         # GPU 增强依赖（可选）
```

---

## 运行模式与降级说明

平台有两条明确的运行路径：

| 后端 | 触发条件 | 响应特征 |
|---|---|---|
| `vllm` | 已安装 vLLM 且模型加载成功 | 真实模型输出，`backend_is_real_model: true` |
| `mock` | 未安装 vLLM | 确定性占位文本，以 `[MOCK]` 开头，响应体 `backend: "mock"` |

**降级是显式的，不是静默的**：`/health` 返回 `degraded: true`，控制台全站顶部显示
**不可关闭的橙色横幅**；模型加载降级显示「已切换到占位后端」而非「加载成功」；
评测结果带可信度标注；不可用指标（如未装 torch 的 perplexity）显示「不可用 + 原因」，
**绝不显示占位数字**。

---

## 已知限制

这些限制是**真实存在**的，不做掩饰：

1. **真实推理需要 GPU 依赖**：未安装 vLLM 时推理走 mock 后端，指标不具参考价值。
2. **困惑度需要 torch**：未安装时如实返回 `available: false`，不估算、不填占位数字。
3. **微调任务未真正训练**：LoRA 微调任务的状态机与产物路径已打通，但实际训练需要
   `requirements-gpu.txt`，当前环境无法验证，故仅保证任务编排链路可用。
4. **SQLite 单机约束**：并发写入高时不适合生产；多实例部署需换 PostgreSQL，
   且必须保持单 worker。
5. **并发与限流未实现**：服务侧没有请求限流、没有推理队列，高并发下需前置网关。
6. **鉴权为单 Token 共享模型**：适合内网小团队；不含账号体系、角色权限与数据隔离。
7. **Docker 构建需外网**：见上文「离线构建替代方案」。
8. **公开的 `/health` 会暴露数据库绝对路径（QA O-1，有意保留）**：`/health` 无需鉴权即可访问，
   其 `database` 字段返回服务端**绝对路径**（例如 `/app/data/unillm.db`）。这意味着任何能访问
   该服务的人都能读到部署目录布局。这是一个**有意保留的取舍**，不是遗漏：`/api/*` 与 `/v1/*`
   全部已鉴权，泄露的仅是目录结构、并非凭证或业务数据；且既有测试
   `tests/test_closed_loop.py:38` 断言该字段包含 `unillm-test-`，改动需连带修改测试契约，
   收益不足。**风险直说**：若把该服务暴露到不可信网络，攻击者可据此推断部署路径；此时应改为
   在 `/health` 中脱敏该字段，或在反向代理层限制 `/health` 的访问来源。

---

## 许可

见仓库 `LICENSE`。
