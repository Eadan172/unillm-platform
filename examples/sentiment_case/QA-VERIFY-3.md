# 独立对抗性验证报告 · 第三轮（QA-4）

> 验证人：software-qa-engineer-4（独立 QA，与前几轮作者无重合）
> 验证对象：`unillm-platform` 三处改动
> 验证时间：2026-09-13 22:32 ~ 22:50（UTC+8）
> 脚本与原始输出：`.qa4/probe.py`、`.qa4/probe2.py`、`.qa4/probe3.py`、`.qa4/probe4.py`，
> 输出留档 `.qa4/probe_out.txt`、`.qa4/probe2_out.txt`、`.qa4/probe3_out.txt`、
> `.qa4/probe4_out.txt`、`.qa4/collect.txt`、`.qa4/junit.xml`、`.qa4/pytest_full*.txt`、`.qa4/smoke.txt`
>
> **本报告的立场**：不确认「改动存在」，而是尝试把三处改动**证伪**。所有结论都给命令与原始输出。
>
> **证据可获取性提示**：`.qa4/` 被仓库 `.gitignore` 的 `.qa*/` 规则忽略，**不会随提交进入版本库**，
> 仅存在于本机工作区。若需长期留档，请把 `.qa4/*_out.txt`、`.qa4/junit.xml` 复制到受跟踪目录。
> `TEST-REPORT.md` 的快照 md5 为 `081c3b01160d0e440fd6841fd6a831f4`（复核于 22:41，未变）。

> ### 修订记录 v2（2026-09-13 22:5x）
>
> 作者 software-engineer-3 对 P2 归属与 P3 定性提出异议。我按其指引回到**修复前源码快照**
> （`unillm-platform_源码全文.md`，文件 mtime 19:11，早于本轮修复）逐条复核，**两处采纳、一处部分采纳**：
> 1. **P2-1 定性改为「本次引入」**（原写「既有实现」）。修复前 `resolve_samples` 用的是
>    `reference = item.get("output") or item.get("answer") or ""`（该快照第 2961 行），`[] or … or ""` 短路成 `""`
>    ⇒ 样本被 `continue` **静默丢弃**；修复后样本被**保留**并字符串化为 `"[]"`。**行为确已改变**，作者正确，我原判定有误。
> 2. **P2-2 维持「既有缺陷」**，但补上新旧一致性证据：修复前为
>    `status = "completed" if str(output_text or "").strip() else "pending"`（同快照第 1811 行），
>    `nan` 为 truthy ⇒ 同样 `completed`，**新旧结果一致**，修复只是把判定收拢进 `_has_visible_content`。
> 3. **P3「跨端缺口径」改为「契约差异，非缺陷」**，并**撤回**我原先「让 `AnnotationUpdate.output_text` 接受 int/float」
>    的建议——该建议会主动削弱 `str` 强契约，作者的反驳成立。保留该条为**观察项**（UX 层面：数字标签用户需自行转字符串）。
>
> 另修正我原报告一处不精确表述：`build_prompt` 对**非标量** `instruction` 的 `repr` 渲染**不是本次引入**
> （修复前 `str(item.get("instruction") or item.get("question") or "")` 同样产出 `"[1]"`，同快照第 2981 行）；
> 该处本次改变的只有 `instruction=0`（由被吞掉 → 正确渲染 `"0"`）。

---

## 〇、结论

### **PASS with issues**

| 验证项 | 判定 |
|---|---|
| 改动 1：数值 `0` 不再被判为「没有内容」 | **PASS**（正向 8 例、反向 12 例、边界 4 例全部符合声明；未放行本应被拒的值） |
| 改动 2：非标量内容字段 → 400 且零副作用 | **PASS**（11 种非标量变体全部 400；`datasets`/`annotations`/`annotation_tasks`/磁盘/list 全部干净；失败后新数据集的标注进度 `total=0/pending=0`） |
| 改动 3：评测不静默丢弃参考答案为 `0` 的样本 | **PASS**（`sample_count==4`、`EM={'value':0.5,'correct':2,'total':4}` 精确复现；反向 9 例仍 400；`dataset_id` 路径与内联路径语义一致） |
| 独立核对 1：pytest 套件总数 | **PASS**（`collected=167`，`tests=167 / failures=0 / errors=0 / skipped=0`，退出码 0） |
| 独立核对 2：`TEST-REPORT.md` 是否有不实 | **基本 PASS**：所有可复算数字（EM / Char-F1 逐条 / 哈希 / 计数 / 数据核验）**逐位复现**，未发现新的伪造原始输出；发现 **1 处出处标注错误**（P3）与 **1 处证据块内非原样文字**（P3） |

**未发现 P1。** 发现 2 条 P2：**P2-1（评测侧非标量参考答案被 repr 静默字符串化）属本次改动引入的行为变化**（修复前该样本被静默丢弃）；**P2-2（`NaN` → 落库 NULL）为既有缺陷**，本轮只是暴露它、未改变其行为。另有 6 条 P3，其中 P3-2 经与作者交叉复核后**降级为非缺陷的契约差异观察**（详见 §4.5、§八、修订记录 v2）。

---

## 一、验证环境与方法

| 项 | 值 |
|---|---|
| 解释器 | `D:/WorkBuddy/.workbuddy/binaries/python/envs/unillm/Scripts/python.exe` |
| Python | `3.13.14`（与 `TEST-REPORT.md` §一 一致，`-V` 实测） |
| 隔离方式 | `tempfile.mkdtemp()` 自建目录，**在 import `app` 之前**改写 `settings.database.path` 与 `settings.storage.*`（同 `tests/conftest.py` 做法） |
| 采集方式 | `starlette.testclient.TestClient`（in-process HTTP），另有一次真实 uvicorn 子进程冒烟 |
| 代理 | 采集前 `unset HTTP_PROXY HTTPS_PROXY ... ALL_PROXY all_proxy` |
| 后端 | 评测用 `ScriptedBackend`（脚本化预测）/ `MockBackend`（确定性占位） |

未使用 pytest 跑对抗性用例，原因是沙箱的批量删除守卫会在 pytest 的 `atexit` 阶段拦截临时目录清理（详见 §七、§八）。

---

## 二、改动 1：数值 `0` 不再被判为「没有内容」

### 2.1 证明「改对了」——正向用例

命令：`.qa4/probe.py`（CELL 1）。原始输出：

