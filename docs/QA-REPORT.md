# QA 独立验证报告 · UniLLM Platform 控制台化改造

- **验证人**：严过关（QA Engineer，独立于实现方）
- **验证对象**：`unillm-platform` 本轮「后端 API → 带内置 Web 控制台的产品」改动
- **方法立场**：**怀疑优先 / 证伪导向**。不重跑实现方跑过的命令即下结论；所有结论均附独立复现证据（HTTP 状态码、真实响应头、代码行号）。
- **结论**：**通过（PASS）**。无阻断性缺陷（P0/P1 = 0）；发现 2 项低severity 观察项（P3，非阻断）。

> **本报告的覆盖范围与后续轮次导航（后补，非本报告原始内容）**
>
> 本文件是**控制台化改造那一轮**的独立验证报告，**只覆盖到该轮为止**。此后平台又经历了多轮
> 独立对抗性验证与修复，报告散落在端到端案例目录下，**读者不应把本报告当作全项目的最新验证结论**：
>
> **轮次编号基准（重要，避免与其他文档对不上）**：下表**以本报告所覆盖的「控制台化改造那一轮」
> 为第 1 轮起算**。项目协作中曾使用另一套口径（把控制台化那轮也算作第 1 轮之后另计），
> 两种数法会**相差一轮**。若你在别处看到「第三轮 / 第四轮」，请以**报告文件名**为准，
> 不要以轮次序号为准。
>
> | 轮次（本表口径） | 验证对象 | 报告 | 结论 |
> |---|---|---|---|
> | 第二轮 | 情感分类端到端案例包 | `examples/sentiment_case/QA-VERIFY.md` | 见报告 |
> | 第三轮 | 平台输入校验（A1/A2/A3）与报告不实核对 | `examples/sentiment_case/QA-VERIFY-2.md` | 发现 2 条 P1（孤儿行 / 500） |
> | 第四轮 | 数值 0 判定、非标量拒绝、评测样本口径 | `examples/sentiment_case/QA-VERIFY-3.md`（已修订至 v2） | PASS with issues；无 P1；2 条 P2 |
> | 第五轮 | 标量契约修复复验 | `examples/sentiment_case/QA-VERIFY-4.md` | 4 项改动实测成立；另发现 1 条**本轮引入的回归**（已修） |
>
> 各轮**实测数据与结论汇总**见 `examples/sentiment_case/TEST-REPORT.md`（其 §九 逐轮登记了平台侧改动，
> §十一 为独立 QA 交叉引用索引）。

---

## 一、验证环境与范围

| 项目 | 内容 |
|---|---|
| 解释器 | `D:\WorkBuddy\.workbuddy\binaries\python\envs\unillm\Scripts\python.exe`（Python 3.13.14） |
| 框架 | FastAPI + Starlette（BaseHTTPMiddleware）+ SQLAlchemy(SQLite) + Pydantic v2 |
| 证据手段 | ① 源码阅读（贴行号）② 进程内真实 ASGI 栈（Starlette TestClient）③ **真实 uvicorn 进程 + HTTP**（独立于 TestClient）④ 端到端冒烟脚本 ⑤ 与源码快照基线 diff |
| 已验证的关键项 | 鉴权逐请求生效、鉴权绕过的**对抗性**尝试、不造假渲染、共享组件单一来源、下载头注入、既有测试是否被削弱、配置/忽略文件、错误契约(401/400/404/405/413/422/500)、CORS 顺序 |
| **明确未能验证** | Docker 镜像构建、真实浏览器渲染/交互（本机无 Docker、无浏览器，见第四节） |

复现命令（可自行重跑）：
```bash
python -m pytest -rs              # 全量：121 passed，0 skipped / 0 xfailed
python scripts/smoke_test.py --port 8125   # 真实 uvicorn 端到端：15/15
```

---

## 二、逐项验证结果表

