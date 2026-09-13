# QA 独立对抗性验证报告 · 第 2 轮（QA-VERIFY-2）

> 验证人：software-qa-engineer-3（独立于代码作者）
> 验证时间：2026-09-13 22:07 ~ 22:20（UTC+8）
> 验证对象：`examples/sentiment_case/TEST-REPORT.md`（**读取时刻 2026-09-13 22:14:45**，该文件 mtime = 22:13:22、size = 30042；会话期间它从 22:04 的 38448B 变为 22:13 的 30042B，请以本报告注明的时刻为准）
> 解释器：`D:/WorkBuddy/.workbuddy/binaries/python/envs/unillm/Scripts/python.exe`（3.13.14）
> Node：`D:/WorkBuddy/.workbuddy/binaries/node/versions/22.22.2-3/node.exe`
>
> **本次未修改任何产品代码**（`app/`、`scripts/`、`tests/`、`examples/sentiment_case/*.py`、`*.md` 均未改动，`git status` 已核对）。
> 我的取证脚本与产物全部放在新建的 `.qa3/` 目录下（未纳入版本控制）。

---

## 〇、结论

# **PASS with issues**

**A1 / A2 / A3 三项改动所声明要实现的行为，全部实测成立**；三项独立核对（129 计数、指标重算、端到端跑通）**全部与报告一致**。上一轮那种「伪造一段平台从未产生的原始输出」的行为，**本轮未再发现**（详见 §五）。

但对抗性测试额外找出 **2 条 P1 级数据残留缺陷**，其中一条会让「空数据集」对外报出并不存在的样本数——直接触及本项目「绝不造假」的底线：

| 编号 | 级别 | 一句话 |
|---|---|---|
| **F-1** | **P1** | A2 拒绝导入后，`annotations` 表残留孤儿行；**下一个新数据集会「继承」这些空壳行**，导致平台对一个 0 样本的数据集报 `pending=3` 并吐出 3 条空白标注卡 |
| **F-2** | **P1** | 内容字段值为 JSON 数组/对象（如 `{"instruction":[1]}`）时返回 **HTTP 500**（不是 400），且**残留孤儿数据集 + 磁盘文件**——正是 A1 想消灭的「静默落库空数据集」 |

---

## 一、A1 — 空文件导入必须 400

### 执行的命令

```bash
"$PY" .qa3/adversarial.py        # TestClient 直打接口，全新 mkdtemp 隔离目录
```

判定口径：`HTTP==400` **且** `GET /api/data/list == []` **且** `annotations` 表行数 == 0。

### 原始输出（节选）

```
  [PASS] A1[0 字节 .jsonl]      :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, 'evaluations': 0} orphans=[]
  [PASS] A1[仅一个换行 .jsonl]  :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, 'evaluations': 0} orphans=[]
  [PASS] A1[仅空白字符 .jsonl]  :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, 'evaluations': 0} orphans=[]
  [PASS] A1[混合空行 .jsonl]    :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, 'evaluations': 0} orphans=[]
  [PASS] A1[0 字节 .json]       :: HTTP=400 detail=数据导入失败: Expecting value: line 1 column 1 (char 0)
  [PASS] A1[空 JSON 数组 .json] :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, ...}
  [PASS] A1[空 JSON 对象 .json] :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, ...}
  [PASS] A1[0 字节 .csv]        :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, ...}
  [PASS] A1[CSV 只有表头]       :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, ...}
  [PASS] A1[CSV 只有表头+换行]  :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 0, ...}
  [**FAIL**] A1[CSV 表头 + 全空行] :: HTTP=400 list=[] counts={'datasets': 0, 'annotations': 1, ...}
                                     orphans=[(1, 1, '', '')]
```

### 判定

- **状态码：11/11 条路径全部 400**。0 字节 / 仅 `\n` / 仅空白 / 混合空行 / 0 字节 json / `[]` / `{}` / 0 字节 csv / 仅表头 csv / 表头+CRLF —— 全部 400，**没有发现任何仍返回 200 的路径**。
- **孤儿数据集：无**。`GET /api/data/list` 在全部 11 条路径后都是 `[]`，`datasets` 表行数恒为 0。作者在 §7.9 1d 写的「上述失败后的数据集列表 → []（无孤儿数据集）」**实测为真**。
- 但 `CSV 表头 + 全空行`（`instruction,input,output\n,,\n`）走的是 **A2 分支**而非 A1：它成功解析出 1 条记录，因此 `len(data)!=0` 不触发 A1，而是被 A2 拦下。该路径 400 正确，**但留下 1 行孤儿 annotation**（见 F-1）。

**A1 结论：行为达标，无 200 漏洞。**

---

## 二、A2 — 记录无可识别内容字段时必须整体拒绝

### 2.1 逐条实测（原始输出）