```
  [int0         ] import=200 ds=1 status=['completed'] instr=['x'](types=['str']) out=['0'](types=['str']) total_samples=1 export=200 exported=[{"instruction": "x", "input": "", "output": "0"}]
  [float0       ] import=200 ds=1 status=['completed'] instr=['x'](types=['str']) out=['0.0'](types=['str']) total_samples=1 export=200 exported=[{"instruction": "x", "input": "", "output": "0.0"}]
  [boolF        ] import=200 ds=1 status=['completed'] instr=['x'](types=['str']) out=['false'](types=['str']) total_samples=1 export=200 exported=[{"instruction": "x", "input": "", "output": "false"}]
  [str0         ] import=200 ds=1 status=['completed'] instr=['x'](types=['str']) out=['0'](types=['str']) total_samples=1 export=200 exported=[{"instruction": "x", "input": "", "output": "0"}]
  [int42        ] import=200 ds=1 status=['completed'] instr=['x'](types=['str']) out=['42'](types=['str']) total_samples=1 export=200 exported=[{"instruction": "x", "input": "", "output": "42"}]
  [instr0       ] import=200 ds=1 status=['pending'] instr=['0'](types=['str']) out=[''](types=['str']) total_samples=1 export=400 exported={... '没有已标注（status=completed 且 output 非空）的样本' ...}
  [instr42      ] import=200 ds=1 status=['pending'] instr=['42'](types=['str']) out=[''](types=['str']) total_samples=1 export=400 exported={... 同上 ...}
  [instr0_out1  ] import=200 ds=1 status=['completed'] instr=['0'](types=['str']) out=['1'](types=['str']) total_samples=1 export=200 exported=[{"instruction": "0", "input": "", "output": "1"}]
```

判定：**PASS**。
- `output=0 / 0.0 / False` 均 `status=completed`、`total_samples=1`、`GET /api/data/{id}/export` → 200 且导出确有该行。
- `{"instruction":0}` 与 `{"instruction":42}` 行为**逐字段一致**（都是 `status=pending`、`total_samples=1`、导出 400），是本次要证明的核心等价性。

### 2.2 边界：`0` / `"0"` / `0.0` 在导出 jsonl 里落成什么

| 用户输入 | 落库 `output_text` | ORM 读出类型 | 导出 jsonl 的 `output` |
|---|---|---|---|
| `0`（int） | `'0'` | `str` | `"0"`（字符串） |
| `"0"`（str） | `'0'` | `str` | `"0"`（字符串） |
| `0.0`（float） | `'0.0'` | `str` | `"0.0"`（字符串） |
| `False`（bool） | `'false'` | `str` | `"false"`（小写） |
| `Infinity` | `'Inf'` | `str` | `"Inf"` |

判定：**类型被静默转换（数字 → 字符串），这是 `Annotation.output_text` 为 TEXT 列 + SQLite TEXT 亲和性导致的既有行为，不是本轮改动引入**。语义基本保留（`0` 与 `0.0` 可区分），但：
- `0` 与 `"0"` 在落库后**不可区分**（都成 `'0'`）——属 P3（见 §六）。
- `False` → `"false"`（小写，`_coerce_scalar` 显式转换），而评测侧 `str(False)` = `"False"`（大写）——两者在 `normalize_text` 里都小写化，故指标不受影响（已实测，见 §4.4）→ P3 观察。
- `Infinity` → `"Inf"`、`-Infinity` → `"-Inf"`：Python 宽松 JSON 字面量被接受且拼写被改写 → P3。

### 2.3 反向：本应被判为「无内容」的值是否**仍然**被拒

命令：`.qa4/probe.py`（CELL 2）。12 个用例**全部** `import=200` + `status=['pending']` + `export=400`：

```
  [None         ] import=200 status=['pending'] total_samples=1 export=400
  [empty        ] import=200 status=['pending'] total_samples=1 export=400
  [space        ] import=200 status=['pending'] total_samples=1 export=400
  [fullwidth    ] import=200 status=['pending'] total_samples=1 export=400    # \u3000 全角空格
  [zwsp         ] import=200 status=['pending'] total_samples=1 export=400    # \u200b
  [bom          ] import=200 status=['pending'] total_samples=1 export=400    # \ufeff
  [zwnj         ] import=200 status=['pending'] total_samples=1 export=400    # \u200c
  [wordjoin     ] import=200 status=['pending'] total_samples=1 export=400    # \u2060
  [mix_ws_zw    ] import=200 status=['pending'] total_samples=1 export=400    # " \u200b \ufeff "
  [missing_key  ] import=200 status=['pending'] total_samples=1 export=400
  [answer_none  ] import=200 status=['pending'] total_samples=1 export=400
  [question_only] import=200 status=['pending'] total_samples=1 export=400
```

判定：**PASS**——`None` / `""` / `"   "` / 全角空格 / 零宽（`\u200b\u200c\u200d\u2060`）/ BOM **仍然**被判为无答案，改动没有「放过」本该被拒的东西。

「整条记录全为不可见字符」应**整体 400**（CELL 3），实测：

```
  [all_zwsp     ] import=400 counts={'datasets': 0, 'annotations': 0, 'tasks': 0} files=[]
      数据导入失败: 没有任何记录包含可识别的内容字段：解析成功 1 条 ... 第一条记录实际出现的键名为：['instruction', 'output']。
  [all_space    ] import=400 counts={'datasets': 0, 'annotations': 0, 'tasks': 0} files=[]
  [all_bom      ] import=400 counts={'datasets': 0, 'annotations': 0, 'tasks': 0} files=[]
  [unknown_keys ] import=400 counts={'datasets': 0, 'annotations': 0, 'tasks': 0} files=[]   # {text,label}
```

判定：**PASS**，且零副作用。

### 2.4 `has_visible_content` 穷举（`app/core/values.py:34`）

```
  has_visible_content(None)  = False   has_visible_content('')      = False
  has_visible_content('   ') = False   has_visible_content('\t\n')  = False
  has_visible_content('0')   = True    has_visible_content(0)       = True
  has_visible_content(0.0)   = True    has_visible_content(-0.0)    = True
  has_visible_content(False) = True    has_visible_content(True)    = True
  has_visible_content(42)    = True    has_visible_content('0.0')   = True
  has_visible_content('\u200b') = False   has_visible_content('\ufeff') = False
  has_visible_content('\u3000') = False   has_visible_content('  \u200b x  ') = True
  has_visible_content([])    = True    has_visible_content({})      = True     # ← 见 P2-1
  has_visible_content(nan)   = True                                            # ← 见 P2-2
```

判定：**有内容判定本身`0`/`False` 正确；但 `[]`/`{}`/`nan` 被判为「有内容」**——这是 P2-1 / P2-2 的共同根因（`app/core/values.py:46` 用 `str(value)`，非标量走 Python `repr`）。在**导入路径**上这不会造成后果（`_require_scalar` 已先拒绝非标量），但在**评测路径**上没有同类守卫（见 §4.5）。

---

## 三、改动 2：非标量内容字段 → 400 且零副作用

### 3.1 非标量变体：有没有仍是 200 / 500 的

命令：`.qa4/probe.py`（CELL 4）。11 种变体（含任务点名的 list / dict / 嵌套 list / list 里含 dict / tuple / set / bytes 等级别）：

