# 情感二分类端到端案例 · QA 独立验证报告

> 验证人：QA 工程师（独立于交付作者）
> 验证日期：2026-09-13（UTC+8）
> 验证对象：`examples/sentiment_case/`（6 个文件）+ 根 `README.md` 新增「端到端测试案例」一节
> 验证原则：**独立重跑、独立重算，以证伪为目标**；所有数字均来自本次实际执行的命令。

---

## 0. 总体结论

# 结论：PASS with issues（建议修复文档后可放行）

- **平台与案例脚本本身：功能正确，可放行。** EM=0.0、Char-F1=0.0132 经我**独立重算逐位一致**；幂等、降级诚实、指标真算，均属实。
- **但交付的文档（TEST-REPORT.md）存在 2 处不实/夸大声明**（见缺陷 D1、D2），且案例自身的延迟数字与作者报告相差约 20 倍（D3）。这些属于**文档层缺陷**，不改平台代码，但必须回到交付作者修订后才算真正完成——尤其对一个以「绝不造假」为底线的项目，报告里的不实数字本身就是问题。
- 另有 2 项平台侧既有边界缺陷被我发现（D4 label 越界不校验、D5 空文件导入被静默接受），**非本次交付引入**，但会被本案例的使用者踩到，建议登记。

---

## 1. 逐项验证结果表（V1 ~ V6）

| 项 | 内容 | 结论 | 关键证据 |
|---|---|---|---|
| V1 | 数据文件真实性核验 | **PASS** | 30 条全部合法；unlabeled 与 test 逐行完全一致；无重复/无泄漏；4-gram 重复率 0.003 |
| V2 | 独立重跑 5 步闭环 | **PASS（含 1 处延迟偏差，见 D3）** | EM=0.0、Char-F1=0.0132 与报告**逐位一致**；幂等复用正常；延迟比报告高约 20 倍 |
| V3 | 指标计算逻辑交叉验证 | **PASS（指标真；但作者的解释数字有误，见 D2）** | 独立实现重算 macro-F1=0.0132、EM=0.0，与平台一致；单条 F1 实为 0.0147~0.0182，**不是** 0.0317 |
| V4 | 对抗性边界测试 | **PASS with issues（见 D4/D5）** | 畸形 JSON→400、错误 Token→401、不存在 eval→404/400 均正确；**空文件→200、label 越界→200** 不合格 |
| V5 | 全量回归 + 未污染核验 | **PASS** | pytest 121 passed（0 skip/xfail）、frontend 13/13、smoke 15/15；`data/_demo/` 未被触碰 |
| V6 | 文档真实性审查 | **FAIL（见 D1、D2）** | 数据来源链接真实存在；但 TEST-REPORT §5 的「完整 results」含一个平台根本没返回的 perplexity 块；§6.7 的 0.0317 无法复现 |

---

## 2. 缺陷清单（按严重级别排序）

> 说明：本清单中 **D1/D2/D3 属于本次交付物（文档）**；**D4/D5 属于平台既有边界行为**，非本次引入，但为完整起见一并登记。

| 级别 | 位置 | 一句话描述 |
|---|---|---|
| **P1** | `TEST-REPORT.md` §5（第 98~121 行） | 「实测返回的完整 results」中**包含一个平台实际从未返回的 `perplexity` 块**，且称 `requested_metrics=[...,"perplexity"]`——而 `run_case.py` 的 `CASE_METRICS` 根本不含 perplexity。属**伪造原始输出**。 |
| **P2** | `TEST-REPORT.md` §6.7（第 344~354 行） | 声称单条 `char_f1≈0.0317`、宏平均 0.0132。**独立重算单条实为 0.0147~0.0182**，且有 2 条为 0.0；0.0317 对应的归一化长度 ≈62，与实际 mock 输出长度（109~135）不符。解释机理方向对，数字不对。 |
| **P2** | 案例延迟数字 `TEST-REPORT.md` §三 + `run_case.py` 输出 | 作者报 1.667/2.289/1.788/3.675/3.675 ms；我在同一脚本、同一 `/v1/completions` 路径上两次实测为 **39.8~43.7ms**（约 20 倍）。延迟虽环境相关，但 20 倍已超出「±50% 合理浮动」，报告未声明该波动范围。 |
| **P2** | 平台 `POST /api/data/import` + `data_service.import_data_from_file` | **空文件 / 仅空行文件被静默接受（HTTP 200, total_samples=0）**，应返回 400。会生成 0 样本的空数据集，后续评测才报错，错误暴露过晚。 |
| **P2** | 平台 `POST /api/data/import` | **label 无域校验**：`label=5`、`label=-1`、`label="abc"` 全部 200 接受。本案例的评测走 `output` 字符串不受影响，但会误导使用者「平台校验了标签」。 |
| **P3** | `run_case.py` STEP1 语义 | 导入 `{"text","label"}` 时，`data_service` 只识别 `instruction/input/output` 等字段，**`text` 被丢弃、`label` 未映射为 output**。故「导入 train.jsonl」实际入库的是 20 条**空文本、无答案**记录（这也解释了报告里 `pending=20`）。评测之所以正确，是因为脚本用独立请求体 `test_data` 传入，绕过了数据集。README/测试报告未说明这一「导入内容其实为空」的事实。 |
| **P3** | 平台 `POST /api/evaluate/create` | `model_id=888888`（不存在）仍返回 200 并创建评测，无外键校验。既有行为，非本次引入。 |
| **P3** | 平台 `POST /api/evaluate/{id}/run`（不存在 id） | 返回 **400**（`Evaluation N not found`）而非 404；同资源的 GET `/{id}/result` 返回 404。**同一资源两种状态码**，语义不一致（但均非 500，未触发 5xx）。 |