```
  [PASS] A2[jsonl 行是数字 123]      :: HTTP=400 detail=数据导入失败: 'int' object has no attribute 'get'
  [PASS] A2[jsonl 行是字符串 "abc"]  :: HTTP=400 detail=数据导入失败: 'str' object has no attribute 'get'
  [PASS] A2[jsonl 行是数组 [1,2]]    :: HTTP=400 detail=数据导入失败: 'list' object has no attribute 'get'
  [PASS] A2[jsonl 行是 null]         :: HTTP=400 detail=数据导入失败: 'NoneType' object has no attribute 'get'
  [PASS] A2[jsonl 行是 true]         :: HTTP=400 detail=数据导入失败: 'bool' object has no attribute 'get'
  [PASS] A2[合法记录后跟数组行]      :: HTTP=400 detail=数据导入失败: 'list' object has no attribute 'get'
  [PASS] A2[非法 JSON 行]            :: HTTP=400 detail=数据导入失败: Expecting property name enclosed in double quotes...
```

### 2.2 团队负责人点名要验证的 4 点

**① `{"text": ..., "label": 1}` → 400？错误消息是否回显 `['label', 'text']`？**

```
HTTP = 400
完整 body:
{
  "detail": "数据导入失败: 没有任何记录包含可识别的内容字段：解析成功 2 条，但每条的
            instruction / input / output 均为空，无法作为有效样本入库。平台接受的内容字段为：
            instruction（或 question）、input（或 context）、output（或 answer）。
            第一条记录实际出现的键名为：['label', 'text']。
            请将文本放入 instruction（或 question）、输入放入 input（或 context）、
            答案放入 output（或 answer）。",
  "error_code": "BAD_REQUEST",
  "hint": null
}
是否回显 ['label', 'text'] : True
```

**✅ 属实。** 400，且 `['label', 'text']` 逐字回显；`error_code` 为 `BAD_REQUEST`。

**② 部分可用语义：前两条 `{"text":...}` + 第三条 `{"instruction":"x"}`**

```
  [PASS] A2[前两条空壳 + 第三条可用 → 应 200/total=3] :: HTTP=200
         body={'id': 1, 'name': 'a2-mixed', ..., 'total_samples': 3, ...}
         counts={'datasets': 1, 'annotations': 3, 'evaluations': 0}
    库内 3 行 → [('', '', '', 'pending'), ('', '', '', 'pending'), ('x', '', 'y', 'completed')]
```

**✅ 与设计一致：不报错，`total_samples=3`。** 注意：前两条**确实以「字段全空」的形式入库了**（`instruction/input/output` 全为 `''`，`status=pending`）——这是作者明确声明的「部分可用」语义，不是缺陷，但它意味着「空壳记录」并没有被彻底消灭，只是被限制在「同批中至少有一条可用」的前提下。

**③ 纯空白 `instruction` 是否算可用？**

```
  [PASS] A2[纯空白 instruction]          :: HTTP=400
  [PASS] A2[纯空白 instruction(全角空格)] :: HTTP=400
  [PASS] A2[纯空白 question]             :: HTTP=400
  [PASS] A2别名[只有空 answer 无其它]     :: HTTP=400
```

**✅ 按设计不算可用**，`str.strip()` 判定正确（半角空格 / Tab / `\u3000` 全角空格 / `\n` 均可被剥除）。

**④ CSV 有列名但全空 / CSV 列名为 `text`**

```
  [PASS] A2[CSV 有列名但全空]              :: HTTP=400
  [PASS] A2[CSV 列名为 text]               :: HTTP=400
  [PASS] A2[CSV 全空值 instruction/input/output] :: HTTP=400
```

**✅ 均为 400。**

**⑤ 畸形输入的 5xx 风险（负责人特别点名）**

`item.get` 抛 `AttributeError` 的那一类（行是数组/字符串/数字）——**全部被路由映射为 400，无一 5xx**。✅

**但我在同一个风险面上找到了另一条会 500 的路径**：畸形出现在**字段的「值」**上，而不是行本身上。见 §四 F-2。

### 2.3 A2 结论

**设计声明的行为全部成立**（整批拒绝 + 回显键名 + 部分可用不误伤 + `item.get` 抛错不 5xx）。
**但拒绝过程不干净**（F-1），且同族输入存在 500 路径（F-2）。

---

## 三、A3 — 评测创建时校验 model_id 存在

### 原始输出

```
  [PASS] A3[不存在 model_id=888888 → 404] :: HTTP=404 body={'detail': 'Model 888888 not found', 'error_code': 'NOT_FOUND', 'hint': None} list=[]
  [PASS] A3[model_id=-1 → 404]            :: HTTP=404
  [PASS] A3[model_id=0 → 404]             :: HTTP=404
  [FAIL] A3[model_id=null → 仍可创建]      :: HTTP=422 body={'detail': '请求参数校验失败（请求体.model_id：应为整数）', 'error_code': 'VALIDATION_ERROR', ...}
  [FAIL] A3[model_id 省略 → 仍可创建]      :: HTTP=422 body={'detail': '请求参数校验失败（请求体.model_id：缺失必填项）', ...}
  [PASS] A3[合法 model_id → 200]           :: HTTP=200 model_id=1
  [PASS] A3[model_id='abc' → 4xx 非 5xx]   :: HTTP=422
```