```
  [list_int          ] import=400 before={d:0,a:0,t:0} after={d:0,a:0,t:0} files=[] list_count=0
      字段 'instruction' 的值类型不受支持：内容字段只能是标量（字符串 / 数字 / 布尔 / 空值），实际为 list。请将该字段改为字符串后再导入（例如把列表拼接为一段文本，或改用多条记录表达）。
  [dict              ] import=400 ... 实际为 dict。...
  [nested_list       ] import=400 ... 实际为 list。...
  [list_of_dict      ] import=400 ... 实际为 list。...
  [output_list       ] import=400 ... 字段 'output' ... 实际为 list。...
  [input_dict        ] import=400 ... 字段 'input' ... 实际为 dict。...
  [answer_list       ] import=400 ... 字段 'answer' ... 实际为 list。...
  [question_dict     ] import=400 ... 字段 'question' ... 实际为 dict。...
  [context_list      ] import=400 ... 字段 'context' ... 实际为 list。...
  [list_of_list_mixed] import=400 ... 字段 'instruction' ... 实际为 list。...
  [bool_ok           ] import=200 after={d:1,a:1,t:0} files=['c.jsonl','dataset_1.json']
  [null_ok           ] import=200 after={d:1,a:1,t:0} files=['c.jsonl','dataset_1.json']
```

**没有一条是 200 或 500。** 消息均点名字段、实际类型、修正方向。

HTTP 无法表达的 `tuple` / `set` / `bytes` / `complex` / `frozenset`，在服务层直接调用 `DataService._require_scalar()`（`.qa4/probe3.py` CELL L）：

```
  [tuple    ] ValueError: 字段 'output' 的值类型不受支持：... 实际为 tuple。...
  [set      ] ValueError: ... 实际为 set。...
  [bytes    ] ValueError: ... 实际为 bytes。...
  [complex  ] ValueError: ... 实际为 complex。...
  [frozenset] ValueError: ... 实际为 frozenset。...
```

判定：**PASS**。

`null` 兜底未被误伤：`{"instruction":"x","output":None}` → import 200（`output_text=''`、`status=pending`），`{"instruction":"x","output":True}` → import 200（`output_text='true'`、`status=completed`）。

### 3.2 零副作用：真的干净吗（含 `annotations` 表）

命令：`.qa4/probe2.py`（CELL J 全树扫描）+ `.qa4/probe.py`（CELL 5）。失败路径下：

```
  failed import status=400 counts={'datasets': 0, 'annotations': 0, 'tasks': 0} files=[]
  GET /api/data/list → 0 条
  非 .db 文件残留（TMP 全树 rglob）: []
```

判定：**PASS**——`datasets` / `annotations` / `annotation_tasks` 三表均 0，`/api/data/list` 空，`storage.datasets_path` 无残留文件，整个隔离 TMP 树无任何非 .db 残留。

### 3.3 复现前几轮的 P1：孤儿 annotation 是否仍被下一个数据集继承

命令：`.qa4/probe.py`（CELL 5）。为了让 SQLite 复用 rowid（本轮的传染前提），先让失败的导入 `create_dataset` 拿到 `id=1` 再被删，随后 `POST /api/data/create` **确实复用了 id=1**：

```
  失败导入 → status=400 counts={'datasets': 0, 'annotations': 0, 'tasks': 0} files=[]
  POST /api/data/create -> 200 {"id":1, ... "total_samples":0}
  POST /api/annotation/task -> 200 {"id":1,"dataset_id":1,"total_items":0,"completed_items":0}
  GET /api/annotation/task/1/progress -> {'total': 0, 'completed': 0, 'pending': 0, 'progress': 0}
```

第二个场景（先成功导入 1 条 → 再失败导入 → 再新建）：

```
  [pre]  seed import status=200 counts={'datasets':1,'annotations':1,'tasks':0}
  [mid]  bad  import status=400 counts={'datasets':1,'annotations':1,'tasks':0} files=['dataset_1.json','ok.jsonl']
  [post] new dataset id=2  task progress={'total':0,'completed':0,'pending':0,'progress':0}  counts={'datasets':2,'annotations':1,'tasks':1}
```

判定：**PASS**——**P1 已根治**。`annotations` 计数在失败前后不变（只含先前合法的那 1 条），新数据集的标注进度 `total=0/pending=0`，不再出现「0 样本数据集对外报 pending=3」。

### 3.4 部分合法 + 部分非法：是否整体拒绝且零副作用

命令：`.qa4/probe2.py`（CELL D）：

```
  [row2_list    ] import=400 counts={'datasets':0,'annotations':0,'tasks':0} files=[]
  [row2_number  ] import=400 ... 但解析到类型 int。
  [row2_string  ] import=400 ... 但解析到类型 str。
  [row2_null    ] import=400 ... 但解析到类型 NoneType。
  [row2_array   ] import=400 ... 但解析到类型 list。
  [row2_dict_bad] import=400 ... 字段 'output' ... 实际为 dict。
```

判定：**PASS**——第 1 条合法记录**不会**被提前落库（校验前移到 `db.add()` 之前，与 §九.2 的描述一致），全部 400 且零副作用。

### 3.5 其它边界（顺手验）

| 输入 | 结果 | 判定 |
|---|---|---|
| 文件名 `../../../evil.py` | 400「不支持的文件类型 '.py'」、无文件落盘 | PASS（先按 `Path(...).name` + 扩展名拒绝） |
| 文件名 `a b\tc.jsonl` | 200，落盘名被净化为 `a_b_09c.jsonl` | PASS |
| 无扩展名 / `.jsonl`（仅扩展名） | 400 | PASS |
| 单个 JSON 对象作为 `.json`（非数组） | 400，但消息为「文件中存在非对象记录…但解析到类型 **str**」——**原因指向错误**（真实原因是顶层不是数组） | P3 |
| `>100MB`（monkeypatch 把上限缩到 1KB 验证分支） | 413，零副作用 | PASS（分支可达；提示里的 `0MB` 是我改小上限的产物，非产品缺陷） |

---

## 四、改动 3：评测不静默丢弃参考答案为 `0` 的样本

### 4.1 核心用例（任务点名的精确断言）

命令：`.qa4/probe.py`（CELL 6），4 条样本（2 条 `output=0` int + 2 条 `output=1` int），`ScriptedBackend` 预测全部脚本化为 `"0"`：

```
  [mixed 4] status=200
    exact_match={"value": 0.5, "correct": 2, "total": 4}
    sample_count=4
```

判定：**PASS**——`sample_count == 4` 且 `exact_match == {'value':0.5,'correct':2,'total':4}`，与要求逐位一致。

### 4.2 全为 int `0`

```
  [all int0 2] status=200 results={... "exact_match": {"value": 1.0, "correct": 2, "total": 2}}
  [0.0 + '0']  status=200 results={... "exact_match": {"value": 1.0, "correct": 2, "total": 2}}
  [bool False ref] status=200 sample_count=1 EM={"value":0.0,"correct":0,"total":1}
```