| # | 验证项 | 方法 | 实际结果 | 结论 |
|---|---|---|---|---|
| 1 | 鉴权开关**逐请求**生效（非构造快照） | 读 `app/core/security.py` + 同一 TestClient 内翻转开关 | `dispatch()` 内**每次请求**读 `settings.app.auth_enabled`（security.py:149-151，无 `self.auth_enabled`）；实测 `True→False→True` 得 `401/200/401` | **PASS** |
| 1b | 真实进程下开关生效 | 两个独立 uvicorn 进程（:8123 auth=on / :8124 auth=off） | on：`/api/data/list` 无 Token=401；off：同路径=200，`/api/auth/verify` 返回 `{"valid":true,"auth_enabled":false}` | **PASS** |
| 2 | 鉴权绕过（对抗） | 8 种路径变形 + 7 种头部伪造，真实 HTTP | 全部 `401`（被拦）或 `404`（无该路由，不泄露数据）；**无任何 200 放行**。见下方证据 | **PASS** |
| 3 | 不造假渲染（perplexity） | 读 `evaluate.html` 分支 + 跑评测取原始 JSON | `ppl.available===true` 才走数字分支；否则走独立 `unavailableCard`（含 reason/how_to_enable，**无数字/进度条/百分比**，evaluate.html:249-264）。原始 JSON：`perplexity.available=false` + `reason` + `how_to_enable`；`backend_is_real_model=false` | **PASS** |
| 3b | 不造假渲染（models 降级） | 读 `models.html:174-197` | `status==='degraded'` 独立分支显示「已切换到占位后端」，**不含「加载成功」**；成功分支为独立 `else if` | **PASS** |
| 3c | 全站兜底写法扫描 | grep `|| 0`/`?? 0`/`Number(`/`parseFloat`/`toFixed(` | 命中 2 处 `asNumber(...)||0`（datasets.html:75-76，见观察项 O-2）；`parseFloat` 仅用于**用户表单输入**（playground.html:88-91），非后端数据。其余数字渲染均经类型判定 `Layout.asNumber`（layout.js:36-44） | **PASS（含 1 观察项）** |
| 3d | 降级横幅单一来源 | grep 全站 | `renderBanner` 仅定义于 `layout.js:180`，仅依赖 `health.degraded===true`；各页仅留容器 `<div id="app-banner">` | **PASS** |
| 4 | 共享组件「只有一份」 | grep 8 个 HTML | 8 页均**无**硬编码顶栏/侧栏/品牌 DOM（`ullm-topbar`/`ullm-nav-item`/`ullm-brand` 在 HTML 中 0 命中）；5 个容器 id 齐备，`login.html` 仅 `#page-content`+`#app-toast`（按设计例外） | **PASS** |
| 4b | 公开页无硬编码密钥/默认值 | grep `token`/`/data/`/`.db`/`Qwen`/`Bearer` | 无 Token、无 DB 路径、无默认模型名；仅 API 路径字符串 | **PASS** |
| 5 | 下载 header 注入防护 | 构造 7 类恶意数据集名，真实请求下载 | 见下方证据：`Content-Disposition` 中 `"`→`_`、`\n\r`→`_`、`/`→`_`，无裸换行、引号成对 | **PASS** |
| 5b | `/export` 与 `/export/download` 错误路径一致 | 无标注样本 | 均 `400` 且 `detail` **逐字相同** | **PASS** |
| 5c | 既有 `/export` 行为未改 | 有标注样本 | 返回 `{"status":"success","dataset_id":..,"output_path":..}` JSON | **PASS** |
| 6 | 既有测试是否被削弱 | 与源码快照 `unillm-platform_源码全文.md` 逐行 diff | `conftest.py` **仅 +1 行**（`auth_enabled=False`）；`test_metrics.py`/`test_closed_loop.py`/`test_upload_safety.py` **逐字节一致** | **PASS** |
| 7 | 无 skip/xfail 充数 | `pytest -rs` | `121 passed`（原 75 + 新 46），**0 skipped / 0 xfailed / 0 error** | **PASS** |
| 8 | 版本三处一致 | 读 config + openapi | `config.py:48`=`0.3.0`、`config.yaml`=`0.3.0`、FastAPI openapi `info.version`=`0.3.0` | **PASS** |
| 9 | `.gitignore` 忽略密钥 | 读文件 | 第 129 行 `data/.api_token` | **PASS** |
| 10 | `.dockerignore` 排除运行期数据 | 读文件 | 含 `.git`、`__pycache__`、`data`（覆盖 `.api_token`）、`logs` | **PASS** |
| 11 | CORS 最外层 | 读 `main.py` + 真实 OPTIONS 预检 | 先 `add_middleware(Auth)` 再 `add_middleware(CORS)`（后加的更靠外，main.py:92-103）；真实预检 `OPTIONS` → `200` + `ACAO=*`（非 401） | **PASS** |
| 12 | 统一错误体三键 | 触发 401/400/404/405/413/422/500 | 全部含 `{detail,error_code,hint}`；422 为**中文摘要**（`请求体.name：缺失必填项`）；500 固定文案、**无 traceback / 无内部串泄露** | **PASS** |
| 13 | 测试断言质量 | 读 `test_auth.py` / `test_errors.py` | 断言真实响应体（状态码+`error_code`+`detail`文案），非复读实现；**未发现恒真假测试** | **PASS** |

---

## 三、关键证据

