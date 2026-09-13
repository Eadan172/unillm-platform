# QA-VERIFY-4 —— 标量契约修复（第四轮）独立复验报告

| 项 | 内容 |
|---|---|
| 验证对象 | 工作区**未提交改动**：`app/core/values.py`、`app/services/data_service.py`、`app/services/evaluate_service.py`、`tests/test_scalar_contract.py`（新增）、`tests/test_input_validation.py`、`tests/test_evaluation_references.py`、`README.md`、`docs/QA-REPORT.md` |
| 对照基线 | `git HEAD = ce9042dec55914bef6c8701e1d13b93362d1c6ae`（**已核实恰为「第三轮修复后」状态**，见 §零.1） |
| 验证者 | `software-qa-engineer-4`（独立 QA，未参与实现） |
| 验证时间 | 2026-09-13 22:58 – 23:10 |
| 运行环境 | Windows 11；解释器 `D:/WorkBuddy/.workbuddy/binaries/python/envs/unillm/Scripts/python.exe`（Python 3.13.14）；in-process `starlette.testclient.TestClient`；每个探针使用独立临时 SQLite 与独立存储目录（复刻 `tests/conftest.py` 的隔离顺序：**先改 `settings.*_path` 再 import `app.main`**） |
| 立场 | 证伪优先。凡是「改动生效」都必须给出可对照的原始输出；凡是「既有 / 本次引入」都必须用实测区分，不用代码推导冒充实测 |

> **修订记录 v2（2026-09-13 23:12，经实现方复核后）**
>
> 1. **P3-1 的成因表述按机制更正**：原报告写的是「prompt 丢掉 alias 内容」，方向正确但机制不够准。实现方指出（并提供代码级成因）：`build_prompt` 的 `if instruction is None:` 回退分支**并未被删除**，只是在本轮调用路径上**不可达** —— 值在上游被 `require_scalar` → `coerce_scalar(None)` 收敛成 `""`，且送进 `build_prompt` 的 dict 键名是 `instruction`、**不含 `question`**。我用运行时探针独立核实了这一主张（新增 §2.7 与 `.qa4/r4_p3mech.py`），确认「不是回退逻辑被删，而是触发条件在上游被消掉」。
> 2. **P2-1 的定性经实现方确认无误**：实现方认账「是第四轮引入的真回归，不是误报」，并给出同源推导（`values.py:74-75` 只在键缺失时回退 → `evaluate_service.py:227-228` 的 `has_visible_content(None)` 为假 → `continue` → 单条时被 `:249` 转成 400），与我的 A/B 数字一致。**定性不变（P2）**。
> 3. **新增取证来源说明**：实现方的 Bash 会话已不可用（自述 `exit 127`），因此**本报告中的 V6 逐字比对与 P2 回归的 A/B 实测数据，全部由我来提供**；实现方提供的是代码级成因，双方不主张对方的独立复现。已在 §零.1 补记。
> 4. 其余结论、数字、缺陷等级均未变化；P3-2 / P3-3 / P3-4 / P3-5 与「须登记的行为变化」保持不变。修复方案（`resolve_field(..., fallback_when_none=True)` 只用于评测侧）由实现方与我都赞同，裁定在任务 #22，本报告不预判。

> **修订记录 v3（2026-09-13 23:2x，验证对象发生第二次变更后）**
>
> 5. **重要：本次复验的验证对象（工作区）在我取证之后被再次改动**。文件 mtime 为 `values.py` 23:11:32、`evaluate_service.py` 23:11:42、`test_scalar_contract.py` 23:12:21，**晚于**我 23:08 的 md5 取证快照；落点正是 P2-1 / P3-1 的修法。因此**本报告 v1/v2 中所有「当前工作区」的结论与数字，其有效对象是「第四轮修复后、追加修复前」的那棵树**，不能直接读作对现行树的描述。这一点不加修饰地写明，避免后读者拿旧结论去核新代码。
> 6. 我在**新树**上重跑了整条证据链：全量测试 **217 passed**（`tests/test_scalar_contract.py` 由 44 增至 50，+6 条针对该回归的新测试）、主对抗矩阵 V2–V5 **178/178**、按实现方给出的 6 条验收契约 **25/25**。结论：**P2-1 与 P3-1 已被修掉**，P3-4 / P3-5 也一并被处理。详见新增 **§十一**。
> 7. 仍未修的是 **P3-2**（`raw_data` / 归档 JSON 可含非法 JSON）与 **P3-3**（数值参考值 `str()` 口径），两条都在新树上重测确认仍在，与我原先「可延后、需登记」的建议一致。
> 8. 前文若干引用对**新树**已过期（源码行号、md5、V1 计数、§3.2 的 NaN 文案引文）。逐条列在 **§11.4**，**未就地覆盖旧值**，以便读者对照两个快照。
> 9. **改动归属已核实**：这轮改动由 **team-lead 执行并自证**（**不是** software-engineer-3 —— 其 Bash 会话不可用、全程只读未写入）。因此本次追加复验的实质是「**QA 第三方独立复验改动者本人落地的改动**」。同时把一次**行号争议**的核对结论也写进 §11.4：以 `git diff` hunk 还原的旧快照行号为准，并记下「行号不能当锚点」这条教训。

---

## 结论（先给结论）

| 项 | 复验内容 | 判定 |
|---|---|---|
| **V1** | 全量测试权威计数 | ✅ **PASS** —— `211`（167 + 44），三条独立口径一致，`collected == passed`。⚠️ **验证对象此后发生第二次变更：现行树为 `217`（+6 条针对回归的新测试），见 §十一** |
| **V2** | 评测侧非标量参考答案必须 400 | ✅ 声明生效（第三轮 P2-A 已修，A/B 实测确认）／❌ 同时引入 1 条 P2 回归（P2-1）——**该回归在新树上已修掉，见 §十一** |
| **V3** | NaN / Infinity → 400 | ✅ 声明生效（第三轮 P2-B 已修；**并在 HEAD 侧实测复现了 `completed + NULL` 矛盾行**）／⚠️ 残留 1 条 P3（`raw_data` 仍可写入 `NaN`） |
| **V4** | `test_data=[]` 不得回退 | ✅ 声明生效（A/B 实测 HEAD 确实静默回退到数据集） |
| **V5** | `.json` 顶层类型要说真话 | ✅ 声明生效，**并额外修掉 2 条更糟的原始 Python 报错** |
| **V6** | 薄委托、既有错误文案一字未变 | ✅ **PASS** —— 21/21 逐字相同（脚本按字节比对），源码 diff 亦证实 |

**总判定：PASS with issues（针对第四轮修复后、追加修复前的那棵树）。**

> ⚠️ **验证对象在报告完成期间发生过第二次变更**（做法与原因见修订记录 v3 与 §十一）。对**现行树**的判定是：V1–V6 全部达成，`217 passed`、主对抗矩阵 `178/178`、6 条验收契约 `25/25`，P2-1 / P3-1 / P3-4 / P3-5 均已修掉；仅剩 P3-2（`raw_data` 非法 JSON）与 P3-3（`str()` 口径）两条非阻断项。

- 无 P0/P1 阻断项。engineer-3 自报的 6 项改动**全部经实测确认生效**，未发现虚报。
- 发现 **1 条 P2**（本轮**新引入**的「静默缩小测试集」回归）、**1 条 P3 回归**（同源：prompt 丢失别名内容）、**4 条 P3**（2 条既有：`raw_data` 非法 JSON、数值参考值 `str()` 口径；2 条文档：README 行号、QA-REPORT 轮次编号）、**1 条须登记的行为变化**（合计 P3-1 ~ P3-5 五条，逐条见下方缺陷一览）。
- 残余 P2 的性质与本项目底线直接冲突（「不报错、数字合理、结论错误」），**建议在交付前修掉**，代价约 3 行。

### 缺陷一览

| 编号 | 级别 | 位置 | 一句话 | 性质 |
|---|---|---|---|---|
| P2-1 | **P2** | `app/services/evaluate_service.py:221-236` + `app/core/values.py:67-78` | `{"output": null, "answer": "x"}` 的样本被**静默丢弃**（第三轮会计入） | **本次改动引入（回归）** |
| P3-1 | P3 | `app/services/evaluate_service.py:242-244`（成因在 `:221-223` 的上游收敛，见 §2.7） | `{"instruction": null, "question": "q"}` 的 prompt 丢掉 `q`（第三轮会用 `q`）。机制：**不是回退分支被删，而是它在调用路径上不可达**（值已被收敛成 `""`，且 dict 里没有 `question` 键） | **本次改动引入（回归，与 P2-1 同源）** |
| P3-2 | P3 | `app/services/data_service.py:172-178`（`raw_data=item`）、`:213`（`json.dump`） | `raw_data` JSON 列与落盘 `dataset_N.json` 仍可写入非法 JSON `NaN`/`Infinity` | 既有（HEAD 同形），本轮未修 |
| P3-3 | P3 | `app/services/evaluate_service.py:245`（`str(reference)`） | 数值参考值按 Python `str()` 口径字符串化：`0.0`→`"0.0"`、`-0.0`→`"-0.0"`，经标点归一化后变 `"00"`，与预测 `"0"` 不匹配 | 既有，口径问题（0 本身已正确计数） |
| P3-4 | P3 | `README.md:386` | 引用 `evaluate_service.py:248`，实际截断在 `:255`（`sample_count` 的 `:136` 正确） | 文档行号过期 |
| P3-5 | P3 | `docs/QA-REPORT.md:8-21` | 后补导航表把 `QA-VERIFY-3.md` 记为「第四轮」、`QA-VERIFY-4.md` 记为「第五轮」，而团队任务口径分别称其为「第三轮 / 第四轮复验」；两种编号口径并存但未注明计数基准 | 文档编号口径含糊 |
| — | 登记 | `app/services/evaluate_service.py:229-236` | 「instruction/input 非标量 + 参考答案为空」由「跳过该样本」变为「整体 400」 | 行为变化，**非缺陷**（报错更早更准确） |

