"""值语义判定：区分「缺失」与「falsy 的合法值」。

本模块只放**无依赖的纯函数**，不引入 config / ORM / 框架，便于任何层复用。

存在意义：``or`` 链（``value or ""``、``a or b or ""``）在 Python 里会把
``0`` / ``0.0`` / ``False`` 一并吞掉，把「值为零」误判成「没有值」。本项目
已因此产出过真实缺陷：

- 导入时 ``output=0`` 被标成 ``pending``，数据集导不出训练数据，而接口对外
  解释是「没有已标注的样本」——报了一个虚假状态；
- 评测时 ``test_data`` 里 ``output=0`` 的样本被静默剔除，评测跑在一个被悄悄
  改小的测试集上，指标数字看起来完全正常——不报错、数字合理、结论错误。

因此凡是需要判断「有没有内容」，一律走 :func:`has_visible_content`，不要再手写
``or ""`` / ``.strip()`` 组合。判断「值是否为缺失」走 :func:`is_missing`。
"""

from typing import Any

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
    """
    if value is None:
        return False
    text = str(value).strip()
    for ch in INVISIBLE_CHARS:
        text = text.replace(ch, "")
    return bool(text.strip())