### 缺陷复现步骤与证据

**D1（P1，伪造 results 块）**
1. 读 `TEST-REPORT.md` §5：展示 `results` 含 `perplexity:{available:false,reason:"未安装 torch / transformers",how_to_enable:...}`，并称 `requested_metrics=["exact_match","token_f1","latency","perplexity"]`。
2. 读 `run_case.py` 第 65 行：`CASE_METRICS = ["exact_match", "token_f1", "latency"]`（**无 perplexity**）。
3. 实跑后查询 `GET /api/evaluate/1/result`，原始返回：
   - `metrics = {"requested": ["exact_match","token_f1","latency"]}`
   - `results` 顶层键 = `[sample_count, backend, backend_is_real_model, metric_definitions, exact_match, token_f1, latency]`（**无 perplexity**）
   - `results.perplexity = null`
4. 脚本汇总表实际打印：`Perplexity : 未请求 / 无数据`。
> 结论：报告 §5 展示的 perplexity 块**不是本次运行的返回**，是被拼接进去的。虽然 `metric_definitions` 里确实有 perplexity 说明（这部分真实），但把它写成「results 的实测内容」属不实陈述。

**D2（P2，0.0317 不可复现）**
- 用平台自身 `char_f1` + `MockBackend` 复算（见 `_qa_out` 中 V3b 记录）：
  - 实际评测 mock 预测（`build_prompt` 口径）单条 `char_f1`：`0.018182, 0.016000, 0.016807, 0.014706, 0.016393, 0.000000, 0.015873, 0.018182, 0.000000, 0.015625`
  - 宏平均 = `0.0132` ✅（与报告一致）
  - 单条非零值区间 = `[0.0147, 0.0182]`，**无一条为 0.0317**
  - 报告 §6.7 引用的自造短串（len=50）算出 `0.0392`，亦非 0.0317。要得到 0.031746 需归一化长度≈62。
> 结论：**F1 指标本身是真算的**（我已证实），但 §6.7 用来「自证真实」的那个 0.0317 是错的，逻辑链不能自洽（8×0.0317/10=0.0254≠0.0132）。

**D3（P2，延迟 20×偏差）**
- 同一脚本两次运行：
  - run#1：min 39.8 / avg 41.555 / p50 41.009 / p95 43.663 / max 43.663 ms
  - run#2：min 21.833 / avg 39.302 / p50 40.594 / p95 43.614 / max 43.614 ms
- 作者报告：min 1.667 / avg 2.289 / p50 1.788 / p95 3.675 / max 3.675 ms
- 旁证：`smoke_test.py` 走 `/v1/chat/completions` 实测 `avg_ms=2.269`（接近报告值）。差异主因应是 **`/v1/completions` 的 run_case 长中文 prompt 触发的推理日志写库（`prompt[:1000]` 落 SQLite）** 与磁盘差异，属**环境/路径相关**，非指标造假。
> 结论：EM / Char-F1 我复现逐位一致；延迟因环境不同而显著偏离，**报告未声明这一波动**，读者会误以为延迟稳定在 2ms 量级。

**D4 / D5（P2，平台边界）** 复现见 §3.V4 原始输出。

---

## 3. 逐项验证详录

### V1 数据文件真实性核验 —— PASS

- 脚本：`examples/sentiment_case/verify_data.py`（我编写，已留作可复现资产）。
- 运行：`python examples/sentiment_case/verify_data.py` → 退出码 0。
- 原始输出节选：