---

## 零、取证方式（先说清方法，避免"为了漂亮数字而掩盖取证方式"）

### 零.1 基线为什么是真基线

`git log` 只有 3 个提交，`HEAD` 是 `ce9042d feat: 0.3.0 成熟 MVP`；三处源码在工作区处于 `M`（modified）状态。我逐一核实 **HEAD 就是「第三轮修复后、第四轮修复前」的状态**：

```
$ git show HEAD:app/core/values.py | grep -c "def require_scalar"      -> 0
$ git show HEAD:app/services/evaluate_service.py | grep -c require_scalar -> 0
$ git show HEAD:app/services/data_service.py | grep -c "值类型不受支持"   -> 1
$ git show HEAD:app/services/data_service.py | sed -n '77,96p'         -> 第三轮的 _require_scalar（含既有文案，无 NaN 分支）
```

即：HEAD 的 `values.py` 只有 `has_visible_content` / `is_missing`（无 `resolve_field`/`coerce_scalar`/`require_scalar`）；HEAD 的 `evaluate_service.py` 完全没有 `require_scalar`；HEAD 的 `data_service.py` 自带 `_require_scalar` 与那句既有文案。

因此我把 HEAD 完整导出成**可运行的第三轮代码树**，用**同一支探针**分别跑两棵树做真 A/B（不是代码推导）：

```
$ git archive HEAD | tar -x -C <workspace>/_qa4_headsrc
$ python .qa4/r4_ab.py <workspace>/_qa4_headsrc   HEAD-round3      > .qa4/ab_head.txt
$ python .qa4/r4_ab.py <repo>                     WORKTREE-round4  > .qa4/ab_cur.txt
```

两棵树各自创建独立临时数据库（`TMP=...\Temp\qa4ab-xxxx`），互不干扰。**下面所有「本次引入 / 既有」的定性都出自这份 A/B，而不是读代码猜的。**

> **取证来源的边界（修订 v2 补记）**：实现方的 Bash 会话已不可用（其自述已 `exit 127`，无法运行双树 A/B）。因此**本报告里 V6 的逐字比对结果与 P2 回归的 A/B 实测数据，均由我这一侧产出且可复现**（原始输出见 `.qa4/ab_head.txt`、`.qa4/ab_cur.txt`、`.qa4/v6_cmp.txt`）；实现方提供的是**代码级成因**（`values.py:74-75` → `evaluate_service.py:227-228` → `:249`）与修法，双方均**不主张**对方做过独立复现。这一分工在下面的缺陷表与 §2.7 里逐条标明。

### 零.2 V1 的计数是怎么得到的（明说）

**单进程、一次性跑完整测试套件**，并让 pytest 把结果写到 junit XML（junit 在 `pytest_sessionfinish` 落盘，即使进程随后被沙箱的清理守卫杀掉也已经写完）：

```
$ TMPD="$(mktemp -d -p /tmp qa4v1f-XXXXXX)"
$ TMP="$TMPD" TEMP="$TMPD" TMPDIR="$TMPD" \
  python -m pytest --junitxml=.qa4/junit_r4.xml -o addopts="" -p no:cacheprovider
```

本轮**没有被沙箱阻塞**（team-lead 那侧被 `SAFE_DELETE_BULK_REJECTED` 守卫打断，我这边一次跑完）。命令行尾部摘要与 junit 属性、以及独立 `--collect-only` 三者一致 —— **我没有按文件分批凑数，也没有用任何方式"凑 211"**；如果这三者不一致，下面的判定就会是不一致。

### 零.3 中间产物与可见性

`.qa4/` 被 `.gitignore:155` 的 `.qa*/` 规则忽略（`git check-ignore -v .qa4` → `.gitignore:155:.qa*/  .qa4`），因此**关键原始输出已抄进本报告正文**（附录 A / 各节引用块），不只躺在 `.qa4/` 里。

本轮 md5（供交叉核对，采集于 2026-09-13 23:08）：

```
2b248d2719c329b5bcedfd48c865dc96  app/core/values.py
37723aeadd2891aff0d9a588bd5fc974  app/services/data_service.py
a5264ad46ded3f8a9878a40ad312fac8  app/services/evaluate_service.py
7d9a96528984680cb92156d5ae48f13b  tests/test_scalar_contract.py
b615c20054320ae3e040102dc4cfaffc  tests/test_input_validation.py
697f2339e8869738de454d78d578a625  tests/test_evaluation_references.py
537a274ab29a41d2faa8dc0cc49c85fb  README.md
944dcf3ccafa2ba5daafcb62edd005ce  .qa4/junit_r4.xml
10c53dee8a981e72e69b7cf532586b38  .qa4/ab_head.txt
0365b06537d8ad3cf82a5a14a429b93e  .qa4/ab_cur.txt
54e38ef1b6c1110355b1470327395dd6  .qa4/v2v5.txt
a8e837c6f368f20f9a357acd7033879b  .qa4/head_data_service.py（HEAD 基线）
```

---

## 一、V1：全量测试权威计数

### 1.1 命令行与原始输出

```
$ python -m pytest --junitxml=.qa4/junit_r4.xml -o addopts="" -p no:cacheprovider
tests\test_auth.py .............                                          [  6%]
tests\test_closed_loop.py .....................                           [ 16%]
tests\test_errors.py .........                                            [ 20%]
tests\test_evaluation_references.py ...........                           [ 25%]
tests\test_input_validation.py ...................................        [ 42%]
tests\test_metrics.py ............                                        [ 47%]
tests\test_scalar_contract.py ..........................................  [ 67%]
..                                                                        [ 68%]
tests\test_security_hardening.py .......................................   [ 87%]
.......                                                                   [ 90%]
tests\test_upload_safety.py ....................                          [100%]

====================== 211 passed, 2 warnings in 22.16s =======================
FULL_EXIT=0
```

junit XML（`<testsuites>` 内唯一 `<testsuite>` 的属性，原样）：

```
<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="211"
           time="22.150" timestamp="2026-09-13T23:00:17.433008+08:00" hostname="media">
```

### 1.2 三条独立口径互相印证

| 口径 | 结果 |
|---|---|
| pytest 终端摘要 | `211 passed`，退出码 `0` |
| junit `tests="211" failures="0" errors="0" skipped="0"` | `211` |
| junit 内 `<testcase>` 元素个数（脚本 `ElementTree` 计数，另用正则 `re.findall(r"<testcase\s")` 复核） | `211`（与属性一致 → `True`） |
| 独立 `--collect-only -q`（另一个 TMP 目录） | `211 tests collected`，`COLLECT_EXIT=0` |

**`collected == passed == 211`，无 skip / xfail / error。**

### 1.3 按文件分布（collected 与 junit 两个来源完全一致）

| 文件 | 数量 |
|---|---|
| `tests/test_security_hardening.py` | 46 |
| `tests/test_scalar_contract.py` | **44** |
| `tests/test_input_validation.py` | 35 |
| `tests/test_closed_loop.py` | 21 |
| `tests/test_upload_safety.py` | 20 |
| `tests/test_auth.py` | 13 |
| `tests/test_metrics.py` | 12 |
| `tests/test_evaluation_references.py` | 11 |
| `tests/test_errors.py` | 9 |
| **合计** | **211** |

### 1.4 对「167 + 44 = 211」的独立佐证

对**第三轮代码树副本**（`_qa4_headsrc`，见 §零.1）跑同样的采集：

```
$ python -m pytest --collect-only -q -o addopts="" -p no:cacheprovider
167 tests collected in 0.37s
     13 tests/test_auth.py        21 tests/test_closed_loop.py
      9 tests/test_errors.py      11 tests/test_evaluation_references.py
     35 tests/test_input_validation.py   12 tests/test_metrics.py
     46 tests/test_security_hardening.py  20 tests/test_upload_safety.py
```

第三轮副本 = **167** 条且**不含** `test_scalar_contract.py`；本轮 = 167 + 44 = **211**。

> 判定：**PASS**。计数方法与结果如上，未做任何形式的凑数。

---

## 二、V2：评测侧非标量参考答案必须 400（且零副作用）

### 2.1 先确认缺陷真实存在（A/B 实测，而非代码推导）

同一支探针在两棵树上的原始输出：

```
--- HEAD（第三轮）---
  [eval output=[1,2]] status=200 status_field='completed' sample_count=1
                      exact_match={"value": 0.0, "correct": 0, "total": 1}

--- 当前工作区（第四轮）---
  [eval output=[1,2]] status=400
    detail="字段 'output' 的值类型不受支持：内容字段只能是标量（字符串 / 数字 / 布尔 / 空值），
            实际为 list。请将该字段改为字符串后再导入（例如把列表拼接为一段文本，
            或改用多条记录表达）。"
```

**第三轮 P2-A（返回 200、把 Python repr 拿去算指标）是实测复现的，不是推导**；本轮已改为 400 且文案点名字段与类型。

### 2.2 16 种非标量变体（HTTP 实测）

命令：`python .qa4/r4_v2v5.py`（§V2-a）。全部 400，`detail` 均含 `字段 'X'` 与 `实际为 <type>`，副作用快照前后一致。

