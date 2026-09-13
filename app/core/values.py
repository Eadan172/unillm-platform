"""值语义判定：区分「缺失」「falsy 的合法值」「类型非法」。

本模块只放**无依赖的纯函数**，不引入 config / ORM / 框架，便于任何层复用。

存在意义（三条都是本项目真实踩过的坑）：

1. ``or`` 链（``value or ""``、``a or b or ""``）在 Python 里会把 ``0`` / ``0.0``
   / ``False`` 一并吞掉，把「值为零」误判成「没有值」：

   - 导入时 ``output=0`` 被标成 ``pending``，数据集导不出训练数据，而接口对外
     解释是「没有已标注的样本」——报了一个虚假状态；
   - 评测时 ``test_data`` 里 ``output=0`` 的样本被静默剔除，评测跑在一个被悄悄
     改小的测试集上，指标数字看起来完全正常——不报错、数字合理、结论错误。

2. ``has_visible_content`` 只回答「有没有内容」，**不回答「类型合不合法」**。
   若拿它当类型守卫，``[]`` / ``{}`` 会因为 ``str([])`` = ``"[]"`` 非空而被放行，
   ``[]`` 还会被 ``str()`` 成 Python repr 写进指标——所以类型必须另有守卫，
   即 :func:`require_scalar`。

3. ``NaN`` / ``Infinity`` 是 ``float`` 实例，能通过标量类型检查，却是非法 JSON
   数字且无法写入 SQLite（会被存成 NULL）。放行它们会产出
   ``status='completed'`` 但 ``output_text IS NULL`` 的自相矛盾状态。

因此：判断「有没有内容」走 :func:`has_visible_content`；判断「值是不是合法标量」
走 :func:`require_scalar`；取别名键走 :func:`resolve_field`。不要再手写
``or ""`` / ``.strip()`` / ``isinstance`` 组合。
"""

import math
from typing import Any, Tuple

# 零宽 / 不可见字符：``str.strip()`` 不会剥除它们，但肉眼与语义上均为空。
# 若不加处理，``{"instruction": "\u200b"}`` 会被误判为「有内容」而入库。
INVISIBLE_CHARS = "\u200b\u200c\u200d\ufeff\u2060"


def is_missing(value: Any) -> bool:
    """判断值是否为「缺失」。

    只有 ``None`` 算缺失。``0`` / ``0.0`` / ``False`` / ``""`` 都是**存在**的值，
    本函数不负责判断它们「有没有内容」——那是 :func:`has_visible_content` 的事。
    """
    return value is None


def has_visible_content(value: Any) -> bool:
    """判断值是否含「可见」内容。

    视为**无内容**：``None``、``""``、纯空白（``"   "``）、零宽字符、BOM。
    视为**有内容**：``0``、``0.0``、``False``、以及任何 ``str(value)`` 后含
    可见字符的值。

    ``0`` / ``0.0`` / ``False`` 必须返回 ``True``——显式区分 ``None`` 与 falsy 的
    合法值，不要退化成 ``str(value or "")``（``0 or ""`` 会短路成 ``""``）。

    注意：这是**存在性**判定，不是类型守卫。``[]`` / ``{}`` 会返回 ``True``
    （``str([])`` = ``"[]"`` 非空）。要拒绝非标量请用 :func:`require_scalar`。
    """
    if value is None:
        return False
    text = str(value).strip()
    for ch in INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return bool(text.strip())