```
[PASS] train.jsonl: UTF-8 无 BOM / [INFO] 20 条
[PASS] test.jsonl: UTF-8 无 BOM / [INFO] 10 条
[PASS] test_without_label.jsonl: UTF-8 无 BOM / [INFO] 10 条
[PASS] train 共 20 条 ; test 共 10 条 ; unlabeled 共 10 条
[PASS] train: 好评(1)=10 差评(0)=10 ; test: 好评(1)=5 差评(0)=5
[PASS] unlabeled 与 test 逐行文本完全一致（顺序也一致）
[PASS] train/test/unlabeled：文件内无重复文本；train 与 test 无交叉泄漏
train: min=18 max=55 avg=34.8 ; test: min=20 max=47 avg=34.1
[PASS] 最短文本 18 字 >= 8 ; 平均长度 34.6 字 >= 20
4-gram 总数=947, 重复覆盖=3, 占比=0.003  [PASS < 0.15]
```

结论：数据文件真实、规范、无泄漏，**unlabeled↔test 逐行一致**（推理→评测可对齐）。

### V2 独立重跑 5 步闭环 —— PASS（延迟偏差见 D3）

- 用全新临时数据目录（`_qa_case_db`）+ 端口 8077，环境变量 `UNILLM_DATABASE__PATH` / `UNILLM_APP__API_TOKEN_FILE` / `UNILLM_STORAGE__*` 全部指向临时目录，**未污染 `data/` 与 `data/_demo/`**。
- run#1 原始汇总（`/health` 返回 `degraded=true`，脚本打印了 mock 警示）：

```
样本数 (sample_count) : 10
Exact Match        : 0.0  (0/10)
Char-F1 (token_f1) : 0.0132  (unit=char)
延迟 min/avg/p50/p95/max : 39.8 / 41.555 / 41.009 / 43.663 / 43.663 ms
Perplexity         : 未请求 / 无数据
```

- 与作者报告对比：**EM 逐位一致（0.0 / 0-10）**、**Char-F1 逐位一致（0.0132）**；延迟显著不同（D3）。
- 确定性旁证：第 1 条预测 `prompt_sha1=d378811577f7` 与作者报告 §6.1 **完全相同**。
- **幂等验证**（立即复跑 run#2）：正确打印全部「已存在 → 复用」（train/test 数据集、标注任务、模型），指标不变，未报错：

```
· 数据集 'sentiment-case-train' 已存在 → 复用 (id=1, total_samples=20)
· 数据集 'sentiment-case-test'  已存在 → 复用 (id=2, total_samples=10)
· 任务 'sentiment-case-annotation' 已存在 → 复用 (id=1, total_items=20)
· 模型 'sentiment-case-mock' 已注册 → 复用 (id=1)
```

### V3 指标计算逻辑交叉验证 —— PASS（指标真，作者解释数字有误）

- 方法：导入平台 `MockBackend` 生成与评测完全相同的预测（prompt 按 `EvaluateService.build_prompt`），再用**我独立实现**的归一化+字符级 F1 重算。
- 结果：

| 指标 | 平台返回 | 我独立重算 | 是否一致 |
|---|---|---|---|
| Exact Match | 0.0 (0/10) | 0.0 (0/10) | ✅ 逐位一致 |
| Char-F1 (macro) | 0.0132 | 0.0132 | ✅ 逐位一致（4 位小数） |

- 逐样本明细（真实 mock 预测，归一化后长度 109~135）：

```
#1 ref=1 f1=0.018182   #2 ref=1 f1=0.016000   #3 ref=1 f1=0.016807
#4 ref=1 f1=0.014706   #5 ref=1 f1=0.016393   #6 ref=0 f1=0.000000
#7 ref=0 f1=0.015873   #8 ref=0 f1=0.018182   #9 ref=0 f1=0.000000
#10 ref=0 f1=0.015625
```

- **机理证实**：mock 输出含 `prompt_sha1=<hex>`，归一化后十六进制数字中偶含 `0`/`1` 字符，与标签 `"0"`/`"1"` 产生 overlap；`#6`、`#9` 恰好不含对应字符 → F1=0，故宏平均被拉低到 0.0132。
- **推翻**作者的「单条≈0.0317」：实测单条 0.0147~0.0182（D2）。
- 我另用平台自身 `char_f1` 复算，结果与我的独立实现**逐条相同**，证明比对方法未引入偏差。
- **判定：Char-F1=0.0132 是真实计算结果，不是凑出来的巧合数字**（其「真实但细碎」的特征可被独立复现）。但作者用于自证的中间数字有误。

### V4 对抗性边界测试 —— PASS with issues