| 用例 | test_data | 实测 | 文案点名字段 | 文案点名类型 | 零副作用 |
|---|---|---|---|---|---|
| output_list | `{"instruction":"x","output":[1,2]}` | 400 | `'output'` | `list` | ✅ |
| output_dict | `{"output":{"a":1}}` | 400 | `'output'` | `dict` | ✅ |
| output_nested_list | `{"output":[[1],[2]]}` | 400 | `'output'` | `list` | ✅ |
| output_list_of_dict | `{"output":[{"a":1}]}` | 400 | `'output'` | `list` | ✅ |
| **output_empty_list** | `{"output":[]}` | 400 | `'output'` | `list` | ✅ |
| **output_empty_dict** | `{"output":{}}` | 400 | `'output'` | `dict` | ✅ |
| answer_list | `{"instruction":"x","answer":["a"]}` | 400 | `'answer'` | `list` | ✅ |
| answer_dict | `{"question":"q","answer":{"a":1}}` | 400 | `'answer'` | `dict` | ✅ |
| input_dict | `{"input":{"k":1},"output":"y"}` | 400 | `'input'` | `dict` | ✅ |
| input_list | `{"input":["i"],"output":"y"}` | 400 | `'input'` | `list` | ✅ |
| question_dict | `{"question":{"q":1},"output":"y"}` | 400 | `'question'` | `dict` | ✅ |
| question_list | `{"question":["q"],"output":"y"}` | 400 | `'question'` | `list` | ✅ |
| context_list | `{"context":["c"],"output":"y"}` | 400 | `'context'` | `list` | ✅ |
| context_dict | `{"context":{"c":1},"output":"y"}` | 400 | `'context'` | `dict` | ✅ |
| instruction_dict | `{"instruction":{"i":1},"output":"y"}` | 400 | `'instruction'` | `dict` | ✅ |
| instruction_list | `{"instruction":["i"],"output":"y"}` | 400 | `'instruction'` | `list` | ✅ |

（任务点名的 9 种 —— list / dict / 嵌套 list / list 里含 dict / output-list / answer-list / input-dict / question-dict / context-list —— **全部覆盖且全部 400**。）

零副作用的判定依据（每个用例的运行前后快照，原文之一）：

```
副作用: counts {'datasets': 0, 'annotations': 0, 'annotation_tasks': 0,
                'evaluations': 1, 'models': 1, 'inference_logs': 0}
     -> {'datasets': 0, 'annotations': 0, 'annotation_tasks': 0,
                'evaluations': 1, 'models': 1, 'inference_logs': 0}
files [] -> []
```

- `datasets` / `annotations` / `annotation_tasks` 均为 **0**；磁盘无任何残留文件。
- `inference_logs` 未新增 → 证明失败发生在**取预测之前**，没有"跑了一半"的隐藏工作。
- `evaluations` 行为 `('failed', '{"error": ...}')` → **失败被记录**（不是静默），与「不谎报状态」一致。

### 2.3 反面：合法的 `0` / `False` / 数字必须照常计数

| 用例 | test_data | 实测 | sample_count | exact_match |
|---|---|---|---|---|
| output_int0 | `{"output":0}`，预测 `"0"` | 200 | 1 | `{value:1.0, correct:1, total:1}` |
| output_float0 | `{"output":0.0}`，预测 `"0.0"` | 200 | 1 | `{value:1.0, correct:1, total:1}` |
| output_neg0 | `{"output":-0.0}`，预测 `"-0.0"` | 200 | 1 | `{value:1.0, correct:1, total:1}` |
| answer_int0 | `{"answer":0}`（无 `output` 键） | 200 | 1 | `{value:1.0, correct:1, total:1}` |
| output_int42 | `{"output":42}` | 200 | 1 | `{value:1.0, correct:1, total:1}` |
| output_str0 | `{"output":"0"}` | 200 | 1 | `{value:1.0, correct:1, total:1}` |
| output_false | `{"output":False}`，预测 `"false"` | 200 | 1 | `{value:1.0, correct:1, total:1}` |
| output_str_cn | `{"output":"北京"}` | 200 | 1 | `{value:1.0, correct:1, total:1}` |
| instr_int0 | `{"instruction":0,"output":"y"}` | 200 | 1 | `{value:1.0, correct:1, total:1}` |

直接观测 `resolve_samples` 产出的真实 `reference`（`python .qa4/r4_v2v5.py` §V2-b2）：

```
  [output=0        ] reference = '0'
  [output=0.0      ] reference = '0.0'          ← 见 P3-3
  [output=-0.0     ] reference = '-0.0'         ← 见 P3-3
  [output=False    ] reference = 'false'
  [output=42       ] reference = '42'
  [instruction=0   ] prompt = '<|im_start|>user\n0\n<|im_end|>\n<|im_start|>assistant\n'
```

### 2.4 反面：`None` / 缺失 / 空白 / 零宽 / BOM 仍然"跳过"

10 种变体（`None`、键缺失、`""`、`"   "`、`\u3000` 全角、`\u200b`、`\ufeff`、`\u200c`、`\u2060`、`" \u200b\ufeff \u3000"`）：

```
  [混合 none      ] status=200 sample_count=1        ← 与一条合法样本同批：只保留 1 条
  [单独 none      ] status=400 detail='没有可用的评测数据：请在请求体传入 test_data，
                                     或为该评测指定含有参考答案（output/answer）的 dataset_id。'
```

- 混合时 `sample_count == 1` → 空白样本确实被**跳过**（不是被计成 0 条参考）。
- 单独时 400，但文案是 `没有可用的评测数据`，**不含** `值类型不受支持` → 与"类型非法"这条路径严格区分。
- 10 种 × 2 场景 = **20/20 PASS**。

### 2.5 控制组（第三轮核心断言未被回归）

`2×output=0(int) + 2×output=1(int)`，预测全部脚本化为 `"0"`：

```
  status=200 sample_count=4 em={"value": 0.5, "correct": 2, "total": 4}
```

### 2.6 ⚠️ 本轮新引入的回归（重要）

`item.get` 别名回退的**触发条件**被本轮改动改变了。第三轮是「值为 `None` 就回退」，本轮变成「只有键缺失才回退」。A/B 实测：

```
--- HEAD（第三轮）---
  [仅此一条]     {"output": null, "answer": "x"}                      status=200 sample_count=1 em={value:1.0}
  [混一条合法样本] 上条 + {"output":"y"}                                status=200 sample_count=2 em={value:1.0,correct:2,total:2}
  [instruction=null/question=q] 实际 prompt = '<|im_start|>user\nq\n<|im_end|>\n<|im_start|>assistant\n'

--- 当前工作区（第四轮）---
  [仅此一条]     {"output": null, "answer": "x"}                      status=400
                 detail='没有可用的评测数据：请在请求体传入 test_data，…'
  [混一条合法样本] 上条 + {"output":"y"}                                status=200 sample_count=1 em={value:0.0,correct:0,total:1}   ← 样本数从 2 降到 1
  [instruction=null/question=q] 实际 prompt = '<|im_start|>user\n\n<|im_end|>\n<|im_start|>assistant\n'   ← q 丢了
```

`resolve_samples` 直接观测（§V2-b2）：

```
  [instruction=None+question=q   ] prompt = '<|im_start|>user\n\n<|im_end|>...'   reference='y'
  [output=None+answer=x          ] ValueError: 没有可用的评测数据：…
  [output 缺失+answer=x           ] reference='x'      ← 键缺失时回退仍正常
```

判定：**键存在但值为 `null`** 时不再回退别名。这正好落进本项目底线点名的最坏一类 —— 「不报错、数字合理、结论错误」：混批时 `sample_count` 少 1 而 HTTP 200、EM 看起来完全正常。详见 P2-1 / P3-1。

### 2.7 P2-1 / P3-1 的准确机制（实现方更正 + 我的运行时核实）

实现方复核时指出我原报告对 P3-1 的**机制**表述不够准，并给出代码级成因：`build_prompt` 的 `if instruction is None:` 回退分支**并没有被删除**，只是在本轮调用路径上**不可达**。其补充的传导链是：

```
values.py:74-75   if primary in item: return primary, item[primary]   ← 只在键缺失时回退；值为 None 原样返回
evaluate_service.py:227-228   has_visible_content(None) 为假 → continue（样本被剔除）
evaluate_service.py:249       if not samples → 400「没有可用的评测数据」（单条时）
```

我不采信对方的口头结论，用**运行时探针**独立核实（`python .qa4/r4_p3mech.py`，原始输出）：

```
1) build_prompt 的回退分支本身是否还在、是否可用（直接调用）
  build_prompt({'instruction': None, 'question': 'q'})  -> '<|im_start|>user\nq\n<|im_end|>\n<|im_start|>assistant\n'
  build_prompt({'question': 'q'})                       -> '<|im_start|>user\nq\n<|im_end|>\n<|im_start|>assistant\n'
  build_prompt({'instruction': None})                   -> '<|im_start|>user\n\n<|im_end|>\n<|im_start|>assistant\n'
  ↑ 三例说明：只要真的传进 None（或键缺失），回退逻辑照常工作 —— 分支没被删。

2) 值的上游收敛
  require_scalar('instruction', None)                   -> ''      （type = str）

3) 键名解析
  resolve_field(item, 'instruction', 'question')        -> ('instruction', None)
  该键名是否存在于构造出的 prompt dict 中？               -> False   （dict 里没有 question）

4) 复刻 evaluate_service.py:221-223 + 242-244 的构造
  送进 build_prompt 的 dict                              -> {'instruction': '', 'input': ''}
  build_prompt(dict)                                    -> '<|im_start|>user\n\n<|im_end|>\n<|im_start|>assistant\n'

5) 对照：值被收敛成 '' 之后，即便 dict 里同时有 question 键也不回退
  build_prompt({'instruction': '', 'question': 'q'})    -> '<|im_start|>user\n\n<|im_end|>\n<|im_start|>assistant\n'
```