### 2. 绕过尝试（真实 uvicorn :8123，全部无 Token）
```
/API/data/list          -> 404 {"detail":"Not Found","error_code":"NOT_FOUND","hint":null}
//api/data/list         -> 404 {"detail":"Not Found","error_code":"NOT_FOUND","hint":null}
/api/data/list/         -> 401 {"detail":"未提供访问令牌",...}
/api/../api/data/list   -> 401
/console/../api/data/list -> 401
/%61pi/data/list        -> 401
/api%2Fdata/list        -> 401
Authorization: Bearer   -> 401   （空值）
Authorization: <token>  -> 401   （缺 Bearer 前缀）
X-API-Token: wrong      -> 401
```
> 说明：大小写变形与 `//` 返回 **404**（路由大小写敏感、无匹配路由），**不是绕过**——受保护数据从未被返回；其余变形均被中间件 401 拦截。

### 3. 评测原始 JSON（mock 后端，故意勾选 perplexity）
```json
{
  "status": "completed",
  "results": {
    "sample_count": 1, "backend": "mock", "backend_is_real_model": false,
    "exact_match": {"value": 0.0, "correct": 0, "total": 1},
    "token_f1": {"value": 0.0211, "unit": "char", "total": 1},
    "latency": {"avg_ms": 2.57, "p50_ms": 2.57, "p95_ms": 2.57, "samples": 1},
    "perplexity": {
      "available": false,
      "reason": "未安装 torch / transformers",
      "how_to_enable": "pip install -r requirements-gpu.txt（需 Linux + CUDA）"
    }
  }
}
```
> `perplexity.available=false` 且带 `reason`/`how_to_enable`，**未给出任何假数值**；`backend_is_real_model=false` 如实标注。渲染分支见 `evaluate.html:249-264`（`available===true` 才进数字卡）。

### 5. 下载头注入（真实响应头）
```
name=`evil";\r\nX-Injected: 1`  -> content-disposition: attachment; filename*=utf-8''evil_%3B_X-Injected%3A%201_training.jsonl
name=`line1\nline2\r\n...`       -> content-disposition: attachment; filename*=utf-8''line1_line2_Content-Length%3A%200_training.jsonl
name=`../../etc/passwd`          -> content-disposition: attachment; filename=".._.._etc_passwd_training.jsonl"
name=`a/b/c`                     -> attachment; filename="a_b_c_training.jsonl"
name=`中文数据集名`               -> attachment; filename*=utf-8''%E4%B8%AD%E6%96%87...jsonl
```
净化逻辑：`app/api/routes/data.py:33` `_HEADER_UNSAFE_CHARS = re.compile(r'[\r\n\t"\\/]+')` + `data.py:45-51 _sanitize_download_name`。**无裸换行、无未转义引号。PASS。**

### 6. 既有测试未被削弱（基线 diff）
> 注：本仓库 `git` 的 HEAD 基线**不包含 `tests/` 目录**（`git ls-files tests/` 为空），故无法用 `git diff` 验证；改用项目自带的源码快照 `unillm-platform_源码全文.md`（其 conftest 为**改动前**版本，自证非事后生成）逐行比对：
```
[DIFF] tests/conftest.py   @@ -27,2 +27,3 @@
     settings.app.debug = False
    +settings.app.auth_enabled = False      ← 唯一新增行
     settings.evaluation.max_samples = 100
[IDENTICAL] tests/test_metrics.py
[IDENTICAL] tests/test_closed_loop.py
[IDENTICAL] tests/test_upload_safety.py
```
测试计数交叉验证：75（全量）− 13（test_auth）− 9（test_errors）= **53**，与「53 个既有测试」自述吻合。

### 12. 错误契约（真实响应体）
```
401 -> {"detail":"未提供访问令牌","error_code":"UNAUTHORIZED","hint":"..."}
422 -> {"detail":"请求参数校验失败（请求体.name：缺失必填项）","error_code":"VALIDATION_ERROR",...}
404 -> {"detail":"Dataset not found","error_code":"NOT_FOUND","hint":null}
400 -> {"detail":"skip 必须 >= 0，limit 必须 > 0","error_code":"BAD_REQUEST","hint":null}
405 -> {"detail":"Method Not Allowed","error_code":"METHOD_NOT_ALLOWED","hint":null}
413 -> {"detail":"文件超过 0MB 上限","error_code":"PAYLOAD_TOO_LARGE","hint":null}
500 -> {"detail":"服务器内部错误","error_code":"INTERNAL_ERROR","hint":"请查看服务端日志以获取详细信息"}
       且响应中不含 "Traceback" / 注入的内部串