对运行中的实例发起的请求（HTTP 层原始结果）：

| 用例 | 请求 | 实际响应 | 判定 |
|---|---|---|---|
| 0 字节文件导入 | `POST /api/data/import` | **200**, `total_samples=0` | ❌ 期望 400（D5） |
| 仅空行文件导入 | 同上 | **200**, `total_samples=0` | ❌ 期望 400（D5） |
| 畸形 JSON 行 | 同上 | **400** `{"detail":"数据导入失败: ...","error_code":"BAD_REQUEST","hint":null}` | ✅ |
| 10000 字超长文本 | 同上 | **200**, 未崩溃 | ✅（无长度上限，但未崩） |
| `label=5` / `-1` / `"abc"` | 同上 | **200** 全部接受 | ❌ 期望拒绝（D4） |
| 错误 Token | `GET /api/data/list` | **401** `{"detail":"访问令牌无效","error_code":"UNAUTHORIZED","hint":"..."}` | ✅ |
| 无 Token | `GET /api/data/list` | **401** `{"detail":"未提供访问令牌","error_code":"UNAUTHORIZED",...}` | ✅ |
| 公开 `/health` | 无 Token | **200** | ✅ |
| 不存在 eval 运行 | `POST /api/evaluate/999999/run` | **400** `Evaluation 999999 not found` | ⚠️ 非 500，但语义应为 404（D7/P3） |
| 不存在 eval 结果 | `GET /api/evaluate/999999/result` | **404** `error_code:NOT_FOUND` | ✅ |
| 不存在 model 建评测 | `POST /api/evaluate/create` | **200** 创建成功 | ⚠️ 无外键校验（P3） |

- **无任何 5xx**。
- 错误 Token 的 `[UNAUTHORIZED]` 前缀：`run_case.py:132-134` 会把 `error_code` 渲染为 `[UNAUTHORIZED] 访问令牌无效`；API 返回的契约字段与此完全匹配，**格式正确**（脚本格式化逻辑经代码审阅确认，且 API 契约已实测）。

### V5 全量回归 + 未污染核验 —— PASS

| 检查 | 命令 | 结果 |
|---|---|---|
| pytest | `python -m pytest tests -rs -q` | **121 passed**；`--collect-only` = `121 tests collected`，**无 skip/xfail** |
| 前端逻辑 | `node scripts/frontend_logic_check.js` | **13/13 passed** |
| 真进程冒烟 | `python scripts/smoke_test.py --port 8091` | **15/15 项通过** |
| `data/_demo/` 未被触碰 | 文件 mtime | 全部为 `20:57~20:58`；本案例产物为 `21:32~21:38`，**未被触碰** ✅ |

- pytest 尾部的 `SystemExit: 1` 是**沙箱 safe-delete 守护在 pytest atexit 清理临时目录时抛出**，与测试结果无关（121 passed 已在上方打印）——与作者报告 §6.3 的描述一致，**属实**。
- smoke 附录里的 `[PASS] 评测结果为真实计算值（非硬编码 0.72） -- exact_match=0.0` 我原样复现（15/15 内容逐条一致）。
- **git 归属说明**：本仓库工作树是**全项目共享的未提交状态**（仅 2 个 commit），`git status` 显示 `app/`、`tests/`、`config.yaml` 等大量 `M`，`examples/` 为 `??`（未跟踪）。因此 **git 无法把改动归因到单一成员**。经 mtime 比对（`data/_demo/` 早于本案例产物），可确认**本案例交付未触碰 `data/_demo/`**；其余 `app/` 改动属本项目其他任务的既有成果，非本案例作者所为。**无法用 git 单独证明「只改了 README+examples」**，如实记录。

### V6 文档真实性审查 —— FAIL（D1、D2）

- **数据来源链接真实性：✅ 真实存在。** `WebFetch https://github.com/SophonPlus/ChineseNlpCorpus` 返回真实仓库，简介为「搜集、整理、发布中文 NLP 语料/数据集」，且**确实收录 `ChnSentiCorp_htl_all`（7000+ 酒店评论）**。README 关于「参照 ChnSentiCorp 格式自造、非官方分发」的声明**诚实准确**，`test_without_label.jsonl`「仅去掉 label 字段」的描述也与 V1 结果一致。
- **README.md（案例目录）：整体诚实、无过度声明。** mock 低准确率的读法、幂等、错误输出说明均与实测一致。
- **TEST-REPORT.md：存在 2 处不实/夸大（D1 伪造 perplexity 结果块、D2 用错的 0.0317 自证）。** 其余（环境、5 步响应、`is_loaded=false`、降级三处一致）经复核**属实**。
- **结论措辞越界检查**：§五「平台链路可用」有充分证据支撑，未越界；「绝不造假」的结语在**平台代码层面成立**（我确认平台侧无硬编码指标），但**报告自身的一处原始输出不实**，与该结语形成讽刺性反差。
- **复现命令可跑通性：✅** `python -m uvicorn app.main:app ...` + `python examples/sentiment_case/run_case.py` 的组合我用等价方式（同脚本、真实 uvicorn 进程）实际跑通，脚本退出码 0，5 步全通。