**核实结论**：实现方的机制更正是**成立**的 —— 回退分支存在且单独调用可用（第 1 节），不可达的直接原因是「值在上游被 `coerce_scalar(None)` 收敛成 `""`」+「dict 的键名是 `instruction`、不含 `question`」（第 2/3/4 节）；第 5 节进一步排除了"只要补一个 `question` 键就能自动恢复"的想法 —— 因为 `item.get("instruction")` 拿到的是 `""` 而不是 `None`，`is None` 判断依然不成立。

**这对修复方案的含义（重要）**：不能靠"把 `question` 塞进 dict"来绕，必须让**上游**别把 `None` 提前收敛成 `""`（即评测侧在 `require_scalar` 之前完成别名回退），或让 `build_prompt` 的判空改成「值为 `None` **或空串**时回退」——后者会改变语义（显式传 `instruction: ""` 时也会被 `question` 顶掉），我不推荐。这也是为什么我建议 `resolve_field(..., fallback_when_none=True)` 只给评测侧用的原因：把回退放回**取值阶段**，而不是留给下游补救。

> 本节的机制归属：代码级成因由实现方提供（其侧无法运行探针）；运行时证据由我提供。

---

## 三、V3：NaN / Infinity 必须 400 且不留矛盾行

### 3.1 第三轮 P2-B 是实测复现的（HEAD 侧）

```
--- HEAD（第三轮）---
  [output=NaN      ] status=200
        annotations=[(1, 1, 'completed', None, 1)]
        ↑ is_null=1 → status='completed' 但 output_text IS NULL —— 自相矛盾状态实测存在
  [output=Infinity ] status=200  annotations=[(1, 1, 'completed', 'Inf', 0)]
  [output=-Infinity] status=200  annotations=[(1, 1, 'completed', '-Inf', 0)]
  [output=1e400    ] status=200  annotations=[(1, 1, 'completed', 'Inf', 0)]
```

顺带把第三轮**未验证**的 `Infinity` / `-Infinity` / `1e400` 补齐了：HEAD 侧三者**都被放行**，落库为文本 `'Inf'` / `'-Inf'`（`NaN` 才是被存成 `NULL` 的那个）。

### 3.2 当前工作区：四种写法全部 400 且零副作用

```
  [.json output=NaN      ] status=400 detail="数据导入失败: 字段 'output' 的值不是有效数字：
      实际为 nan（类型 float）。NaN / Infinity 虽然能被 json.loads 与 pandas.to_json 产出，
      但不是合法的 JSON 数字，也无法写入数据库（会被存成空值）。请改用有限数字或字符串。"
        annotations=[]  counts={'datasets': 0, 'annotations': 0, 'annotation_tasks': 0, ...} files=[]
  [.json output=Infinity ] status=400  ... 实际为 inf ...
  [.json output=-Infinity] status=400  ... 实际为 -inf ...
  [.json output=1e400    ] status=400  ... 实际为 inf ...      ← 1e400 解析为 inf，被同一守卫拦住
  [.jsonl 行内 NaN        ] status=400  ... 实际为 nan ...
```

评测侧（`httpx` 的 `json=` 会走 `allow_nan=False`，故用**原始字节**绕过，即任务所指的 bypass 手法）：

```
  payload = b'{"test_data":[{"instruction":"x","output":NaN}]}'
  → status=400 detail="字段 'output' 的值不是有效数字：实际为 nan（类型 float）。…"
  → 副作用: 所有计数不变；files [] -> []
```

`Infinity` / `-Infinity` / `1e400` 同样 400，同样零副作用。

### 3.3 关键判据：不得存在 `status='completed' AND output_text IS NULL` 的行

```
  SELECT COUNT(*) FROM annotations WHERE status='completed' AND output_text IS NULL   ->  0
  SELECT COUNT(*) FROM annotations WHERE status='completed' AND (output_text IS NULL OR output_text='') -> 0
```

在跑完上述全部 4 种导入变体 + 4 种评测变体之后查询 —— **0 行**。这条判据是本项真正的验收标准（只看"返回 400"不够，要看**库里没有留下自相矛盾的残行**）。

### 3.4 对抗扩展：NaN 藏在未被守卫的字段里（残留，P3-2）

```
  test_data/file = [{"instruction":"x","output":"y","meta":NaN,"nested":{"n":Infinity}}]
  status=200
  annotations=[(1, 1, 'completed', 'y', 0, 0)]           ← 内容字段正常
  raw_data(库内) = ('{"instruction": "x", "output": "y", "meta": NaN, "nested": {"n": Infinity}}',)
  磁盘 datasets\dataset_1.json = '[\n  {\n    "instruction": "x",\n    "output": "y",\n    "meta": NaN,\n    "nested": {\n      "n": Infinity\n    }\n  }\n]'
  check: 库内 contradictions = 0
```

守卫只覆盖 `instruction` / `input` / `output` 三个**内容字段**；`raw_data`（`JSON` 列）与归档 JSON 文件**原样保留了非法 JSON**。HEAD 同形（`raw_data=item` 两侧一致）→ **既有、非本轮引入**，且**不产生自相矛盾状态**（`output_text` 是干净的 `'y'`），故评 P3。风险面：严格 JSON 客户端（浏览器 `JSON.parse`、Go/Rust 解析器）无法解析归档文件里的 `NaN` / `Infinity`。

> V3 判定：**声明生效**（P2-B 已修，且用 HEAD 实测坐实了原缺陷）；残留 1 条 P3（见 P3-2）。

---

## 四、V4：`test_data=[]` 不得回退到数据集

### 4.1 缺陷实测存在（HEAD）

```
--- HEAD（第三轮）---
  数据集 id=1 total=2
  [test_data 缺省（应回退 dataset）] status=200 sample_count=2
  [test_data=null（应回退 dataset）] status=200 sample_count=2
  [test_data=[]（不得回退）      ] status=200 sample_count=2   ← 静默回退，用数据集评了 2 条
```

### 4.2 当前工作区

```
  [完全不传 body   ] status=200 sample_count=2      ← 回退正常
  [空对象 body     ] status=200 sample_count=2      ← 回退正常
  [test_data=null  ] status=200 sample_count=2      ← 回退正常
  [test_data=[]    ] status=400
      detail='test_data 已传入但为空列表（[]），没有任何可评测的样本。
              若要改用评测关联的数据集，请省略 test_data 或显式传 null。'
      副作用: {'datasets': 1, 'annotations': 2, 'annotation_tasks': 0,
               'evaluations': 3, 'models': 3, 'inference_logs': 6}
           -> {'datasets': 1, 'annotations': 2, 'annotation_tasks': 0,
               'evaluations': 4, 'models': 4, 'inference_logs': 6}
      files ['datasets\\dataset_1.json', 'datasets\\dsv4.jsonl'] -> 同上（不变）
  关联数据集现状: {'id': 1, 'name': 'dsv4', 'total_samples': 2}
  /api/data/1/export -> 200
```

（`evaluations` / `models` 各 +1 是我探针每次新建评测与模型所致，不是产品副作用；其余计数与文件列表**完全不变**。）

任务要求的三点全部满足：
1. 文案点明「**空列表（[]）**」—— 原文 `test_data 已传入但为空列表（[]）`；
2. 文案给出「**省略 test_data 或显式传 null**」的回退方式；
3. 控制面：`test_data` 省略 / `{}` / `null` 三种"真的没传"的形态**都仍正常回退**（`sample_count=2`），未把"没传"误伤成"传了空"。

> 判定：**PASS**（第三轮 P3-1 已修，且 HEAD 侧缺陷实测复现）。

---

## 五、V5：`.json` 顶层不是数组时必须报真实顶层类型

### 5.1 A/B 对照（原始输出）

```
--- HEAD（第三轮）---
  [单对象 (.json)]   400 detail="数据导入失败: 文件中存在非对象记录：…但解析到类型 str。"        ← 报错了对象：真实顶层是 object
  [空对象 (.json)]   400 detail='数据导入失败: 文件中没有任何有效记录：…'
  [标量 int (.json)] 400 detail="数据导入失败: object of type 'int' has no len()"              ← 原始 Python 异常文本
  [标量 str (.json)] 400 detail="…但解析到类型 str。"
  [null (.json)]     400 detail="数据导入失败: object of type 'NoneType' has no len()"          ← 原始 Python 异常文本
  [空数组 (.json)]   400 detail='数据导入失败: 文件中没有任何有效记录：…'
  [数组含标量 (.json)] 400 detail="…但解析到类型 int。"

--- 当前工作区（第四轮）---
  [单对象]   400 detail="数据导入失败: JSON 文件的顶层结构不是数组：解析到的顶层类型是 对象（object），
                        无法逐条提取样本。请用数组包裹记录（形如 [{'instruction': ..., 'output': ...}, ...]），
                        或改用 .jsonl（每行一条记录）。"
  [空对象]   400 …顶层类型是 对象（object）…
  [标量 int] 400 …顶层类型是 int…
  [标量 str] 400 …顶层类型是 str…
  [标量 true]400 …顶层类型是 bool…
  [null]     400 …顶层类型是 NoneType…
  [数组套数组] 400 detail="…但解析到类型 list。"        ← 仍由"每行必须是对象"这条拦下，正确
  [空数组]   400 detail='…文件中没有任何有效记录：…'     ← A1 分支，正确
```

### 5.2 逐条"是否说真话"