### 判定

- 不存在 / 负数 / 0 的 `model_id` → **404**，且 `GET /api/evaluate/list` 为空（不创建失败记录）。✅
- 合法 `model_id` → **200**。✅
- **`model_id` 为 `null` 或省略 → HTTP 422，不能创建**。这与「不应误伤」的预期**不符**，但**不是本次改动的回归**：`EvaluationCreate.model_id: int` 在改动前（`git show HEAD:app/models/schemas.py`）就是必填字段，未做任何修改。因此这是**既有行为**，本轮改动既未引入也未修复。→ 列为 P3 观察（并说明 A3 代码里 `if request.model_id is not None` 这个分支是**死代码**，永不触发）。

---

## 四、缺陷清单（按级别）

### 🔴 P1 — F-1：A2 拒绝后 `annotations` 表残留孤儿行，并被后续数据集继承

**位置**
- `app/services/data_service.py:64-87`（循环里逐条 `self.db.add(annotation)`，**先 add 后校验**）
- `app/services/data_service.py:92-101`（A2 校验失败抛 `ValueError`，**此时 pending 对象已在 Session 中**）
- `app/services/data_service.py:119-126`（`delete_dataset` 的批量 delete）
- `app/api/routes/data.py:106-111`（路由回滚）
- `app/models/database.py:200-207`（`sessionmaker(..., autoflush=False)`）——**根因**

**根因**：`autoflush=False`，所以 `delete_dataset()` 里的 `query(Annotation).filter(...).delete()` 看不到尚未 flush 的 pending 对象，DELETE 影响 0 行；随后 `delete_dataset` 末尾的 `self.db.commit()` 触发 flush，**把这批 pending 的 Annotation 真正 INSERT 进库**。此时数据集已被删除，于是留下 `dataset_id` 悬空的孤儿行。

**实测取证（.qa3/probe2.py）**

```
P2 — 孤儿 annotations 泄漏：同一进程内取证
上传结果 HTTP=400
GET /api/data/list = []
GET /api/annotation/task/list = []
datasets 表行数   = 0
annotations 表行数 = 3  ← 数据集已被删除，但这些行仍在
    (1, 1, '', '', '', 'pending')
    (2, 1, '', '', '', 'pending')
    (3, 1, '', '', '', 'pending')

P3 — 独立进程直读 SQLite 文件（排除同进程连接缓存的影响）
datasets    : 0
annotations : 3
孤儿(JOIN)  : 3
```

**危害放大（.qa3/probe4.py）** —— SQLite 的 `INTEGER PRIMARY KEY` 会复用 rowid，新数据集拿到同一个 id：

```
步骤 1：{text,label} × 3 上传 → HTTP=400，GET /api/data/list = []
步骤 2：POST /api/data/create 新建数据集 → {'id': 1, 'name': '全新数据集', 'total_samples': 0, ...}
        ↑ 与被删除的那一个 id 相同（rowid 复用）
步骤 3：POST /api/annotation/task（dataset_id=1）
        创建任务 → {'id': 1, 'total_items': 0, ...}
        任务进度 → {'task_id': 1, 'total': 0, 'completed': 0, 'pending': 3, 'progress': 0}
        任务记录数 = 3
           {'id': 1, 'dataset_id': 1, 'instruction': '', 'input_text': '', 'output_text': '', 'status': 'pending', ...}
           {'id': 2, 'dataset_id': 1, 'instruction': '', 'input_text': '', 'output_text': '', 'status': 'pending', ...}
           {'id': 3, 'dataset_id': 1, 'instruction': '', 'input_text': '', 'output_text': '', 'status': 'pending', ...}
```

**后果**：一个刚刚创建、样本数为 0 的数据集，平台对外报 **`pending=3`**（`total=0` 与 `pending=3` 自相矛盾），前端会渲染出 3 张空白标注卡。这正是 A2 想根除的「空壳记录」现象——**只是被推迟到了下一个数据集身上**。这条直接违反「绝不造假：缺失值不伪装成 0 / 不谎报状态」。

**为什么现有回归测试没抓到**：`tests/test_input_validation.py:45,81,88` 只断言 `_dataset_list(client) == []`，即只看 `datasets` 表，**从未检查 `annotations` 表**。

**建议修法（不在我的改动范围，仅供参考）**：在 A2/A1 校验失败时显式 `self.db.rollback()`，或把校验前置到 `self.db.add()` 之前（先整体校验 `data`，再落库）。

---

### 🔴 P1 — F-2：内容字段的「值」为数组/对象时 → HTTP 500 + 孤儿数据集 + 磁盘残留