```

---

## 四、发现的缺陷清单

> 本轮**无 P0/P1/P2 缺陷**。以下为 2 项 P3 观察项（不阻断交付，供团队决议）。

| 编号 | 严重度 | 位置 | 复现/证据 | 期望 vs 实际 | 归属 |
|---|---|---|---|---|---|
| **O-1** | **P3（信息泄露·已知取舍）** | `app/main.py:146`、`app/models/schemas.py` `HealthResponse.database` | 公开端点 `/health` 无 Token 即返回 `"database":"C:\\...\\data\\unillm.db"`（实测） | 期望：公开端点不暴露服务器文件系统路径；实际：暴露 DB 绝对/相对路径。**原因**：`database` 是既有测试契约字段，不可移除。**风险评估（诚实）**：仅泄露部署布局，**不含任何凭证**；攻击者无法据此直接访问文件（无文件读取端点，`/api/*` 已鉴权）。综合评级 **低**。建议后续将 `database` 改为布尔/掩码（如 `"database":"sqlite"`）或移入受保护端点，但需同步修改既有测试契约。 | Engineer（非阻断，需团队确认是否保留契约） |
| **O-2** | **P3（渲染兜底）** | `app/web/datasets.html:75-76` | `grep -n "|| 0"` 命中：`total += Layout.asNumber(taskList[i].total_items) || 0;` | 期望（架构硬要求）：缺失/非数字一律渲染「未知」，绝不落 0；实际：标注任务数**求和**时，缺失值被当作 0 累加，极端情况下会显示 `0` 而非「未知」。**影响面小**：仅用于数据集详情的标注进度汇总；数据集自身「样本数」列正确使用 `Layout.numOrUnknown`（datasets.html:100）。 | Engineer（前端，非阻断） |

**判定说明**：
- `config.yaml:53-57 evaluation.metrics` 含 `accuracy`（非正式指标名）—— 经核实为**有意为之**：`evaluate_service.py:147-149` 显式兼容旧配置 `"accuracy"→exact_match`，非缺陷。
- 头部伪造 `坏 Authorization + 好 X-API-Token` → `401`：`Authorization` 优先级高于 `X-API-Token`（`security.py:44-48`），**符合设计契约**（"优先 Authorization"），非缺陷，已在新增测试中锁定该行为。

---

## 五、未能验证的项（诚实列出）

| 项 | 原因 | 替代验证 |
|---|---|---|
| **Docker 镜像构建**（`docker build` / `docker-compose up`） | 本机**无 Docker** | 静态审查 `Dockerfile` / `docker-compose.yml` / `.dockerignore`：`.dockerignore` 已排除 `data`（含 `.api_token`）、`logs`、`.git`、`__pycache__`；`Dockerfile` 单 worker（SQLite 约束）合理。**构建成功性未验证。** |
| **真实浏览器渲染 / 交互**（含横幅、登录跳转、下载） | 本机**无浏览器**，禁用浏览器自动化 | 以**代码级证据**验证渲染分支（`evaluate.html` / `models.html` / `layout.js`）；DOM 结构与容器 id 通过 grep 静态核对。**真实渲染未验证。** |
| **POSIX 文件权限收紧**（`chmod 0o600`） | 验证运行于 **Windows**，无 POSIX 权限位 | 代码已用 `try/except OSError` 包裹（`security.py:74-78`），Windows 下静默忽略、不中断启动；**实际 0600 权限未验证。** |
| 消息队列/多进程并发下的 Token 缓存一致性 | 不在本轮范围 | 未评估 |

---

## 六、总体结论

1. **鉴权边界忠实于架构契约**：`/api/*`、`/v1/*` 受保护，`/console/*`、`/health`、`/docs`/`/redoc`/`/openapi.json` 公开；`Authorization: Bearer` 与 `X-API-Token` 双支持。**逐请求读取开关**已由代码与真实进程双证。
2. **对抗性绕过未能得手**：8 类路径变形 + 7 类头部伪造，无 200 放行；公开面不泄露业务数据或密钥。
3. **「不造假」底线成立**：perplexity 与降级均有独立渲染分支，`available=false` / `backend_is_real_model=false` 如实呈现，无假数字；全站兜底写法扫描仅 1 处 P3 聚合偏差。
4. **共享组件单一来源**：8 页无复制粘贴的顶栏/侧栏/横幅 DOM，容器 id 齐备，`login.html` 按设计例外。
5. **既有测试未被削弱**：53 个既有测试零改动，仅 conftest +1 行；全量 **121 passed，0 skip / 0 xfail**。

**智能路由判定**：**Send To: NoOne（通过）**。
- 无源码 Bug 需返工（P0/P1/P2 = 0）。
- 测试代码无 Bug（新增 46 项自测全绿）。
- 2 项 P3 观察项不阻断交付，建议由主理人决定是否排入后续小迭代；O-1 涉及既有测试契约，改动需 PM/架构确认。

---

### 附：本次 QA 新增交付物
- `tests/test_security_hardening.py` — 46 项独立回归/对抗测试（绕过、头伪造、公开面、下载头注入、错误契约、配置契约）。
- `docs/QA-REPORT.md` — 本报告。