def resolve_field(
    item, primary: str, alias: str, *, fallback_when_none: bool = False
) -> Tuple[str, Any]:
    """返回 ``(实际使用的键名, 值)``，优先 primary、回退 alias，都没有则为默认空串。

    默认（``fallback_when_none=False``）保留 ``item.get(primary, item.get(alias, ""))``
    的语义：**primary 键存在时即使值为 None 也取 None，不回退 alias**。导入侧用这个
    语义，与历史行为逐字一致（错误文案的一字不变依赖于此）。回显实际键名是为了让校验
    错误能准确指出用户写的到底是哪个字段（写了 ``input`` 就别报 ``context``）。

    ``fallback_when_none=True`` 时，**值为 None 也继续回退** alias。评测侧必须用这一
    档：它的历史实现是 ``x = item.get("output"); if x is None: x = item.get("answer")``，
    即「键缺失 / 值为 None 都回退」。

    为什么这个开关必须存在（真实回归教训）：把两档语义合成一档后，
    ``{"output": None, "answer": "x"}`` 在评测侧的 ``require_scalar`` 之前就被判为
    「没有参考答案」而 ``continue`` —— 单独一条时表现成 400，**混在一批里则让
    ``sample_count`` 从 2 静默降到 1**，HTTP 仍是 200、EM 看起来完全正常。
    这正是本项目底线点名的最坏一类：不报错、数字合理、结论错误。
    """
    if primary in item:
        value = item[primary]
        if not (fallback_when_none and value is None):
            return primary, value
    if alias in item:
        return alias, item[alias]
    return primary, item.get(primary, "")


def coerce_scalar(value: Any) -> Any:
    """把字段值收敛为可安全写入 TEXT 列的标量（**仅限空值与布尔**）。

    - ``None`` -> ``""``（``Annotation.instruction`` 为 ``nullable=False``，
      空值语义明确，属于正常兜底，不算「假成功」）
    - ``bool`` -> ``"true"``/``"false"``（避免被存成 ``'True'``/``'False'``）
    - ``str`` / ``int`` / ``float`` -> 原样返回
    - 其它（``list`` / ``dict`` / ``set`` ...）-> **原样返回，不收敛**

    非标量不在此收敛：早期实现用 ``json.dumps`` 把它们转成字符串后照常入库并返回
    200「成功 N 条」，等于用一个看似正常的返回值掩盖真实的格式错误——属于静默存
    垃圾，与本项目「不造假、不谎报」原则相悖。这类值一律交由
    :func:`require_scalar` 显式拒绝。
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return value
    return value


def require_scalar(field_name: str, value: Any) -> Any:
    """校验字段值为**合法标量**；否则抛 ``ValueError``（路由映射为 400）。

    拒绝两类值：

    1. **非标量**：``list`` / ``dict`` / ``set`` ... —— 无法绑定进 SQLite 列，
       ``str()`` 收敛只会把格式错误变成一条看似成功入库的垃圾样本。
    2. **非有限浮点**：``NaN`` / ``inf`` / ``-inf`` —— 是 ``float`` 实例却非法
       （JSON 规范不允许，只是 ``json.loads`` 与 ``pandas.to_json`` 会产出），
       放行后会被 SQLite 存成 NULL，产出 ``status='completed'`` 但
       ``output_text IS NULL`` 的自相矛盾状态，随后导出报「没有已标注的样本」。

    错误消息点明**哪个字段**、**实际是什么类型/值**，并给出修正方向，避免用户
    看到「类型不对」却不知道该改哪里。
    """
    coerced = coerce_scalar(value)

    if not (isinstance(coerced, (str, int, float, bool)) or coerced is None):
        raise ValueError(
            "字段 '{field}' 的值类型不受支持：内容字段只能是标量"
            "（字符串 / 数字 / 布尔 / 空值），实际为 {actual_type}。"
            "请将该字段改为字符串后再导入（例如把列表拼接为一段文本，"
            "或改用多条记录表达）。".format(
                field=field_name, actual_type=type(coerced).__name__
            )
        )

    if isinstance(coerced, float) and not math.isfinite(coerced):
        raise ValueError(
            "字段 '{field}' 的值不是有效数字：实际为 {literal}（类型 float）。"
            "NaN / Infinity 虽然能被 json.loads 与 pandas.to_json 产出，"
            "但不是合法的 JSON 数字；写入该内容列时会被 SQLite 存成空值，"
            "于是样本对外显示为「已标注」而答案列为空，导出随即报「没有已标注的样本」。"
            "请改用有限数字或字符串。".format(
                field=field_name, literal=repr(coerced)
            )
        )

    return coerced
