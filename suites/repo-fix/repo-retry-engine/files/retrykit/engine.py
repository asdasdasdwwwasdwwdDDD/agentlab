"""带重试的执行器。"""

import time

FATAL = (TypeError, ValueError)


def run_with_retry(fn, attempts=3, delays=None):
    """最多尝试 attempts 次（attempts >= 1）。

    - 遇到 FATAL 异常立即原样抛出，不重试；
    - 其它异常重试，直到成功或用尽 attempts 次；
    - 用尽后原样抛出最后一次异常（类型与消息不变）。
    """
    last_error = None
    for index in range(attempts + 1):
        try:
            return fn()
        except FATAL:
            raise
        except Exception as error:
            last_error = error
            if delays and index < len(delays):
                time.sleep(delays[index])
    raise RuntimeError('retry failed after %r attempts: %s' % (attempts, last_error))