**位置**
- `app/services/data_service.py:65-67`（`item.get(...)` 取到的值未做类型收敛，直接写入 `Text` 列）
- `app/services/data_service.py:105`（`self.db.commit()` 抛 `sqlalchemy.exc.ProgrammingError`）
- `app/api/routes/data.py:106-111`（`except` 块里访问 `dataset.id` **再次抛异常**）

**实测（.qa3/probe3.py，`raise_server_exceptions=False`，等价于 uvicorn 生产行为）**

```
  !!5xx!!   instruction 为数组 [1]        HTTP=500 datasets=1 annotations=0
            body={"detail": "服务器内部错误", "error_code": "INTERNAL_ERROR", "hint": "请查看服务端日志以获取详细信息"}
  !!5xx!!   instruction 为对象 {}         HTTP=500 datasets=1 annotations=0
  !!5xx!!   instruction 为对象 {a:1}      HTTP=500 datasets=1 annotations=0
  !!5xx!!   input 为数组 [1,2]            HTTP=500 datasets=1 annotations=0
  !!5xx!!   output 为数组                 HTTP=500 datasets=1 annotations=0
  !!5xx!!   instruction 为嵌套数组        HTTP=500 datasets=1 annotations=0
  !!5xx!!   正常记录后跟数组值记录        HTTP=500 datasets=1 annotations=0
  ok        input 为布尔 true             HTTP=200
  ok        input 为 null 但 instruction 有值  HTTP=200
```

**根因（服务端 traceback 关键帧）**

```
sqlite3.ProgrammingError: Error binding parameter 3: type 'list' is not supported
  File ".../app/services/data_service.py", line 105, in import_data_from_file
    self.db.commit()
  File ".../app/api/routes/data.py", line 105, in import_dataset
    count = data_service.import_data_from_file(dataset.id, str(file_path), file_type)
  ...
sqlalchemy.exc.PendingRollbackError: This Session's transaction has been rolled back due to a
  previous exception during flush. ... Original exception was: (sqlite3.ProgrammingError)
  Error binding parameter 3: type 'list' is not supported
  File ".../app/api/routes/data.py", line 109, in import_dataset
    data_service.delete_dataset(dataset.id)     ← dataset.id 取属性触发 refresh，Session 已失效 → 再次抛异常
```

即：**路由的兜底 `except` 自己抛异常**，HTTPException(400) 从未构造出来，异常穿透到 Starlette 的 `ServerErrorMiddleware` → 500。

**残留取证（.qa3/probe5.py）**

```
  上传 HTTP=500  body={'detail': '服务器内部错误', ...}
  GET /api/data/list = [{'id': 1, 'name': '数组字段数据集', ..., 'total_samples': 0, ...}]
  → 残留数据集数 = 1（孤儿：total_samples=0）
  磁盘 datasets 目录内容 = ['bad.jsonl']      ← 上传文件也没被 unlink
  annotations 行数 = 0
  新建数据集 → {'id': 2, ...}
```

**后果**：用户拿到 500，同时库里多出一个 `total_samples=0` 的空数据集（**正是 A1 想消灭的症状**）、磁盘多一个永久文件。`app/api/routes/data.py:107` 的注释「解析失败：回滚数据库记录与落盘文件，不留孤儿数据」在这一类输入下**完全不成立**。

**回归性质说明（如实标注）**：改动前（`git show HEAD:app/api/routes/data.py`）该路由**没有 try/except**，同样的输入同样是 500。所以 **500 本身不是本次改动引入的回归**；但本次改动明确把「失败即回滚、不留孤儿」写进了注解与交付说明（TEST-REPORT §九），而这个承诺在数组/对象取值下并未兑现。现有 `tests/test_upload_safety.py::test_malformed_jsonl_rolls_back_everything` 只覆盖「JSON 语法非法」，未覆盖「JSON 合法但值类型非法」。

---

### 🟡 P3 — 零宽字符 / BOM 字符可冒充「有内容」

```
  零宽空格 instruction \u200b   HTTP=200 annotations=1  rows=[(1, '\u200b', '', '', 'pending')]
  BOM 字符 instruction \ufeff   HTTP=200 annotations=1  rows=[(1, '\ufeff', '', '', 'pending')]
  不换行空格 \xa0 instruction    HTTP=400 annotations=1
```

`str.strip()` 不剥除 `\u200b`（零宽空格）与 `\ufeff`（BOM），这类「肉眼全空」的记录会被判定为可识别内容并入库。属于可接受的边界，但 A2 声称的「没有任何可识别内容字段」在零宽字符面前可被绕过。位置：`app/services/data_service.py:70`。

### 🟡 P3 — CSV 多余列被静默丢弃