判定：**PASS**——全 `0` 不返回 400，`EM=1.0`。
（`False` 那条 `EM=0.0` 是因为预测脚本化成 `"0"`、参考答案为 `"False"`，归一化后 `"false" != "0"`，属正确行为；另测预测写 `"False"` 时 `EM=1.0`，说明大小写差异被 `normalize_text` 抹平。）

### 4.3 反向：真正没有答案的样本仍被跳过

命令：`.qa4/probe.py`（CELL 7）+ `.qa4/probe2.py`。9 个变体全部 `400` 且消息含「没有可用的评测数据」：

```
  [missing     ] status=400 has_msg=True   [None        ] status=400 has_msg=True
  [empty       ] status=400 has_msg=True   [space       ] status=400 has_msg=True
  [fullwidth   ] status=400 has_msg=True   [zwsp        ] status=400 has_msg=True
  [bom         ] status=400 has_msg=True   [answer_none ] status=400 has_msg=True
  [answer_empty] status=400 has_msg=True
```

混合（2 有答案 + 2 无答案）→ `sample_count=2`、`EM={'value':0.5,'correct':1,'total':2}`：

```
  status=200 sample_count=2 em={'value': 0.5, 'correct': 1, 'total': 2}
```

判定：**PASS**。

### 4.4 `dataset_id` 路径 vs 内联路径

`.qa4/probe.py`（CELL 9）/ `.qa4/probe2.py`（CELL E/F）：

```
  [dataset path] status=200 sample_count=2 em={"value":0.5,"correct":1,"total":2}
  [inline path ] status=200 sample_count=2 em={"value":0.5,"correct":1,"total":2}
```

用 `output=0` 的 TEXT 列落库实证：

```
  [ds-zero]  stored output_text='0' type=str   → dataset path sample_count=2 EM=1.0 (2/2)
  [ds-false] stored output_text='false' type=str → dataset path sample_count=1 EM=1.0 (1/1)
```

判定：**PASS**——两条路径语义一致；`TEXT` 列读回的 `'0'` 是 truthy/可见，`or ""` 不会短路（与实现注释一致，已实证）。

### 4.5 两个真实缺口（P2）

#### P2-1：评测侧不校验「参考答案必须是标量」，非标量被 Python `repr` 静默字符串化

`.qa4/probe3.py`（CELL K）直接调用 `resolve_samples`：

```
  output=[]              -> samples=[{"prompt": "...", "reference": "[]"}]
  output=[0, 1]          -> samples=[{"prompt": "...", "reference": "[0, 1]"}]
  output={'a': 1}        -> samples=[{"prompt": "...", "reference": "{'a': 1}"}]        # Python repr，单引号
  output=[[1], {'b': 2}] -> samples=[{"prompt": "...", "reference": "[[1], {'b': 2}]"}]
```

经 HTTP（`.qa4/probe2.py` CELL A）：

```
  [ref_list_empty  ] 评测 status=200     |  同样的值走 /api/data/import → import=400（字段 'output' ... 实际为 list）
  [ref_list        ] 评测 status=200     |  导入 → 400
  [ref_dict        ] 评测 status=200     |  导入 → 400
  [ref_nested      ] 评测 status=200     |  导入 → 400
  [ref_true        ] 评测 status=200     |  导入 → 200（bool 合法）
```

`build_prompt` 同样把非标量 `instruction` 变成 `repr`（**注意：此点非本次引入，见下**）：

```
  instruction=[1]             -> '<|im_start|>user\n[1]\n<|im_end|>\n<|im_start|>assistant\n'
  instruction={'a': 1}        -> "...\n{'a': 1}\n..."
```

- **位置**：`app/services/evaluate_service.py:203-213`（`has_visible_content(raw_reference)` 通过后直接 `str(raw_reference)`）、`app/services/evaluate_service.py:236`（prompt 直接 f-string 内插任意值）；根因在 `app/core/values.py:46`（`str(value)` 是**存在性**判定，不是**类型**判定；`str([]) == "[]"` 非空 ⇒ 放行）。
- **性质（已按作者异议更正）：本次改动引入的行为变化，不是遗留缺陷。** 修复前源码快照（`unillm-platform_源码全文.md:2961`，19:11 时点）为：

  ```python
  reference = item.get("output") or item.get("answer") or ""
  if not str(reference).strip():
      continue  # 没有参考答案的样本无法参与指标计算
  ```

  对 `output=[]`：`[] or None or ""` → `""` → 样本被 `continue` **静默丢弃**。修复后改为显式判 `None` + `has_visible_content`，样本被**保留**、reference 变成 `repr` 字符串。即：

  | | 修复前 | 修复后（当前） |
  |---|---|---|
  | `output=[]` | 样本**静默消失**（`sample_count` 变小） | 样本**保留**，reference = `"[]"` |
  | `output={'a':1}` | 样本**静默消失** | 样本**保留**，reference = `"{'a': 1}"`（Python repr，非合法 JSON） |

  两者都是错的（正解是 400），但**当前症状更隐蔽**：修复前「样本数变少」至少还是一条线索，现在连这条线索都没了，指标会拿着 repr 字符串算出一个看起来正常的数字。因此这条应记为**回归性质**（由「静默丢弃」变为「静默接受垃圾」），责任在本轮改动。
- **级别**：P2（不阻断，不丢样本，但会产出以无意义字符串为基准的指标）。
- **建议**：在 `resolve_samples` 复用 `DataService._require_scalar`（或等价的标量守卫），非标量 → 400；或在文档中显式声明评测 `output` 会被 `str()` 化。
- **`build_prompt` 的从属说明**：非标量 `instruction` 被 `repr` 渲染**不是本次引入**——修复前的 `str(item.get("instruction") or item.get("question") or "")`（同快照 `:2981`）同样产出 `"[1]"`。该处本次唯一的行为变化是 `instruction=0`（修复前被 `or` 吞成 `""`，现在正确渲染 `"0"`）。

#### P2-2：`NaN` 被当作标量接受 → `status=completed` 但 `output_text` 落库为 `NULL`，导入却报 200 成功

Python 宽松 JSON 允许 `NaN` 字面量（`pandas.DataFrame.to_json` 就会这样输出缺失值）。实测（`.qa4` 内联探针）：

```
  [NaN      ] import=200 stored=('completed', None, 'NoneType') export=400 jsonl=None
  [Infinity ] import=200 stored=('completed', 'Inf', 'str')      export=200 jsonl={"instruction": "x", "input": "", "output": "Inf"}
  [-Infinity] import=200 stored=('completed', '-Inf', 'str')     export=200 jsonl={"instruction": "x", "input": "", "output": "-Inf"}
  [1e400    ] import=200 stored=('completed', 'Inf', 'str')      export=200 jsonl={"instruction": "x", "input": "", "output": "Inf"}
```