| 输入 | 真实顶层类型 | 本轮报出的类型 | 说真话？ |
|---|---|---|---|
| `{"instruction":"x","output":"y"}` | object | `对象（object）` | ✅（HEAD 误报 `str`） |
| `{}` | object | `对象（object）` | ✅ |
| `123` | int | `int` | ✅（HEAD 抛原始 `len()` 文本） |
| `"x"` | str | `str` | ✅（这条 HEAD 也"蒙对"了） |
| `true` | bool | `bool` | ✅ |
| `null` | NoneType | `NoneType` | ✅（HEAD 抛原始 `len()` 文本） |
| `[]` | list（空） | A1 分支：`没有任何有效记录` | ✅ |
| `[[1,2]]` | list | `非对象记录…解析到类型 list` | ✅ |

全部 400，`datasets`/`annotations` 均为 0，磁盘无残留。

**额外收获**：本轮顺带修掉了两条**比我第三轮报告的更糟**的返回 —— HEAD 对顶层 `123` / `null` 直接把 Python 内置异常文本（`object of type 'int' has no len()`）当成用户可见的 `detail` 返回。这一条我之前没报，属于本轮新增的改进。

**边界（不算缺陷，供知悉）**：`.jsonl` 里的单对象 `{"instruction":"x","output":"y"}` 仍是 **200**（jsonl 按行 append 成数组，语义上本就是"一条记录"），与 `.json` 的顶层校验不冲突。

> 判定：**PASS**（第三轮 P3-2 已修，且**消息真实性**逐条核对通过）。

---

## 六、V6：薄委托与"既有错误文案一字不变"

### 6.1 方法：源码 diff + 运行时逐字比对（双重）

**（a）源码层**：`git diff HEAD -- app/services/data_service.py` 显示四个方法都变成了薄委托，且 `_require_scalar` 的既有文案（4 段字符串拼接）**原样搬走**：

```diff
     @staticmethod
     def _require_scalar(field_name: str, value: Any) -> Any:
-        """校验字段值为标量；非标量直接抛 ``ValueError``（路由映射为 400）。
-        ...
-        """
-        value = DataService._coerce_scalar(value)
-        if isinstance(value, (str, int, float, bool)) or value is None:
-            return value
-        raise ValueError(
-            "字段 '{field}' 的值类型不受支持：内容字段只能是标量"
-            "（字符串 / 数字 / 布尔 / 空值），实际为 {actual_type}。"
-            "请将该字段改为字符串后再导入（例如把列表拼接为一段文本，"
-            "或改用多条记录表达）。".format(
-                field=field_name, actual_type=type(value).__name__
-            )
-        )
+        """薄委托，实现统一收敛在 app.core.values.require_scalar。
+
+        保留同名方法是为了不惊动既有调用点，并确保既有错误文案一字不变。
+        """
+        return require_scalar(field_name, value)
```

`app/core/values.py` 中 `require_scalar` 的前 4 段字符串与 HEAD 的 `_require_scalar` **逐字相同**（新增的只有后面的 `math.isfinite` 分支）；`coerce_scalar` 的分支体（`None→""`、`str` 原样、`bool→"true"/"false"`、`int/float` 原样、其它原样返回）**逐字相同**；`resolve_field` 的**函数体**逐字相同（仅 docstring 措辞变化，非用户可见文案）。

**（b）运行时层**：用同一支探针（`.qa4/r4_ab.py` 的 G 段）在两棵树上跑 21 组导入侧非法输入，再用脚本（`.qa4/r4_v6_cmp.py`）按**标签配对、按字节比对**：

```
HEAD 采集到 29 条；当前工作区采集到 34 条
缺失用例: 无

[一致] list_int           status=400 文案逐字相同（112 字符）
[一致] dict               status=400 文案逐字相同（112 字符）
[一致] nested_list        status=400 文案逐字相同（112 字符）
[一致] list_of_dict       status=400 文案逐字相同（112 字符）
[一致] output_list        status=400 文案逐字相同（107 字符）
[一致] input_dict         status=400 文案逐字相同（106 字符）
[一致] answer_list        status=400 文案逐字相同（107 字符）
[一致] question_dict      status=400 文案逐字相同（109 字符）
[一致] context_list       status=400 文案逐字相同（108 字符）
[一致] list_of_list_mixed status=400 文案逐字相同（112 字符）
[一致] row2_list          status=400 文案逐字相同（91 字符）
[一致] row2_number        status=400 文案逐字相同（90 字符）
[一致] row2_string        status=400 文案逐字相同（90 字符）
[一致] row2_null          status=400 文案逐字相同（95 字符）
[一致] row2_array         status=400 文案逐字相同（91 字符）
[一致] row2_dict_bad      status=400 文案逐字相同（107 字符）
[一致] all_space          status=400 文案逐字相同（267 字符）
[一致] all_zwsp           status=400 文案逐字相同（267 字符）
[一致] unknown_keys       status=400 文案逐字相同（259 字符）
[一致] A1 空文件             status=400 文案逐字相同（84 字符）
[一致] A1 仅空行             status=400 文案逐字相同（84 字符）

=== 结论：逐字相同 21 例，不同 0 例 ===
```

覆盖的既有文案：`值类型不受支持`（8 种字段/类型组合）、`文件中存在非对象记录…解析到类型`（int/str/NoneType/list）、`没有任何记录包含可识别的内容字段…`（含键名回显 `['instruction','output']` / `['label','text']`）、`文件中没有任何有效记录…`。

### 6.2 文案变化清单（全量，不隐瞒）

V6 要求的"既有文案一字未变"**成立**，但为了让上架审查不含糊，我把**所有可观测的文案/路径变化**列全：

| # | 输入（同一条探针） | 第三轮 | 第四轮 | 性质 |
|---|---|---|---|---|
| 1 | `.json` 顶层单对象 / 空对象 | `解析到类型 str` | `顶层类型是 对象（object）` | **有意修复**（P3-2，V5） |
| 2 | `.json` 顶层 `123` / `null` | `object of type 'int' has no len()` 等原始异常文本 | `顶层类型是 int` / `NoneType` | **有意修复**（V5 的意外收获） |
| 3 | 评测 `test_data=[]` | 200 且回退数据集 | 400 + `test_data 已传入但为空列表（[]）…` | **有意修复**（P3-1，V4） |
| 4 | 评测侧非标量参考值 | 200（repr 参与指标） | 400 + `字段 'output' 的值类型不受支持…` | **有意修复**（P2-A，V2） |
| 5 | 评测侧 `output=NaN` 等 | 200（NaN 落库为 NULL） | 400 + `字段 'output' 的值不是有效数字…` | **有意修复**（P2-B，V3） |
| 6 | 导入侧 `output=NaN` 等 | 200（落库） | 400 + `…不是有效数字…` | **新增守卫**（V3） |
| 7 | 评测 `{"instruction":[1],"output":""}` | 400 `没有可用的评测数据` | 400 `字段 'instruction' 的值类型不受支持…` | 行为变化，**非缺陷**（见缺陷一览「登记」行） |
| 8 | 评测 `{"output":null,"answer":"x"}` | 200 且计入 | **400/样本被丢** | **回归 → P2-1** |
| 9 | 评测 `{"instruction":null,"question":"q"}` | prompt 含 `q` | prompt 为空 | **回归 → P3-1** |

第 7 条的实测证据（`.qa4/ab_order.txt`）：

```
--- HEAD ---    [instruction 非标量 + output='' ] 400 '没有可用的评测数据：…'
--- 当前 ---    [instruction 非标量 + output='' ] 400 "字段 'instruction' 的值类型不受支持：…实际为 list。…"
```

> V6 判定：**PASS**。21/21 逐字相同；变化项共 9 条，其中 6 条是有意修复、1 条是可接受的行为变化、2 条是**需要修的回归**。

### 6.3 补充：HTTP/JSON 无法表达的类型，两侧口径已一致

第三轮我只在导入侧的服务层验过 `tuple/set/bytes/...`。本轮补测**两条路径**（`python .qa4/r4_types.py`）：

```
  [导入侧 tuple     ] ValueError -> 字段 'output' 的值类型不受支持：…实际为 tuple。…
  [评测侧 tuple     ] ValueError -> 字段 'output' 的值类型不受支持：…实际为 tuple。…
  [导入侧 set/bytes/complex/frozenset/dict_keys/range ] 同上，逐一拒绝
  [评测侧 set/bytes/complex/frozenset/dict_keys/range ] 同上，逐一拒绝
```

7 种类型 × 2 条路径 = 14/14 拒绝，**且文案逐字相同** → "与导入侧口径一致"这一声明成立。

---

## 七、关于 `max_samples` 静默截断：我同意本轮不修，但附两条证据

team-lead 请我在认为裁定不对时给反证。我的实测结论是**该定性站得住**，但**有一条文档错误需要修**。

### 7.1 实测（`python .qa4/r4_extra.py` + `python .qa4/r4_types.py`）

`test_data` 路径（`max_samples=2`，提交 5 条）：

```
当前 settings.evaluation.max_samples = 2
提交样本数 = 5；HTTP 200
results 的所有键 = ['backend', 'backend_is_real_model', 'exact_match', 'metric_definitions', 'sample_count']
sample_count = 2
exact_match  = {"value": 1.0, "correct": 2, "total": 2}
```

`dataset_id` 路径（`max_samples=1`，数据集 3 条）：

```
导入数据集 total_samples = 3
dataset 路径 run -> HTTP 200 sample_count=1 em={"value": 0.0, "correct": 0, "total": 1}
results 键 = ['backend', 'backend_is_real_model', 'exact_match', 'metric_definitions', 'sample_count']
```

### 7.2 我的判断