```
  CSV 多条多余列  HTTP=200  rows=[(1, 'hi', 'yo', 'ok', 'completed')]
```
`instruction,input,output\nhi,yo,ok,EXTRA1,EXTRA2\n` 中多出的两列进入 `csv.DictReader` 的 `None` 键后被无声丢弃，`raw_data` 里以 `"null": [...]` 形式保留。不报错也不提示。位置：`app/services/data_service.py:46-47`。

### 🟡 P3 — A3 的 `model_id is not None` 是死代码

`app/api/routes/evaluate.py:45` 的分支永远为真（`EvaluationCreate.model_id: int` 是必填），`null`/省略在 Pydantic 层就被 422 拦掉。不影响正确性，但注释「`model_id` 非空且模型不存在 → 404」容易让人误以为该字段可选。

### 🟡 P3 — 报告的延迟区间偏窄（非不实）

§三 声明 `延迟 min = 54.9 ~ 66.9 ms`。我的第 6 次独立运行（真实 uvicorn，端口 8931）实测 `min=67.864 / avg=76.752 / p50=72.836 / p95=91.678 / max=91.678`，`min` 落在此区间之外（`avg 76.752` 恰好落在区间上沿 76.8 内）。报告已在 §三 / §五 显式声明「延迟环境相关、不主张跨环境一致」，故**不算不实**，但把 5 次自测的极值写成区间容易让读者当成稳定范围。

---

## 五、三项独立核对

### ① 套件总数：**129，不是 121** ✅ 独立确认

```bash
"$PY" -m pytest --collect-only -o addopts="" -p no:cacheprovider -q
# → 129 tests collected in 0.16s
```

按文件分布（我独立复算）：

```
     46 tests/test_security_hardening.py
     21 tests/test_closed_loop.py
     20 tests/test_upload_safety.py
     13 tests/test_auth.py
     12 tests/test_metrics.py
      9 tests/test_errors.py
      8 tests/test_input_validation.py      ← 本版新增
     ---
    129 合计
```

`test_input_validation.py` 逐个数：`TestEmptyFileRejected` 3 + `TestUnrecognizedFieldsRejected` 3 + `TestEvaluationCreateValidatesModel` 2 = **8**，与报告一致。

**并且我在作者留下的原始产物里找到了佐证**：`.pytest_tmp/out3.txt`（mtime 22:11:02）内容为

```
........................................................................ [ 55%]
.........................................................                [100%]
...
RESULT collected=129 passed=129 failed=0 errors=0 skipped=0 exit_code=0
```

该文件的点阵（72 + 57 = 129，72/129 = 55.8% → `[ 55%]`）与 TEST-REPORT §7.3 引用的块**逐字一致**；且它晚于 `tests/test_input_validation.py` 的 mtime（22:02:47），因此「129」是真实计数。**文档里那个 121 是过时数字，应以 129 为准。**

> **关于我自己无法跑完整套件**：我尝试跑完整 `pytest` 时被沙箱的批量删除守卫拦截（`SAFE_DELETE_BULK_REJECTED {"count":348,...}`，目标是 `%LOCALAPPDATA%\Temp\pytest-of-adm\garbage-*`），结果是 `121 passed, 8 errors`。这 8 个 ERROR **全部是 `tmp_path` / `sample_jsonl` 夹具的 setup 错误**（`test_auth` 1 + `test_closed_loop` 6 + `test_upload_safety` 1，已用 `grep` 逐一核对与 `tmp_path` 的依赖关系），**没有一个落在 `test_input_validation.py` 上**，属于我这次调用的沙箱副作用而非产品失败。详见 §六。

### ② 案例包评测指标：**全部属实** ✅ 独立重算

方法：走真实接口（导入 → 注册模型 → create → run）拿到服务端返回值；再从**平台自己的 `inference_logs` 表**取出评测过程真实记录的 prompt / response（不是我推测的），用**我自己实现**的多重集字符 F1 重算（未 import `evaluate_service` 的任何指标函数）。

服务端原始返回：

```json
{
  "sample_count": 10, "backend": "mock", "backend_is_real_model": false,
  "exact_match": { "value": 0.0, "correct": 0, "total": 10 },
  "token_f1":    { "value": 0.0132, "unit": "char", "total": 10 },
  "latency":     { "avg_ms": 2.032, "min_ms": 1.81, "max_ms": 2.682, "p50_ms": 1.908, "p95_ms": 2.682, "samples": 10 }
}
results 键集合        : ['backend', 'backend_is_real_model', 'exact_match', 'latency', 'metric_definitions', 'sample_count', 'token_f1']
是否含 perplexity 键  : False
GET /result 的 results 键: [同上]
GET /result 是否含 perplexity: False
```

我的独立逐条重算：