- **行为**：`output: NaN` → `_coerce_scalar` 原样返回 `float('nan')`（`app/services/data_service.py:73`）→ `has_visible_content(nan)` 因 `str(nan)=='nan'` 返回 `True` → `status` 判为 `completed`（`app/services/data_service.py:186`）→ HTTP **200 / total_samples=1**。但 SQLite 把 `NaN` 持久化为 **NULL**，于是库里出现「`status='completed'` 且 `output_text IS NULL`」的自相矛盾行；随后 `export` 报「没有已标注（status=completed 且 output 非空）的样本」——**与刚才 200/ completed 的成功语义直接冲突**。
- **性质（已按作者异议标明）：既有缺陷，非本次引入。** 修复前源码快照（同文件 `:1811`）为 `status = "completed" if str(output_text or "").strip() else "pending"`；`nan` 在 Python 中为 truthy，`nan or ""` → `nan`，`str(nan)` = `"nan"` ⇒ 同样判 `completed`。**新旧结果完全一致**，本轮只是把判定收拢进 `_has_visible_content`，未改变其行为。本轮修复暴露了它，但没有引入它。
- **级别**：P2（低概率但真实：只要用户上传含 `NaN` 的 JSON 就会踩；平台先报成功、再自打嘴巴）。
- **建议**：`_coerce_scalar` 对 `float` 增加 `math.isfinite` 校验，非有限值走「无内容」或显式 400；或把 `status` 的判定改为基于**落库后的值**而非落库前的 Python 值。
- **关于 `Infinity / -Infinity / 1e400 → 'Inf' / '-Inf'`**：作者称未独立确认并建议标「未验证」。**该三行是我自己探针的原始输出（见上表），非转引，故保留为已观测事实**；按其归属同理（修复前 `inf or ""` → `inf` → `str(inf)` = `"inf"` 可见 ⇒ 同样 `completed`），亦属**既有行为**。此处仅记录「拼写被改写」（`Infinity` → `Inf`），未主张其为回归。

### 4.6 `build_prompt` 行为核对

```
  instruction=0   -> '<|im_start|>user\n0\n<|im_end|>\n<|im_start|>assistant\n'   contains '0'? True
  instruction=hi  -> '...\nhi\n...'
  question 回退   -> '...\nQ?\n...'
  instruction=None + question -> '...\nQ2?\n...'
  instruction=0 + question    -> '...\n0\n...'      # 0 不是 None，不回退 → 正确
  input=0                     -> '...\nhi\n0<|im_end|>\n...'
  empty dict                  -> '...\n\n...'
```

端到端断言（脚本化后端捕获真实 prompt）：

```
  e2e status=200 captured_prompt=["<|im_start|>user\n0\n<|im_end|>\n<|im_start|>assistant\n"]
```

判定：**PASS**——`instruction=0` 在 prompt 里确实渲染出 `"0"`；键缺失/值为 `None` 时才回退到 `question`。

### 4.7 另一处请求体边界

```
  test_data=dict / str / 42        -> 422（"应为列表"）
  test_data 元素非 dict            -> 422（"请求体.test_data.N：应为对象"）   ← 不是静默丢弃
  test_data 缺失                   -> 400「没有可用的评测数据」
  test_data=[] 且评测绑定了 dataset -> 200，**回退到 dataset**，sample_count=1
```

判定：`test_data=[]` 语义歧义 → **P3**（用户显式传空列表，通常期望「无数据 → 400」，实际被当成「未传」而回退到 `dataset_id`；`app/services/evaluate_service.py:181` 用 `if test_data:` 判真假而非 `is not None`）。

---

## 五、交叉一致性：`app/` 下 `or` 链 / falsy 判定的逐个裁定

任务要求：「有没有**其它**地方还在用 `or` 链或 `or ""` 取值、从而可能吞掉 falsy 的合法值」。命令：

```
grep -rn 'or ""' app/ ;  grep -rn "or ''" app/ ;  grep -rn '\.get([^)]*) or ' app/ ;
grep -rn 'or 0\b' app/ ; grep -rnE '= *[A-Za-z_][A-Za-z0-9_.\[\]()\x27"]* or ' app/ ;
grep -rnE 'or (\[\]|\{\})' app/ ; grep -rn ' or ' app/services app/api app/core app/models app/config.py ;
grep -rnE 'if not [a-zA-Z_]' app/services app/api app/core
```

逐个裁定（**判断依据**：该位置是否可能承载「`0`/`False`/空串 是合法业务值」的语义）：

| # | 位置 | 形态 | 裁定 | 依据 |
|---|---|---|---|---|
| 1 | `app/api/routes/data.py:38` | `Path(raw_name or "").name` | **正当兜底** | 文件名不承载 falsy 业务值；随后必判空 → 400 |
| 2 | `app/api/routes/data.py:50` | `str(raw_name or "")` | **正当兜底** | 同上（Content-Disposition 净化） |
| 3 | `app/api/routes/data.py:51` | `name or "dataset"` | **正当兜底** | HTTP 头回退默认名 |
| 4 | `app/core/security.py:87` | `(settings.app.api_token or "").strip()` | **正当兜底** | token 为空 = 未配置 |
| 5 | `app/services/data_service.py:277` | `ann.input_text or ""` | **当前非缺陷** | 读 TEXT 列，`0` 落库即 `'0'`（truthy）；但形态与曾咬人的 bug 同源，列类型一旦改变会复发 |
| 6 | `app/services/evaluate_service.py:190` | `ann.input_text or ""` | **当前非缺陷** | 同上 |
| 7 | `app/services/evaluate_service.py:191` | `ann.output_text or ""` | **当前非缺陷** | `or ""` 发生在 `has_visible_content` 之前，`None`/`""` 都表示无答案，语义等价；已用 `output=0` 数据集实证（`stored='0'`、`sample_count=2`） |
| 8 | `app/services/evaluate_service.py:147` | `(metrics or {}).get("requested", []) or []` | **正当兜底**（1 处 P3） | 空 list/None → `[]`；但用户显式传 `metrics: []` 想「不计算任何指标」时会被 `create_evaluation` 的 `metrics or settings.evaluation.metrics` 覆盖成默认全指标 → P3 |
| 9 | `app/services/evaluate_service.py:78` | `inference_service or InferenceService()` | **正当兜底** | 依赖注入默认值 |
| 10 | `app/services/evaluate_service.py:93` | `metrics or settings.evaluation.metrics` | **正当兜底**（见 #8） | 空 = 未指定 |
| 11 | `app/services/evaluate_service.py:315` | `lora_path or model_path or base_model` | **正当兜底** | 路径回退，空串=无该路径 |
| 12 | `app/api/routes/model.py:73`、`app/services/inference_service.py:135`、`app/services/finetune_service.py:141` | 名称/路径回退 | **正当兜底** | 同上 |
| 13 | `app/services/model_service.py:76` | `config or {}` | **正当兜底** | JSON 配置默认空对象 |
| 14 | `app/core/errors.py:94` | `errors or []` | **正当兜底** | Pydantic 错误列表 |
| 15 | `app/config.py:121` | `yaml.safe_load(f) or {}` | **正当兜底** | 空 YAML |
| 16 | `app/models/database.py:181` | `Path(db_path or settings.database.path)` | **正当兜底** | 路径回退 |
| 17 | `app/api/routes/annotation.py:142` | `if not has_visible_content(update.output_text)` | **正当**，但见 P3 | `AnnotationUpdate.output_text: str` 由 Pydantic 强制，数值 `0` 在入口就 422（已实测），到不了这行 |