- **同意"限制"而非"谎报"**：`sample_count = len(samples)` 取的是截断后的真实值（`app/services/evaluate_service.py:136`），它陈述的是"实际参与计算的条数"，**没有声称评过 5 条**。这与 P2-A/P2-B 那类"返回 200 却落一个自相矛盾的状态"性质不同 —— 后者是**说假话**，这条只是**少说一句**。README 把两者区分开，定性准确。
- **反证方向**（供决策者权衡，不构成本轮必须修）：`results` 里确实**没有任何字段**说明"你提交了 N 条"（实测键列表见上），且 `dataset_id` 路径**同样静默**（我原本只测了 `test_data` 路径，补测后确认两条路径走的是同一行 `samples[:max_samples]`）。也就是说，一个不知道默认上限 100 的调用方，**无法从响应里察觉样本被丢**。若本版允许"契约新增"，加一个 `provided_count` 字段是 3 行改动；若坚持不动契约，则至少应在 **控制台评测页**给出提示（当前控制台没有该提示，我没有验证前端——见 §八）。
- **必须修的文档错误（P3-4）**：README 限制 #9 引用

  ```
  （`app/services/evaluate_service.py:248`）以 `samples[:max_samples]` 截断
  ```

  实测该行是 `app/services/evaluate_service.py:255`（`:248` 落在 `samples.append(...)` 的收尾括号上）。同一段里 `（app/services/evaluate_service.py:136）` 的 `sample_count` 行号**是对的**。建议改成 `:255`。

---

## 八、未能验证项（明确列出，不掩饰）

1. **真实 uvicorn 进程 + 浏览器/控制台端到端**：本轮全部验证走 in-process `TestClient` 与 `pytest`，未起真实 HTTP 服务、未验证 `app/web/*` 前端行为。改动未触及 `app/web`（`git status` 中无该目录），但"控制台是否会因新增 400 而白屏/无提示"我**没有验证**。
2. **多进程/多线程并发下的行为**：`max_samples` 截断、`resolve_field`、`require_scalar` 都是纯函数或单请求内逻辑，未做并发压测。
3. **`raw_data` 非法 JSON 对下游的影响面**：我只证明了"能写进去、能读回来"，未穷举哪些消费方（前端、导出脚本、外部系统）会因此解析失败。
4. **`TEST-REPORT.md` 的整体不实核对**：本轮任务未要求重审该文件，且它在验证期间被并行修改（22:58 mtime）；我只做了**与本轮改动直接相关**的测试注释更正核对（见 §九.2）。该文件的完整真实性仍是第三轮的结论（`QA-VERIFY-3.md` §七）。
5. **`app/services/evaluate_service.py:255` 截断与 Web 控制台的联动**：见 §7.2，前端未验证。
6. **100MB 上传上限、鉴权、路径穿越等既有安全面**：本轮未复测（不在 V1–V6 范围，且未改动）。

---

## 九、我认为作者声明不实或夸大的地方

### 9.1 代码/文案层面：**无新增不实**

- engineer-3 自报的 6 项改动（P2-A、P2-B、P3-1、P3-2、标量契约提升为公共层、"既有文案一字未变"）**逐项经我独立实测确认，全部成立**，未发现夸大或虚报。
- 唯一需要注意的措辞是 `require_scalar` 的 NaN 文案：

  > `NaN / Infinity … 也不是合法的 JSON 数字，也无法写入数据库（会被存成空值）。`

  这句话对它**点名的那个字段**（`output_text` 等 TEXT 列）是准确的（实测 NaN → NULL）；但严格说平台**并非"无法写入数据库"** —— 同一批数据里的 `NaN` 会被原样写进 `raw_data` JSON 列与归档 JSON 文件（§3.4 实测）。建议文案限定作用域，例如"无法写入本字段的文本列"。**不构成谎报**（它没有声称"平台任何地方都不会存 NaN"），仅属措辞可收紧。

### 9.2 值得肯定的更正（不是问题，但必须记录）

本轮把两条测试注释里的**"修复前实测"改成了"代码推导（非实测）"**，并**撤回了一条错误的实测表述**：

```diff
-        修复前实测：sample_count=2、EM=0.0（一半数据被静默丢弃）。
+        旧行为（**代码推导，非在本代码库上跑出的修复前实测值**）：
+        ``item.get("output") or item.get("answer") or ""`` 中 ``0 or ...`` 短路成
+        ``""``，带 output=0 的两条会被 ``continue`` 静默丢弃 ⇒ 样本数 2、
+        EM = 0.0（两条预测 "0" 对不上参考 "1"）。本用例只固化**修复后**的期望值。
```

```diff
+        更正记录：本用例注释早期写的是「修复前实测 run 400」，那条观察**成因
+        不是 falsy 短路**——当时探针把 ``test_data`` 误传给了 ``/create``（该端点
+        不接收此字段），``/run`` 无 body 才导致 400。已撤回该表述，改为纯代码推导。
```

我核对了两件事，结论是该更正是**诚实且正确**的：

1. **推导前提成立**：`unillm-platform_源码全文.md:2961` 确实存在
   `reference = item.get("output") or item.get("answer") or ""`，因此"`0 or ...` 短路成空串 → 样本被 `continue`"的推导有真实代码依据（不是臆测）。
2. **撤回的成因解释成立**：`RunEvaluationRequest` 只声明 `test_data`，向 `/create` 传 `test_data` 会被忽略（Pydantic 默认忽略未知字段），随后 `/run` 无 body → `test_data=None`、无 `dataset_id` → 必然 `没有可用的评测数据`。所以"当时的 400 不是 falsy 短路造成的"这一更正是对的。

这正好是第三轮我提的「不实/夸大」问题的**正面闭环**，我在本轮记录为改进项。

---

## 十、修复优先级建议

| 优先级 | 项 | 建议改动 | 代价 |
|---|---|---|---|
| **P2（建议交付前修）** | P2-1：`output: null` + `answer` 有值时样本被静默丢弃 | 评测侧恢复"值为 `None` 也回退"的语义。最小改法：在 `resolve_samples` 里改用 `item.get(primary)`，为 `None` 时再取 `item.get(alias)`（即保留 HEAD 的 None-回退），或在 `resolve_field` 上加 `fallback_when_none: bool = False` 让导入侧保持现状、评测侧传 `True`。**不要**直接改 `resolve_field` 的默认语义（会连带改变导入侧行为与 V6 的文案不变承诺） | ~3 行 + 1 个测试 |
| **P3** | P3-1：`instruction/input` 为 `null` 时 prompt 丢掉 alias 内容（回退分支存在但不可达，见 §2.7） | 与 P2-1 同源，一并修；修法必须落在**取值阶段**（`resolve_field(..., fallback_when_none=True)` 只给评测侧），**不要**改成「空串也回退」——那会让显式传 `instruction: ""` 时被 `question` 顶掉。若坚持"`null` 即显式空"的新契约，则必须改 `build_prompt` 的 docstring（现写"回退只在键缺失 / 值为 `None` 时发生"，与实际路径不符）并补一条测试固化 | 随 P2-1 |
| **P3** | P3-4：README `evaluate_service.py:248` → `:255` | 一行 | 1 行 |
| **P3** | P3-5：`docs/QA-REPORT.md:8-21` 后补导航表的轮次编号（QA-VERIFY-3 记为"第四轮"、QA-VERIFY-4 记为"第五轮"）与团队任务口径（第三轮 / 第四轮复验）差一轮 | 在表头注明计数基准（是"含控制台化那一轮的全部轮次"还是"仅平台侧轮次"），或改用文件名作为主键 | 2 行 |
| **P3（可延后，需登记）** | P3-2：`raw_data` / 归档 JSON 仍含 `NaN`/`Infinity` | 若要修：对 `raw_data` 递归校验非有限浮点，且 `json.dump(..., allow_nan=False)` 并在失败时明确 400 | ~15 行 |
| **P3（可延后，口径）** | P3-3：数值参考值按 `str()` 字符串化（`0.0` → `"0.0"` → 归一化后 `"00"`） | 若要修：`reference` 规范化（如整数型浮点去尾）或文档写明口径。**不是本轮引入**，0 的计数已正确 | 视口径决定 |
| 登记 | 「非标量 instruction + 空参考」由跳过改为整体 400 | 建议在 README/测试里固化这一契约（现在只有测试隐含覆盖） | 1 条测试 |

---

## 十一、验证对象在验证期间发生**第二次变更**：对新树的追加复验（v3）

### 11.1 时间线与变更内容（谁在什么时候动了什么）

| 时刻 | 事件 |
|---|---|
| 23:00:17 | 我跑完全量测试并落盘 `.qa4/junit_r4.xml`（`tests="211"`） |
| 23:08 | 我采集产品文件 md5 快照（记于 §零.3），此即 v1/v2 结论的有效对象 |
| **23:11:32** | **`app/core/values.py` 被改动** |
| **23:11:42** | **`app/services/evaluate_service.py` 被改动** |
| 23:12:21 | `tests/test_scalar_contract.py` 被改动 |
| 23:12 | 我发出报告 v2（此时产品文件已与我的取证快照不同） |
| 23:15–23:17 | 我发现漂移，在**新树**上重跑全量 / 主矩阵 / 验收契约（本节全部数据） |

**改动的执行者与归属（已核对，写明以免后人误判）**：这轮改动由 **team-lead 执行并自证**，**不是** software-engineer-3 所为。依据两条：

1. **时序与状态**：engineer-3 的 Bash 会话已不可用（其自述 `exit 127`），在 team-lead 下达「停笔、不编辑任何文件、不 commit」之后，他全程只使用只读工具（Read / Grep），**未写入任何文件**；他在给 team-lead 的裁定请求里也写明「我处在停笔 + Bash 不可用状态，改完无法自证，按你的规矩我不动手」。
2. **实现方转述的 team-lead 原话**：「不用你做了，我已经改完并验证……我的 Bash 可用，改完能当场自证，所以由我直接落地」，其告知的落点（`values.py` 加关键字限定参数、评测侧三处传 `True`、另补 6 条 `TestAliasFallbackWhenValueIsNone`）与本节的 md5/mtime 实测**完全吻合**。