```
  # 1 ref=1 len(pred)= 109 EM=0 f1_multi=0.018182
  # 2 ref=1 len(pred)= 124 EM=0 f1_multi=0.016000
  # 3 ref=1 len(pred)= 118 EM=0 f1_multi=0.016807
  # 4 ref=1 len(pred)= 135 EM=0 f1_multi=0.014706
  # 5 ref=1 len(pred)= 121 EM=0 f1_multi=0.016393
  # 6 ref=0 len(pred)= 131 EM=0 f1_multi=0.000000
  # 7 ref=0 len(pred)= 125 EM=0 f1_multi=0.015873
  # 8 ref=0 len(pred)= 109 EM=0 f1_multi=0.018182
  # 9 ref=0 len(pred)= 125 EM=0 f1_multi=0.000000
  #10 ref=0 len(pred)= 127 EM=0 f1_multi=0.015625

  Exact Match       : 我=0.0000 (0/10)      服务端=0.0 (0/10)
  Char-F1(多重集)   : 我=0.0132             服务端=0.0132
  单条 char_f1 非零值范围 = [0.014706, 0.018182]  共 8 条
  单条 char_f1 为 0 的条数 = 2
```

**逐项裁定**

| 报告声称 | 我的独立结果 | 判定 |
|---|---|---|
| Exact Match `0.0 (0/10)` | `0.0 (0/10)` | ✅ 属实 |
| Char-F1 `0.0132` | `0.0132` | ✅ 属实（逐位一致） |
| `GET /api/evaluate/1/result` 的 `results` **不含 perplexity 键** | 不含 | ✅ 属实 |
| 单条 char_f1 落在 `0.0147~0.0182`，含 2 条 0.0 | `[0.014706, 0.018182]`，2 条 0.0 | ✅ 属实 |
| §7.7 十条逐条值（`0.018182 / 0.016000 / 0.016807 / 0.014706 / 0.016393 / 0 / 0.015873 / 0.018182 / 0 / 0.015625`） | 十条**逐位相同**（6 位小数） | ✅ 属实 |
| §7.7 「第 6、9 条恰为 0.0，其 mock 哈希里不含标签字符」 | 独立验算：归一化输出中不含 `'0'` 的正是 #6、#9 | ✅ 属实（解释也正确） |

**结论：上一版那个自相矛盾的 `0.0317` 确实是假的，本版 `0.0182` 上限是真的。** 我另行用「集合口径」算得 `0.0229`（与服务端不同），说明数值依赖 F1 口径——服务端用的是**多重集（Counter 交）**口径，与其自述「按字符切分计算 F1，逐样本计算后取宏平均」一致，不构成不实。

### ③ 案例包在 A2 收紧后仍能端到端跑通 ✅ 确认

**在全新隔离目录（`.qa3/e2e/`）上进行，工作区 `data/` 未被触碰**（核对方式：`ls -la --time-style=full-iso data/` 全部 mtime ≤ 20:58，早于本次 22:14 的运行；隔离库路径经 `/health` 确认为 `.qa3/e2e/data/unillm.db`）。

```bash
# 启动隔离服务（端口 8931，UNILLM_* 环境变量全部指向 .qa3/e2e）
"$PY" -m uvicorn app.main:app --host 127.0.0.1 --port 8931
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy

"$PY" examples/sentiment_case/run_case.py \
      --base-url http://127.0.0.1:8931 --token qa3-fixed-token-0123456789
# → EXIT CODE = 0
```

关键原始输出：

```
[STEP 1/5] 导入数据集  POST /api/data/import
  · 导入 'sentiment-case-train' → id=1, total_samples=20, source_type=file
  · 导入 'sentiment-case-test' → id=2, total_samples=10, source_type=file

[STEP 2/5] 创建标注任务  POST /api/annotation/task
  · 创建任务 → id=1, name=sentiment-case-annotation, total_items=20, status=pending
  · 任务进度 → total=20, completed=0, pending=0, progress=0.0%
  · 内容核验 'sentiment-case-train': 首条 input 非空 → '房间不大，但收拾得干净，床睡得踏实。', output='1', status='completed'

[STEP 5/5] 运行评测  POST /api/evaluate/create + /{id}/run
  · 运行结果 → status=completed, sample_count=10, backend=mock, backend_is_real_model=False

情感二分类案例 · 指标汇总
  样本数 (sample_count) : 10
  Exact Match        : 0.0  (0/10)
  Char-F1 (token_f1) : 0.0132  (unit=char)
  延迟 min             : 67.864 ms
  延迟 avg             : 76.752 ms
  延迟 p50             : 72.836 ms
  延迟 p95             : 91.678 ms
  延迟 max             : 91.678 ms
  Perplexity         : 未请求 / 无数据

案例执行完成：5 步全通。
```

独立直读隔离库：

```
datasets   : [(1, 'sentiment-case-train', 20), (2, 'sentiment-case-test', 10)]
annotations: 30
  completed: 30
  pending  : 0
  task_id  : 20
空壳(input&output 均空): 0
orphans  : 0
```

**✅ 报告的两点声称全部成立**：STEP1 导入后记录**不再有空壳**（`instruction`/`output` 非空、`status='completed'`、空壳行数 0），中文字段映射后 **`pending=0`**。