**总结论**：`app/` 下**不再存在**「`or` 链吞掉 falsy 合法值」的活跃缺陷（`0` 被判为缺失的那一类已全部收敛）。剩余风险不是 `or` 链，而是：
- 评测路径**缺标量守卫**（P2-1，`str()` + `repr`）；
- `_coerce_scalar` **放行 `NaN`**（P2-2）；
- TEXT 列上的 `or ""`（#5~#7）只是「当前安全」，属**潜在复发点**（P3）。

---

## 六、独立核对 1：pytest 套件总数

命令：

```bash
python -m pytest --collect-only -q -o addopts="" -p no:cacheprovider
python -m pytest -q -p no:cacheprovider --junitxml=.qa4/junit.xml
```

原始输出（`.qa4/collect.txt`）：

```
167 tests collected in 0.26s
```

按文件分布（我对 `.qa4/collect.txt` 独立计数，与团队负责人的 167 逐文件比对）：

| 文件 | 我的计数 | 团队负责人计数 |
|---|---:|---:|
| `test_security_hardening.py` | 46 | 46 |
| `test_input_validation.py` | 35 | 35 |
| `test_closed_loop.py` | 21 | 21 |
| `test_upload_safety.py` | 20 | 20 |
| `test_auth.py` | 13 | 13 |
| `test_metrics.py` | 12 | 12 |
| `test_evaluation_references.py` | 11 | 11 |
| `test_errors.py` | 9 | 9 |
| **合计** | **167** | **167** |

完整跑批（`.qa4/pytest_full3.txt`）：

```
........................................................................ [ 43%]
........................................................................ [ 86%]
.......................                                                  [100%]
```

junit 权威计数（`.qa4/junit.xml`，`pytest_sessionfinish` 阶段落盘，不受沙箱 `atexit` 影响）：

```
<testsuite name="pytest" errors="0" failures="0" skipped="0" tests="167" time="16.617" ...>
```

脚本退出码 `PYTEST_EXIT=0`；`.qa4/junit.xml` 中 `<failure>/<error>/<skipped>` 标签数为 **0**。

**判定：PASS。`collected == passed == 167`，`failed=0 / errors=0 / skipped=0`。**

> 对照：仓库里既有的 `.pytest_report.xml`（21:57 的旧快照）写的是 `tests="121"`，与本轮 167 不符——那是更早时点的产物，不作证据；我以自己 22:36 的 `.qa4/junit.xml` 为准。

---

## 七、独立核对 2：`TEST-REPORT.md` 是否仍有不实

**读取快照**：`examples/sentiment_case/TEST-REPORT.md`
- 读取时刻：**2026-09-13 22:37:07 (+08:00)**
- 文件 mtime：**2026-09-13 22:34:49.636 (+08:00)**（该文件在团队内被并行修改，本报告只对上述快照负责）
- `md5 = 081c3b01160d0e440fd6841fd6a831f4`，699 行

### 7.1 数字复算（全部通过）

| 报告声称 | 我的独立复现 | 判定 |
|---|---|---|
| §7.7 `char_f1` 逐条 `[0.018182, 0.016000, 0.016807, 0.014706, 0.016393, 0.0, 0.015873, 0.018182, 0.0, 0.015625]` | `.qa4/probe4.py` 用真实 HTTP + `build_prompt` + `MockBackend` 复算，**10/10 逐位一致** | ✅ |
| §7.7 `macro = 0.013177 → 0.0132`、非零 8 条、区间 `[0.014706, 0.018182]` | 复算 `macro=0.013177`、非零 8 条、区间一致 | ✅ |
| §三/§7.2 `sample_count=10`、`EM=0.0 (0/10)`、`token_f1=0.0132 (char, total 10)` | 端到端复现，逐位一致；`results` 中**确无 `perplexity` 键** | ✅ |
| §7.1 第 1 条 `prompt_sha1=d378811577f7` | 用 `run_case.py` 的 prompt 构造式独立计算 sha1[:12] = **d378811577f7** | ✅ |
| §三 延迟表 run#1/2/3 | 与 `.tmp_cap/probe.json` 的 `evaluations[0..2]` 逐字段一致 | ✅ |
| §7.2 `GET /api/evaluate/3/result` 原样 JSON（含 `created_at 14:19:21.097161`、`completed_at 14:19:22.017525`） | 与 `.tmp_cap/probe.json.detail_result` **逐字段一致** | ✅ |
| §7.4 前端逻辑 `13/13` | `node scripts/frontend_logic_check.js` → `结果: 13/13 passed` | ✅ |
| §7.6 `verify_data.py` 全部 PASS（train 20 / test 10 / unlabeled 10 / 10:10 / 5:5 / 逐行一致 / 4-gram 0.003 / avg 34.8、34.1） | 逐行比对本机实际输出，**完全一致** | ✅ |
| §7.5 冒烟 `15/15` | 真实 uvicorn 子进程复跑 → `结果: 15/15 项通过`，退出码 0 | ✅（但延迟数字见 7.2-b） |
| §7.9 1f `model_id=888888 → 404 "Model 888888 not found"` | 实测 404、消息逐字一致 | ✅ |
| §7.10「修复后」F1/F2/F3/F4/F5 各项 | 实测一致（`[1]`→400、`{a:1}`→400、`\u200b`→400、`\ufeff`→400、非对象行→400、合法→200、新数据集进度 `total=0/pending=0`） | ✅ |
| §一 Python `3.13.14` | `python -V` → `Python 3.13.14` | ✅ |
| §b 三条挑战样本标签 `1/0/0` | 在 `test.jsonl` 中逐条命中，标签一致 | ✅ |

**结论：报告的核心数字全部可当场复算，未发现新的伪造原始输出**（前几轮被抓到的伪造 perplexity 块、自相矛盾 0.0317、"修复后→200" 均已不在本版）。

### 7.2 发现的问题（无一项构成「不实数字」，均为标注/措辞级）