---

## 4. 独立重算指标 vs 作者报告 —— 对比表

| 指标 | 作者报告 | QA 独立重跑/重算 | 是否一致 |
|---|---|---|---|
| 样本数 | 10 | 10 | ✅ |
| Exact Match | 0.0 (0/10) | **0.0 (0/10)** | ✅ 逐位一致 |
| Char-F1 (token_f1) | 0.0132 | **0.0132** | ✅ 逐位一致 |
| 延迟 min (ms) | 1.667 | 39.8（run#1）/ 21.833（run#2） | ❌ 约 20×（D3） |
| 延迟 avg (ms) | 2.289 | 41.555 / 39.302 | ❌ |
| 延迟 p50 (ms) | 1.788 | 41.009 / 40.594 | ❌ |
| 延迟 p95 (ms) | 3.675 | 43.663 / 43.614 | ❌ |
| 延迟 max (ms) | 3.675 | 43.663 / 43.614 | ❌ |
| Perplexity | 不可用(available:false) | **本次未请求**（脚本无此指标） | ❌ 报告失真（D1） |
| 单条 char_f1 | ≈0.0317 | 0.0147~0.0182（含 2 条 0.0） | ❌（D2） |
| pytest | 121 passed | 121 passed，无 skip/xfail | ✅ |
| frontend | 13/13 | 13/13 | ✅ |
| smoke | 15/15 | 15/15 | ✅ |
| 第 1 条 prompt_sha1 | d378811577f7 | d378811577f7 | ✅ 确定性一致 |

---

## 5. `verify_data.py` 说明

- 路径：`examples/sentiment_case/verify_data.py`（本次新增，留作可复现 QA 资产）。
- 作用：对三个 JSONL 做机器化校验（编码/BOM、合法 JSON、字段集合、label∈{0,1}、条数与正负分布、unlabeled↔test 逐行一致、重复与交叉泄漏、长度分布、4-gram 模板句粗检）。
- 用法：`python examples/sentiment_case/verify_data.py`；退出码 0=通过，1=存在失败项。
- 依赖：仅标准库，零第三方依赖。

---

## 6. 未能验证项（诚实声明）

1. **真实模型（vLLM 后端）效果**：本机无 GPU、未装 vLLM，`backend=vllm` 路径无法触及；高准确率、真实延迟、`backend_is_real_model=true` 的形态**未验证**。
2. **Perplexity 指标计算**：未装 torch/transformers，未验证其数值路径；且本案例脚本压根未请求该指标。
3. **前端页面浏览器渲染**：无浏览器环境，仅验证了 `scripts/frontend_logic_check.js` 的逻辑层 13/13；`/console/*` 的实际渲染与交互**未验证**。
4. **微调链路** `/api/finetune/*`：本案例不涉及，**未验证**。
5. **并发/多实例压测**：仅单进程串行，**未验证**并发行为。
6. **git 级改动归属**：仓库为共享未提交工作树，**无法**用 git 单独证明本案例作者「只改了 README+examples」；仅能以 mtime 证明未触碰 `data/_demo/`。
7. **测试环境差异**：延迟数字受本机磁盘/负载影响显著，我给出的 20× 偏差是**本机实测**，不代表作者机器上的数值必然错误；但我未能在本机复现出作者报告的毫秒级延迟。

---

## 7. 放行建议

| 交付物 | 建议 |
|---|---|
| 平台代码 / `run_case.py` / 数据文件 | **可放行**（功能正确，指标真算） |
| `examples/sentiment_case/README.md` | **可放行**（诚实准确） |
| `examples/sentiment_case/TEST-REPORT.md` | **需修订后放行**：删除/更正伪造的 perplexity results 块（D1）、更正 0.0317 的解释（D2）、补注延迟的环境波动范围（D3） |
| 平台边界缺陷 D4/D5（label 越界、空文件） | **建议登记为后续改进项**，非本次阻断 |

**一句话**：平台和案例本身**真材实料、绝不造假的底线守住了**；但**这份「绝不造假」报告自己在两处不实**，需先改正再交付——否则会重演它试图杜绝的问题。