`verify_data.py` 亦独立复跑通过：

```bash
"$PY" examples/sentiment_case/verify_data.py    # EXIT CODE = 0
# train: min=18 max=55 avg=34.8 median=34.0 ; test: min=20 max=47 avg=34.1 median=36.5
# 4-gram 总数=947, 重复出现的 4-gram 覆盖数=3, 占比=0.003
# V1 结论: PASS（全部校验通过）
```

---

## 六、未能验证项（如实说明）

1. **完整 `pytest` 套件的干净通过（129 passed / errors=0）** —— 我被沙箱的批量删除守卫拦截，无法自行跑出干净结果。
   - 我的尝试：`pytest -p no:cacheprovider --basetemp=... -o addopts="" -q` → `121 passed, 8 errors in 14.11s`，`SAFE_DELETE_BULK_REJECTED {"count":348,"threshold":50,...}`。
   - 8 个 ERROR 全部是 `tmp_path`/`sample_jsonl` 夹具的 **setup** 错误，与产品代码无关（已逐个核对依赖关系）。
   - **我不再重试，也不绕过沙箱保护**（遵循任务约定）。因此我**只能确认 129 这个收集数**，**不能亲自确认 errors=0**；`errors=0` 由作者留存的 `.pytest_tmp/out3.txt` 佐证，我核对过其内容自洽、时间晚于新增测试文件。
2. **真实模型（vLLM）链路** —— 本机无 GPU、未装 vLLM，`backend=vllm` 路径完全未触及。
3. **Perplexity 真实计算** —— 需求未请求该指标，且缺 torch/transformers，未验证。
4. **浏览器端渲染** —— 无浏览器，前端仅通过 `node scripts/frontend_logic_check.js` 的逻辑层检查（我复跑 13/13 通过），未做真实 DOM 渲染验证。
5. **并发 / 多实例** —— 未做压测。
6. **微调链路 `/api/finetune/*`** —— 未涉及。
7. **Docker 构建** —— 未执行（无 Docker 环境验证）。
8. **`1.864ms` 这个历史延迟值** —— 全仓库检索只在 `TEST-REPORT.md` 出现，无任何留存原始输出可佐证（对比：§三 的 5 轮延迟、§7.5 的 `46.92ms`、§7.8 的根因探针数值**都**能在 `.tmp_report/`、`.tmp_clean/`、`.tmp_verify/` 里找到逐字对应的原始文件）。

---

## 七、我认为作者声明不实或夸大的地方

**先说明方法与自我更正**：我第一次用检索工具搜「46.92」时没搜到留档，一度怀疑 §7.5 是编造。随后发现该工具默认跳过隐藏文件/隐藏目录（`.tmp_*` / `.smoke_out.txt` 都是隐藏路径），改用 `grep -r` 全量重搜后**找到了逐字对应的原始文件**：

```
46.92   -> .tmp_verify/smoke.txt  + TEST-REPORT.md
54.853  -> .tmp_report/console.txt, .tmp_report/report_out.txt + TEST-REPORT.md
72.624  -> .tmp_report/console.txt, .tmp_report/report_out.txt + TEST-REPORT.md
66.949 / 76.839 / 60.729 / 70.267 / 78.345 -> .tmp_clean/clean_out.txt, .tmp_clean/console.txt
57.958 / 71.657 / 64.984 / 72.898 / 81.171 -> .tmp_verify/console.txt, .tmp_verify/verify_out.txt
d378811577f7 -> 我用标准库独立复算 sha1(step4 prompt) 得到完全相同的前 12 位
```

`.tmp_verify/smoke.txt` 中 `[PASS] 延迟为实测值（> 0） -- avg_ms=46.92` 与 §7.5 引用**逐字一致**；`.tmp_report/report_out.txt` 与 §7.1/§7.2 的 `54.853 / 72.624 / 72.018 / 86.002` 及 `GET /result` JSON（含 `created_at 14:12:08.132820`）**逐字一致**。**上述怀疑撤回。**

### 结论：**未发现伪造原始输出的行为。**

相对上一轮被抓住的「凭空写出平台从未返回的 perplexity 块」，本轮的原始输出块（§7.1/§7.2/§7.3/§7.5/§7.8/§7.9）**都能在磁盘上找到留档**，且我对可确定性复算的部分（`prompt_sha1`、十条 char_f1、EM、`verify_data` 全部统计量、`frontend_logic_check` 13/13、`smoke_test` 15/15）**都得到了逐位一致的结果**。

### 但仍有 2 处「夸大/不完整」，须记录在案：