- **P3-a（出处标注错误）**：§二 开篇写「以下来自 **run #1** 运行，raw 见 §七.1、§七.2」，但 §二 STEP5 内嵌的 `results`（`avg_ms 75.13 / min 63.666 / p50 75.122 / p95 83.22`）**是 run #3（`eval_id=3`）的数据**，与 §七.1 的 run #1（`70.907 / 79.744 / 78.876 / 87.282`）不同。数字本身真实（来自真实 run #3，可对到 `.tmp_cap/probe.json.detail_result`），但「来自 run #1」的表述与内嵌数据不符。建议改为「run #3」或统一取同一轮。
- **P3-b（证据块内非原样文字）**：§7.10「**修复后**（同一组输入，重跑）」的代码块里写 `字段 'instruction' 的值类型不受支持：只能标量……实际为 list`。平台实际消息是 `字段 'instruction' 的值类型不受支持：内容字段只能是标量（字符串 / 数字 / 布尔 / 空值），实际为 list。请将该字段改为字符串后再导入（...）`。虽用 `……` 标了省略，但块被标注为「原始证据」，措辞被改写。建议原样粘贴或明确标「摘录」。
- **P3-c（口径未说明）**：§b 挑战样本表里的「mock 输出」列取自 **STEP4 批量推理**（prompt 为 `请判断下面这条酒店评论是好评还是差评…`），而 §STEP5 的指标来自**第二次后端调用**（`run_case.py` 传的 `test_data` 只有 `input/output`，`build_prompt` 生成的 prompt **不含**那句指令）。两者 mock 输出不同（实测：评测 prompt 的 `prompt_sha1=8b64be2b633b`，STEP4 的为 `d378811577f7`）。报告未说明「指标并非由 STEP4 的那批预测产出」。结论（EM=0 全错）仍成立，但读者可能误以为 STEP4 的预测就是被打分的那批。建议补一句口径说明。
- **观察（非缺陷）**：§7.5 的 `avg_ms=3.272` 我在 22:4x 复跑得到 `avg_ms=2.504`。原始留档 `.tmp_cap/smoke.txt` 确实含 `3.272`，且报告已显式声明该量「环境相关、可跨量级漂移」——**不算不实**，只是不可在另一时刻复现同一个数。
- **观察（无法归属）**：§一 声明 `data/` 与 `data/_demo/` 「全程未被触碰（以 mtime 核对）」。读取时刻实测 `data/_demo/demo.db` mtime = `22:36:00`、`data/_demo/datasets` = `22:35:58`，**晚于**报告 mtime（22:34:49）。这不代表报告在其自身运行窗口（22:14~22:19）内的说法为假（很可能由并行队友的活动造成，且 `data/unillm.db` 根本不存在，说明主库确未被启动流程落盘），但**该声明在当前工作区已不再成立**，建议补充「快照时点」限定。

---

## 八、缺陷清单

### P1（阻断）—— 无

### P2（应修）

| 编号 | 位置 | 现象 | 证据 | 性质 |
|---|---|---|---|---|
| **P2-1** | `app/services/evaluate_service.py:203-213`（`str(raw_reference)`）、`:236`（prompt 内插）；根因 `app/core/values.py:46`（`str(value)` 是存在性判定而非类型判定） | 评测 `test_data` 的参考答案若为 list / dict / 嵌套结构，**静默通过**并由 `str()` 变成 `"[]"`、`"{'a': 1}"`（Python repr，非合法 JSON）后参与指标计算，返回 200。同一份数据走 `/api/data/import` 是 400。 | `.qa4/probe3_out.txt` CELL K；`.qa4/probe2_out.txt` CELL A；新旧对照见 §4.5 | **本次改动引入的行为变化（回归性质）**：修复前 `output=[]` 被 `continue` **静默丢弃**（样本数变小，尚有线索）；修复后样本被**保留**并 repr 字符串化（线索消失）。正解是 400 |
| **P2-2** | `app/services/data_service.py:73`（`_coerce_scalar` 放行任意 `int/float`）+ `:186`（`status` 基于落库前的 Python 值判定） | `{"instruction":"x","output":NaN}`（`pandas.to_json` 会产出）→ **HTTP 200、total_samples=1、`status=completed`**，但 SQLite 把 NaN 存为 **NULL**，库内出现 `status='completed' AND output_text IS NULL`；随后 `export` 报「没有已标注的样本」，与刚返回的成功语义冲突。`Infinity/-Infinity/1e400` → 被存成 `'Inf'`/`'-Inf'`（拼写被改写）。 | 本报告 §4.5 内联探针原始输出；新旧一致性证据（`源码全文.md:1811`）见 §4.5 | **既有缺陷，非本次引入**：修复前 `str(output_text or "").strip()` 对 `nan` 同样判 `completed`，新旧结果一致 |

### P3（观察）

| 编号 | 位置/对象 | 现象 |
|---|---|---|
| P3-1 | `app/services/evaluate_service.py:181` | `if test_data:` 用真假判定而非 `is not None`；显式传 `test_data=[]` 时被当作「未传」而**回退到 `dataset_id`**（实测 200 且 sample_count=1），与用户「传空 = 无数据」的直觉不符 |
| P3-2 | `app/models/schemas.py:63` + `app/api/routes/annotation.py:142` | 数值 `0 / 0.0 / false` 作为 `output_text` 在入口即 **422「应为字符串」**（已实测；代码注释中「Pydantic 会 422」的声明**属实**）。**已按作者异议更正定性：这不是「口径不一致」，而是三处契约不同导致的必然差异，`422` 是正确行为，不应修改。** 判据：`AnnotationUpdate.output_text: str` 是裸 `str` 强契约 ⇒ 数字在契约外 ⇒ 422 正确；`test_data: Optional[List[dict]]` 与导入的 JSON 值不受类型约束 ⇒ 数字在契约内 ⇒ 接受正确。**我原报告「建议让 `output_text` 接受 int/float」的建议已撤回**（那会主动削弱类型契约）。仅保留为 **UX 观察**：情感案例的 0/1 标签若以数字提交标注会被拒，应由前端/文档明确「标注答案提交字符串」 |
| P3-3 | `app/services/data_service.py:277`、`app/services/evaluate_service.py:190-191` | TEXT 列上的 `ann.x or ""` 当前安全（`'0'` 为 truthy），但形态与曾咬人的 fake-missing 同源，列类型变化即复发 |
| P3-4 | `app/services/evaluate_service.py:93` | `metrics or settings.evaluation.metrics`：显式传 `metrics: []`（想不算任何指标）会被默认全指标覆盖 |
| P3-5 | 导出 jsonl 的 `output` | 数值 `0` / `0.0` / `False` 落库后变为字符串 `"0"` / `"0.0"` / `"false"`（`False` 被 `_coerce_scalar` 转成小写，评测侧 `str(False)` 是 `"False"`）；同语义值经不同端点得到不同拼写。指标因 `normalize_text` 小写化而不受影响 |
| P3-6 | `app/services/data_service.py:159-166` | 顶层为**单个 JSON 对象**（非数组）的 `.json` 文件 → 400，但消息为「文件中存在非对象记录…但解析到类型 **str**」，原因指向错误（真实原因是顶层不是数组）。不影响安全性与零副作用 |

---

## 九、未能验证项（环境限制）