也就是说：**本节的追加复验，实质上是"QA 独立复验 team-lead 本人落地的改动"** —— 由改动者自证之后再经第三方实测，与前面各轮「实现方改、QA 验」的分工不同，但验证强度不打折（结论全部来自我这一侧的可复现探针）。

`.qa4/r4_accept.py` §0 的原始输出（新树 vs 我 23:08 的快照）：

```
  app/core/values.py                         1025c737dcedb85ee30436dfbc10f870  (我 23:08 记录 2b248d2719c329b5bcedfd48c865dc96) -> **已变**
  app/services/data_service.py               37723aeadd2891aff0d9a588bd5fc974  (我 23:08 记录 37723aeadd2891aff0d9a588bd5fc974) -> 未变
  app/services/evaluate_service.py           2fdc3ba8f69759ff0e3b8d08b7569760  (我 23:08 记录 a5264ad46ded3f8a9878a40ad312fac8) -> **已变**
  tests/test_scalar_contract.py              0049df326fde8b4344188161ce8baa5f  (我 23:08 记录 7d9a96528984680cb92156d5ae48f13b) -> **已变**
```

**改动内容正是 P2-1 / P3-1 的修法**（实现方在任务 #22 里的提案，我的报告 §2.7 与 §十 也推荐了同一方向）：

```
app/core/values.py
  67: def resolve_field(
  68:     item, primary: str, alias: str, *, fallback_when_none: bool = False
  69: ) -> Tuple[str, Any]:
  87:     if primary in item:
  88:         value = item[primary]
  89:         if not (fallback_when_none and value is None):
  90:             return primary, value
  91:     if alias in item:
  92:         return alias, item[alias]
  93:     return primary, item.get(primary, "")

app/services/evaluate_service.py   ← 只有评测侧三处显式开启
 231:                 item, "instruction", "question", fallback_when_none=True)
 233:                 item, "input", "context", fallback_when_none=True)
 235:                 item, "output", "answer", fallback_when_none=True)
```

**导入侧一个字节未动**（`data_service.py` md5 与我的快照完全相同），这正是 V6「既有文案一字不变」得以继续成立的原因。同时夹带的 5 条附带变更：

1. `values.py` 的 NaN 文案**收紧**了作用域（回应我 §9.1 的措辞意见）：由「**也无法写入数据库**（会被存成空值）」改为「**写入该内容列时**会被 SQLite 存成空值」——不再声称"平台任何地方都存不了 NaN"。
2. `evaluate_service.py:276-279` 的 `build_prompt` 注释改为与实际路径一致（原注释声称「回退只在键缺失 / 值为 None 时发生」，与调用路径不符）——即我 §2.7 / 缺陷表 P3-1 备注里点名的那处矛盾已消除。
3. `README.md` 限制 #9 不再写死行号，改为「（`app/services/evaluate_service.py`，本版位于 `:267`；**行号会随编辑漂移，请以该表达式为准**）」——即 **P3-4 已修，且改法比"只把 248 换成 255"更稳**。
4. `README.md:289` 的预期计数由 `211` 改为 `217`（与本轮 +6 条测试对齐）。
5. `docs/QA-REPORT.md:8-26` 的导航表新增「**轮次编号基准（重要）**」段，明确声明本表以「控制台化改造那一轮」为第 1 轮起算、并指示**以报告文件名为准而不是轮次序号** —— 即 **P3-5 已修**。
6. `tests/test_scalar_contract.py` 新增 `TestAliasFallbackWhenValueIsNone`（6 条），直接固化「默认档 = 导入侧语义 / 显式档 = 评测侧语义」与「混批不得静默缩小」。

> **声明**：这次改动**不是我做的**。我在整个复验期间只写入 `.qa4/` 下的探针与原始输出，以及本报告自身；产品代码、测试、其它文档一律未动（见 §11.6 与附录 C）。

### 11.2 新树上的重跑证据

**（a）全量测试**（单进程一次跑完，与 V1 同法）：

```
tests\test_metrics.py ............                                       [ 46%]
tests\test_scalar_contract.py .......................................... [ 65%]
........                                                                 [ 69%]
tests\test_security_hardening.py .......................................  [ 87%]
.......                                                                  [ 90%]
tests\test_upload_safety.py ....................                         [100%]

====================== 217 passed, 2 warnings in 22.18s =======================
FULL_EXIT=0
```

```
<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="217"
           time="22.171" timestamp="2026-09-13T23:16:11.074055+08:00" hostname="media">
testcase 元素数 = 217          （ElementTree 解析，与属性一致）
```

| 文件 | 旧树 | **新树** |
|---|---|---|
| `tests/test_scalar_contract.py` | 44 | **50**（+6） |
| `tests/test_security_hardening.py` | 46 | 46 |
| `tests/test_input_validation.py` | 35 | 35 |
| `tests/test_closed_loop.py` | 21 | 21 |
| `tests/test_upload_safety.py` | 20 | 20 |
| `tests/test_auth.py` | 13 | 13 |
| `tests/test_metrics.py` | 12 | 12 |
| `tests/test_evaluation_references.py` | 11 | 11 |
| `tests/test_errors.py` | 9 | 9 |
| **合计** | **211** | **217** |

**（b）主对抗矩阵 V2–V5 重跑**（`.qa4/r4_v2v5.py`，178 条断言）：`PASS=178  FAIL=0` —— 与旧树同分，**新增改动没有打回任何既有判定**。别名回退的直接观测已翻转为修复后的行为：

```
  [output=0                      ] reference = '0'
  [instruction=None+question=q   ] prompt = '<|im_start|>user\nq\n<|im_end|>\n<|im_start|>assistant\n'
  [output=None+answer=x          ] reference = 'x'          ← 旧树此处为 ValueError
  [output 缺失+answer=x           ] reference = 'x'
```

空白类（`None` / 缺失 / `""` / 空白 / 零宽 / BOM）仍按「真无值」跳过，且单独一条时仍报 `没有可用的评测数据` 而**不是**类型错。

**（c）按实现方给出的 6 条验收契约逐条取证**（`.qa4/r4_accept.py`）：**`PASS=25  FAIL=0`**。

### 11.3 六条验收契约的逐条结果

| # | 契约 | 实测 |
|---|---|---|
| 1 | `{"output": null, "answer": "x"}` 单独 → 200 / `sample_count=1` / EM=1.0；混批 → 2 | ✅ `status=200 sample_count=1 em={"value": 1.0, "correct": 1, "total": 1}`；混批 `sample_count=2 em={"value": 1.0, "correct": 2, "total": 2}` |
| 2 | `{"instruction": null, "question": "q"}` → prompt 含 `q` | ✅ 实际 prompt（捕获真实送进后端的字符串）= `<\|im_start\|>user\nq\n<\|im_end\|>\n<\|im_start\|>assistant\n` |
| 3 | **判别性反例**：`{"instruction": "", "question": "q"}` → instruction 保持空、不被 `q` 顶掉 | ✅ prompt = `<\|im_start\|>user\n\n<\|im_end\|>...`，**完全不含 `q`** → 证伪「改成 `None` 或空串都回退」那种改法 |
| 4 | `{"output": null}` 且无别名 → 仍跳过 / 400 | ✅ 单独 400「没有可用的评测数据」；混批 `sample_count=1`；空串/空白/零宽/全角/BOM 仍全部跳过 |
| 5 | **硬回归**：`{"output": 0}` 必须仍保留 | ✅ `output=0` / `0.0` / `False` / `answer=0` / `instruction=0` 均 `sample_count=1` 且 `correct=1`；控制组 2×0+2×1 → `sample_count=4 em={"value": 0.5, "correct": 2, "total": 4}` |
| 6 | 导入侧既有文案 21/21 逐字相同 | ✅ 与 `.qa4/ab_head.txt`（第三轮原文）按字节比对：`逐字相同 21 例，不同 0 例` |

两条我额外追加的扩展（不在原契约内，但同源风险点）：

```
  [扩展] instruction=0（falsy 合法值）prompt = '<|im_start|>user\n0\n<|im_end|>\n<|im_start|>assistant\n'
        → instruction=0 保留为 '0'，未被 question 顶掉
  [扩展 output=0 + answer=x] -> status=200 sample_count=1 em={"value": 0.0, "correct": 0, "total": 1}
        → 显式的 output=0 优先于别名 answer='x'（未被"回退"误伤）
```

第二条尤其关键：`fallback_when_none` 只对 `None` 生效、**不碰 falsy 合法值**，这正是第 5 条硬回归与第 3 条判别性反例能同时成立的原因。

### 11.4 对报告前文的影响（过期引用清单，不就地覆盖）

| 前文位置 | 旧值（对应 23:08 快照） | 新树现状 |
|---|---|---|
| §零.3 md5 表 | `values.py=2b248d27…`、`evaluate_service.py=a5264ad4…`、`test_scalar_contract.py=7d9a9652…` | `1025c737…` / `2fdc3ba8…` / `0049df32…` |
| 缺陷一览 P2-1 位置 | `evaluate_service.py:221-236` | 相应代码现位于 `:213-267`（三处 `resolve_field` 在 `:230-235`） |
| 缺陷一览 P3-1 位置 | `:242-244`（调用点） | `:254-256` |
| §2.7 探针引用的行号 | `values.py:74-75` | 现为 `values.py:87-93` |
| §3.2 的 NaN 文案引文 | 「也无法写入数据库（会被存成空值）」 | 已收紧为「写入该内容列时会被 SQLite 存成空值…」 |
| §七 P3-4 | README 写 `:248`，应为 `:255` | README 已改为 `:267` + 「以表达式为准」措辞 |
| 结论表 V1 | `211` | `217` |

