"""指数退避序列。"""


def backoff_delays(attempts, base=0.5, cap=4.0):
    """attempts 次总尝试对应 attempts-1 个重试间隔：base, 2*base, ...（不超过 cap）。"""
    delays = []
    for index in range(attempts):
        delays.append(min(cap, base * 2 ** (index + 1)))
    return delays