1. **无 GPU / 未装 vLLM**：`backend=vllm` 真实推理路径、`compute_perplexity` 的真实分支（需 torch+transformers）均未触及；本报告所有评测数字都来自 `mock` / `scripted` 后端。**不对此类路径做任何结论。**
2. **无浏览器**：前端只跑了 `node scripts/frontend_logic_check.js`（逻辑层 13/13），未做任何真实 DOM/浏览器渲染验证。
3. **无 Docker**：`Dockerfile` / `docker-compose.yml` / `start.sh` 未构建、未运行。
4. **沙箱批量删除守卫干扰 pytest 收尾**：直接 `python -m pytest -q` 时，pytest 的 `atexit` 会清理 `%LOCALAPPDATA%\Temp\pytest-of-*\garbage-*`（本次触发样本 348 个文件 > 阈值 50），被沙箱拦截并抛 `SystemExit: 1`，**终端汇总行（`167 passed in ...`）因此不会打印**（`.pytest_out.txt` 有完整 traceback，栈顶为 `sitecustomize.py:826 _exit_bulk_guard_control`）。我改用：
   - `--junitxml`（由 `pytest_sessionfinish` 在 `atexit` 之前落盘）取得权威计数 `tests=167/failures=0/errors=0/skipped=0`；
   - 点阵行独立计数 72+72+23 = 167，全程无 `E`/`F`；
   - 进程退出码 `0`。
   依此判定「`collected == passed`」可靠；但**我无法提供一条带 `N passed` 终端汇总行的原始输出**。
5. **未修改产品代码、未回退 git 版本**：`TEST-REPORT.md` §7.10 的「**修复前**」证据（500 + 孤儿数据集 + 磁盘残留）属于历史状态，我**没有**改用未修复版本复现，因此**未独立印证**该「修复前」描述；我印证的是「修复后」的全部行为。
   - 附带说明：为裁定 P2 归属，我用的是工作区内的**修复前源码快照** `unillm-platform_源码全文.md`（文件 mtime 19:11，早于本轮修复；`evaluate_service.py` 段见 `:2940-2986`，`data_service.py` 段见 `:1811`）。该快照**不在 git 历史里**（三个提交中最早的是未重构版本、最新的是已修复版本，中间的「已重构未修复」状态只存在于工作区），因此其「修复前基线」地位由**该快照 + 作者本人的独立复核**两方互证，而非单一来源。若需更强证据，建议把该时点的 `app/services/evaluate_service.py` 单独归档。
6. **`>100MB` 真实 413**：为免生成 100MB 载荷，我用 monkeypatch 把上限临时缩到 1KB，仅验证 413 **分支可达且零副作用**；未验证真实 100MB 边界。（提示语里的 `0MB` 是缩限产物，非产品缺陷。）
7. **未验证并发/多实例**：全部为单进程串行。
8. **`TEST-REPORT.md` 是并行修改中的文件**：本报告只对其 22:37:07 的 md5 快照负责，后续修改可能使 §7.2/§7.3 的结论失效。
9. **`tuple/set/bytes` 只能服务层验证**：JSON 无法表达这些类型，HTTP 层不可达，故仅在 `_require_scalar` 单元层验证（均为 ValueError → 400 语义）。
10. **`NaN` 通过评测请求体（而非文件）**：标准 HTTP 客户端（httpx 的 `allow_nan=False`）**无法发送** `NaN`，我用裸 body 绕过才复现 200；该子路径在真实客户端下不可达，仅记录。

---

## 十、我认为作者声明不实或夸大的地方

**没有发现「数字造假」或「伪造原始输出」。** 本轮所有可复算的数字（EM、Char-F1 逐条、宏平均、prompt 哈希、pytest 计数、数据核验统计、模型不存在 404）均**逐位复现**，且报告引用的留档文件（`.tmp_cap/*`）确实存在并与正文一致。

需要指出的是**标注/措辞层面**的 3 处（均已在 §7.2 给出证据，不构成数字不实）：

1. **§二 的出处标注错误**：正文声明 STEP5 数据来自「run #1」，实际是 run #3（`eval_id=3`）的数据；run #1 的数据在 §七.1 里另有其值。数字为真、来源标注不符。
2. **§7.10「修复后」证据块内包含被改写的错误消息**（`只能标量……` vs 实际的 `内容字段只能是标量（字符串 / 数字 / 布尔 / 空值）`），块却被标为原始证据。虽有 `……` 提示省略，仍建议原样粘贴。
3. **§b 挑战样本表未说明「指标不由 STEP4 的预测产出」**：STEP4 的 mock 输出与 STEP5 评测内部再调用后端得到的输出不是同一批（prompt 不同，实测哈希 `d378811577f7` vs `8b64be2b633b`），报告未做口径说明，容易让读者把两者等同。结论本身（全错、EM=0）不受影响。

另有一句**在当前工作区已不再成立**的声明：§一「`data/` 与 `data/_demo/` 全程未被触碰（以 mtime 核对）」——读取时刻 `data/_demo/demo.db` 的 mtime（22:36:00）晚于报告 mtime（22:34:49）。鉴于 `data/unillm.db` 并不存在、且并行队友也在跑，我倾向于认为这是**并行活动所致、非报告作者说谎**，但该句缺少「快照时点」限定，建议补上。

除此之外，**报告对 mock 后端能力的自我限制、对延迟不稳定性的反复声明、对未验证项的显式列举，均属克制且准确**；v1 的 perplexity 伪造、v3 的「无孤儿数据集」过度声明，在本版中确实已被更正并留痕。

---

## 十一、建议的修复优先级

1. **P2-1**：在 `EvaluateService.resolve_samples` 复用标量守卫（`DataService._require_scalar` 或等价物），非标量参考答案 → 400 且点名字段/类型/修正方向。同时消除 `app/core/values.py:46` 对非标量走 `repr` 的副作用（或至少在文档中声明评测 `output` 会被 `str()` 化）。
2. **P2-2**：`_coerce_scalar` 对 `float` 增加 `math.isfinite` 校验（非有限值 → 400 或按「无内容」处理）；或把 `status` 判定改为基于落库后读回的值。
3. **P3-1**：`if test_data:` → `if test_data is not None:`，让显式空列表按「无样本 → 400」处理。
4. **P3-2（已按作者异议降级为观察，不建议改代码）**：**不建议**放宽 `AnnotationUpdate.output_text` 的类型——`422` 对 `str` 强契约而言是正确响应，放宽反而削弱契约。只需在控制台/文档/前端明确「标注答案请提交字符串」（已有前端提示则无需改动）。
5. **P3-3~P3-6**：按 §八 逐条小额修正；`TEST-REPORT.md` 补 §7.2 的 3 处标注（run 编号、原样消息、STEP4/STEP5 口径）与 §一 的快照时点限定。

> **归属口径小结**（供 triage 用）：**P2-1 是本次改动引入的行为变化**（由「静默丢弃」变为「静默接受垃圾」）；**P2-2 是既有缺陷**，本轮只是把它暴露并收拢了判定路径，新旧行为一致；**P3-2 不是缺陷**，是契约差异的正确表现。

---

*本报告只读验证，未修改任何产品代码，未覆盖 `QA-VERIFY.md` / `QA-VERIFY-2.md`。所有中间产物集中存放于 `.qa4/`。*