**保留旧值不覆盖**，是为了让读者能把两个快照对上；凡本报告写「当前工作区」处，请以 §11 各节的新树数据为准。

**附：一次行号争议的核对结论（教训：行号不能当锚点）**

实现方在复核时给出过另一组行号（`resolve_field` 在 `:214-216`、`:221-223` 是「注释 + `require_scalar`」），与我的两处引用不一致，遂请我以双树侧为准核对。我的核对方法与结果：

| 代码 | 旧快照（我 23:08 快照，由 `git diff` hunk 逐行还原） | 现行树 | 实现方给的数字 |
|---|---|---|---|
| 三处 `resolve_field(...)` | **221 / 222 / 223** | **230–235**（六行） | 214–216 ❌ |
| `require_scalar(instruction_name, …)` | **229-230** | 241-242 | 称在 221-223 ❌ |
| `build_prompt(...)` 调用点 | **242-244** | **254-256** | 242-244 ✅ |
| `"reference": str(reference)` | 245 | 257 | — |
| `samples[: settings.evaluation.max_samples]` | 255 | 267 | — |

- 我的数字不是凭记忆：由我当时产出的 `git diff HEAD`（`.qa4/r4_diff_evaluate_service.txt`，hunk 头 `@@ -200,15 +216,33 @@`）按「新增/上下文行推进新文件行号、删除行不推进」逐行还原，与 §2.7、缺陷表、§七 的引用**互相自洽**（例如 `:255` 正是 P3-4 指出的截断行）。
- 实现方**已接受该表为准**，并说明其数字来自开发期某次 `Read`（其 Bash 不可用，无法做 `git show`/`git diff` 对照），且**不对应我已取证的任何一个快照**（比 23:08 快照早 7 行）。双方均未对「中间态由谁何时造成」作推断。
- **结论与建议**：`build_prompt` 的调用点确实**不该改**也已确认**未改**（现行树 `:254-256` 与旧快照结构一致）——修复落在取值阶段，不在下游补救位置。**教训**：源码行号在活跃编辑期随时失效，**引用位置应优先用函数名 / 唯一表达式等代码锚点**；本轮 README 限制 #9 已由团队改为「以表达式为准」，方向一致。

### 11.5 仍未修的两条（新树实测，均非本轮引入）

```
P3-3（数值参考值按 str() 口径字符串化）
  [output=0.0                    ] reference = '0.0'
  [output=-0.0                   ] reference = '-0.0'
  → 经标点归一化后 '0.0' -> '00'、'-0.0' -> '00'，与预测 '0' 不匹配。0 本身已被正确计数。

P3-2（未被守卫的额外字段仍可写入非法 JSON）
  test_data = [{"instruction":"x","output":"y","meta":NaN,"nested":{"n":Infinity}}]
  status=200   annotations=[(1, 1, 'completed', 'y', 0, 0)]
  raw_data(库内) = ('{"instruction": "x", "output": "y", "meta": NaN, "nested": {"n": Infinity}}',)
  磁盘 datasets\dataset_1.json = '... "meta": NaN, "nested": { "n": Infinity } ...'
  check: 库内 contradictions = 0
```

两条与我原先的定性一致：**既非本轮引入、也不产生自相矛盾状态**，列为可延后登记的 P3。

### 11.6 过程风险（必须记一笔）

1. **验证对象在验证窗口内被改动**，导致任何「验证通过」的结论都自带一个**有效时间窗**。我这个窗口是 23:08 → 23:11，仅 3 分钟；如果我没有做 md5 快照与 `git status` 交叉核对，v2 报告的 211 / 行号 / 文案引文会**静默失效**而不被任何人发现 —— 这正是本项目底线里说的「数字合理、结论错误」的另一种形态（只不过这次错误在报告侧，不在产品侧）。
2. **建议**：交付前的最后一轮验证，请给出一个**冻结窗口**（验证开始时记录全树 md5，期间不允许写入产品文件）；若期间必须改动，则改动方有义务告知复验方重跑，并**重新出具 md5 清单**。本轮我是靠自查发现的，不是被通知的。
3. **我方边界**：整个复验期间我未写入任何产品文件；本轮我新增/写入的只有 `.qa4/` 下的探针与原始输出（被 `.gitignore:155 .qa*/` 忽略）以及本报告 `QA-VERIFY-4.md`。

---

## 附录 A：本轮产出的原始证据文件（均在 `.qa4/`，已被 `.gitignore:155 .qa*/` 忽略）

| 文件 | 内容 |
|---|---|
| `.qa4/v1_collect.txt` / `.qa4/v1_collect_summary.txt` | `--collect-only` 全量 211 与按文件分布 |
| `.qa4/v1_full.txt` | 全量一次跑完的终端输出（`211 passed`，`FULL_EXIT=0`） |
| `.qa4/junit_r4.xml` + `.qa4/v1_junit_summary.py` | junit 权威计数与分布（脚本解析） |
| `.qa4/ab_head.txt` / `.qa4/ab_cur.txt` / `.qa4/r4_ab.py` | 第三轮 vs 第四轮 A/B 全量原始输出与探针源码 |
| `.qa4/ab_order.txt` / `.qa4/r4_ab_order.py` | 报错路径单点 A/B |
| `.qa4/v2v5.txt` / `.qa4/r4_v2v5.py` | V2/V3/V4/V5 主探针（178 条断言，`PASS=178 FAIL=0`） |
| `.qa4/v6_cmp.txt` / `.qa4/r4_v6_cmp.py` | V6 逐字比对（21/21） |
| `.qa4/extra.txt` / `.qa4/r4_extra.py` | `max_samples` 截断复核 + 孤儿 annotation 复核 |
| `.qa4/types.txt` / `.qa4/r4_types.py` | 不可 JSON 表达类型 14/14 拒绝 + dataset 路径截断 |
| `.qa4/head_data_service.py` | `git show HEAD:app/services/data_service.py`（第三轮基线） |
| `.qa4/r4_diff_values.txt` / `.qa4/r4_diff_data_service.txt` / `.qa4/r4_diff_evaluate_service.txt` / `.qa4/r4_diff_tests.txt` | HEAD → 工作区完整源码 diff |

**§十一追加复验（新树）新增的文件：**

| 文件 | 内容 |
|---|---|
| `.qa4/r4_accept.py` / `.qa4/accept.txt` | 6 条验收契约的完整探针与原始输出（`PASS=25 FAIL=0`、`ACCEPT_EXIT=0`），含 §0 的 md5 漂移对照 |
| `.qa4/v2v5_b.txt` | 新树上重跑的 V2–V5 主矩阵（`PASS=178 FAIL=0`）与别名回退的直接观测 |
| `.qa4/junit_r4b.xml` / `.qa4/v1_full_b.txt` / `.qa4/v1_summary_b.txt` / `.qa4/v1_junit_b.txt` | 新树全量测试的 junit 权威计数（`tests="217"`）与按文件分布 |
| `.qa4/_drift.txt` / `.qa4/_lines_cur.txt` / `.qa4/_docs_b.txt` / `.qa4/_qa_report_b.txt` | md5/mtime 漂移记录、现行行号对照、README 与 QA-REPORT 现状、新增测试类原文 |

## 附录 B：第三轮 P1（孤儿 annotation）复核结果

顺手复核（`python .qa4/r4_extra.py` §2），确认未回归：

```
失败导入 status=400 detail="数据导入失败: 字段 'instruction' 的值类型不受支持：…实际为 list。…"
失败后 counts = {'datasets': 0, 'annotations': 0, 'annotation_tasks': 0}
POST /api/data/create -> id=1 total_samples=0
POST /api/annotation/task -> {'id': 1, 'dataset_id': 1, 'total_items': 0, 'completed_items': 0, 'status': 'pending'}
GET  /api/annotation/task/1/progress -> {'task_id': 1, 'total': 0, 'completed': 0, 'pending': 0, 'progress': 0}
最终 counts = {'datasets': 1, 'annotations': 0, 'annotation_tasks': 1}
→ PASS：新数据集标注进度 total=0 / pending=0（无孤儿继承）
```

## 附录 C：本轮未改动产品代码的证明

```
$ git status --short
 M README.md
 M app/core/values.py
 M app/services/data_service.py
 M app/services/evaluate_service.py
 M docs/QA-REPORT.md
 M examples/sentiment_case/TEST-REPORT.md
 M tests/test_evaluation_references.py
 M tests/test_input_validation.py
?? DELIVERY.md
?? examples/sentiment_case/QA-VERIFY-3.md
?? examples/sentiment_case/QA-VERIFY-4.md      ← 本报告（我唯一的产出物）
?? tests/test_scalar_contract.py
```

与验证开始前完全一致（本报告 `QA-VERIFY-4.md` 是验证结束后新增的，除它以外**我没有新增或修改任何文件**）；`data/` 目录未被写入（无新增数据集文件，`.api_token` 时间戳仍是 20:36）。本轮未修改任何产品代码、测试或文档，未覆盖 `QA-VERIFY.md` / `QA-VERIFY-2.md` / `QA-VERIFY-3.md`。

> ⚠️ **注意（v3 补正）**：上面这段 `git status` 是 v1/v2 时期的快照，它只证明「**我**没动产品文件」，**不能**用来证明「产品文件在整个验证窗口内没变过」—— 事实上 `values.py` / `evaluate_service.py` / `tests/test_scalar_contract.py` / `README.md` 在 23:11–23:12 被**其他人**改动过（详见 §11.1 的 md5/mtime 对照）。`git status` 的文件**清单**两轮完全一致，掩盖了这一点；能发现漂移的是 md5 与 mtime，不是 `git status`。这是一条方法论提醒：**文件清单不变 ≠ 文件内容不变**。