**(1) §7.9 1d 的「（无孤儿数据集）」——字面为真，实质不完整。**
该括号只验证了 `datasets` 表（我确认它为真）。但同一次失败在 `annotations` 表里留下了与解析记录数等量的孤儿行，且会被**下一个数据集继承**，让 0 样本数据集对外报 `pending=3`。§九「行为变化」一栏也只写了「→ 400」，未提及这个副作用。读者据 §7.9 会得出「失败的导入没留下任何东西」的印象，而事实并非如此。**这是本轮最有价值的发现，也是最应补进报告的一条。**

**(2) §一 环境信息「运行数据目录：全新临时目录（仓库内 `.tmp_*`，**用完即删**）」——「用完即删」与事实不符。**
- `未污染 data/ 与 data/_demo/` → **为真**（我用 mtime 核对，`data/` 下所有条目 mtime ≤ 20:58，早于 22:12 的报告现场运行）。
- `用完即删` → **为假**。`ls -a | grep -E "^\.(tmp|pytest|check|smoke|gitinfo)"` 实际输出：
  ```
  .check_out.txt .gitinfo.txt .pytest_cache .pytest_out.txt .pytest_report.xml .pytest_tmp
  .smoke_out.txt .tmp_cap .tmp_clean .tmp_compile.txt .tmp_ptb .tmp_pytest .tmp_pytest_out.txt
  .tmp_report .tmp_run .tmp_verify
  ```
  即十几个目录/文件全部留存，其中 `.tmp_report/case.db` 有 131KB、`.tmp_verify/case.db` 有 106KB，均含案例真实数据。属轻微表述不实，建议改为「用后保留在 `.tmp_*` 下作为原始佐证」。

**(3) 一处数字无留档佐证（轻微）**：§7.5 附注里的 `1.864ms` 全仓库检索无任何原始文件支撑（`2.172ms` 在 `.smoke_out.txt`、`46.92ms` 在 `.tmp_verify/smoke.txt` 都有）。该数字出现在「为说明延迟不稳定」的语境里，不构成自利夸大，但严格按「只写能当场复现的数字」的标准，它不合规。

---

## 八、复核用命令索引

```bash
PY="D:/WorkBuddy/.workbuddy/binaries/python/envs/unillm/Scripts/python.exe"
NODE="D:/WorkBuddy/.workbuddy/binaries/node/versions/22.22.2-3/node.exe"
export PATH="/usr/bin:/bin:/mingw64/bin:/c/Windows/System32:$PATH"
cd "C:/Users/宋艺丹/WorkBuddy/2026-09-13-17-52-04/unillm-platform"

# ① 套件总数
"$PY" -m pytest --collect-only -o addopts="" -p no:cacheprovider -q

# A1/A2/A3 对抗性验证（42 项断言，落两个 mkdtemp 隔离目录）
"$PY" .qa3/adversarial.py       # 汇总：42 项，失败 12 项
                                #   （10 项 = 孤儿 annotations / 孤儿数据集残留；2 项 = model_id
                                #    null/省略返回 422，属既有必填字段行为，非本次回归）
"$PY" .qa3/probe2.py            # 完整错误消息 + 孤儿行取证 + 独立进程直读 SQLite
"$PY" .qa3/probe3.py            # 畸形「值类型」→ HTTP 500 取证（raise_server_exceptions=False）
"$PY" .qa3/probe4.py            # 孤儿行被下一个数据集继承（pending=3）
"$PY" .qa3/probe5.py            # 500 后的孤儿数据集 + 磁盘残留文件

# ② 指标独立重算（不复用 evaluate_service 的私有函数）
"$PY" .qa3/recompute_metrics.py

# ③ 端到端（隔离目录 .qa3/e2e，端口 8931）
"$PY" examples/sentiment_case/verify_data.py
"$PY" examples/sentiment_case/run_case.py --base-url http://127.0.0.1:8931 --token <token>

# 旁证
"$PY" scripts/smoke_test.py --port 8944     # 15/15
"$NODE" scripts/frontend_logic_check.js     # 13/13
```

原始输出留档：`.qa3/`（我的）、`.pytest_tmp/`、`.tmp_report/`、`.tmp_clean/`、`.tmp_verify/`、`.smoke_out.txt`（作者的）。

---

## 九、给作者 / 团队的最小修复建议（不含代码改动，仅定位）

| 缺陷 | 建议位置 |
|---|---|
| F-1 孤儿 annotation | `app/services/data_service.py:92-101` 抛错前 `self.db.rollback()`；或把「可识别内容字段」校验整体前移到 `self.db.add()` 之前 |
| F-2 数组/对象取值 → 500 | `app/api/routes/data.py:106-111`：`except` 内先 `self.db.rollback()` 再访问 `dataset.id`（或直接删 `dataset` 对象）；并对 `instruction/input/output` 做 `str()` 收敛 |
| 测试盲区 | `tests/test_input_validation.py` 增加对 `annotations` 表行数与磁盘残留的断言 |
| P3 零宽字符 | `app/services/data_service.py:70` 如需严格，可加 `\u200b\u200c\u200d\ufeff` 之类的显式剥除 |
