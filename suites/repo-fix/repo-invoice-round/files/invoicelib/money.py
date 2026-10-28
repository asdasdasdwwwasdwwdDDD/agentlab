"""金额与整数分之间的转换。"""


def to_cents(amount):
    """把金额（字符串，例如 '12.34'）转换为整数分。"""
    return int(round(float(amount) * 100))


def format_cents(cents):
    """把整数分格式化成两位小数字符串。"""
    if not isinstance(cents, int) or isinstance(cents, bool):
        raise TypeError('cents 必须是整数')
    sign = '-' if cents < 0 else ''
    value = abs(cents)
    return sign + str(value // 100) + '.' + str(value % 100).zfill(2)
