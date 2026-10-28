import importlib
import json
import sys


def _import(ctx, name):
    root = str(ctx.workspace)
    for module_name in list(sys.modules):
        if module_name == name or module_name.startswith(name + '.'):
            del sys.modules[module_name]
    if root not in sys.path:
        sys.path.insert(0, root)
    module = importlib.import_module(name)
    return module


def _load_api(ctx, package):
    _import(ctx, package)
    return importlib.import_module(package)


def check_attempt_cap(ctx):
    try:
        api = _load_api(ctx, 'retrykit')
    except Exception as exc:
        return False, '无法导入 retrykit: %r' % (exc,)
    calls = {'n': 0}

    def always_fails():
        calls['n'] += 1
        raise OSError('disk full')

    problems = []
    try:
        api.run_with_retry(always_fails, attempts=3)
        problems.append('attempts=3 用尽后没有抛异常')
    except OSError as error:
        if calls['n'] != 3:
            problems.append('attempts=3 实际调用 %d 次，期望 3 次' % calls['n'])
        if str(error) != 'disk full':
            problems.append('原始异常消息丢失: %r' % (str(error),))
    except Exception as error:
        problems.append('抛出了 %s，期望原始 OSError: %r' % (type(error).__name__, error))
    calls['n'] = 0
    try:
        api.run_with_retry(always_fails, attempts=1)
    except OSError:
        if calls['n'] != 1:
            problems.append('attempts=1 实际调用 %d 次，期望 1 次' % calls['n'])
    else:
        problems.append('attempts=1 用尽后没有抛异常')
    return (not problems), '; '.join(problems) or '总尝试次数与原始异常传播正确'


def check_fatal_and_success(ctx):
    try:
        api = _load_api(ctx, 'retrykit')
    except Exception as exc:
        return False, '无法导入 retrykit: %r' % (exc,)
    problems = []
    calls = {'n': 0}

    def fatal():
        calls['n'] += 1
        raise TypeError('bad argument')

    try:
        api.run_with_retry(fatal, attempts=3)
    except TypeError as error:
        if calls['n'] != 1:
            problems.append('FATAL 异常应只调用 1 次，实际 %d 次' % calls['n'])
        if str(error) != 'bad argument':
            problems.append('FATAL 异常消息被改动: %r' % (str(error),))
    except Exception as error:
        problems.append('FATAL 异常被转换成 %s: %r' % (type(error).__name__, error))
    else:
        problems.append('FATAL 异常没有抛出')

    calls['n'] = 0

    def succeeds_on_second():
        calls['n'] += 1
        if calls['n'] < 2:
            raise OSError('temporary')
        return 'done'

    result = api.run_with_retry(succeeds_on_second, attempts=2)
    if result != 'done' or calls['n'] != 2:
        problems.append('第二次成功时返回 %r，调用 %d 次' % (result, calls['n']))
    return (not problems), '; '.join(problems) or 'FATAL 直抛与成功路径正确'


def check_backoff_sequence(ctx):
    try:
        api = _load_api(ctx, 'retrykit')
    except Exception as exc:
        return False, '无法导入 retrykit: %r' % (exc,)
    problems = []
    cases = [
        ((4,), [0.5, 1.0, 2.0]),
        ((1,), []),
        ((0,), []),
        ((6,), [0.5, 1.0, 2.0, 4.0, 4.0]),
    ]
    for args, expected in cases:
        try:
            got = api.backoff_delays(*args)
        except Exception as exc:
            problems.append('backoff_delays%r 抛异常 %r' % (args, exc))
            continue
        if got != expected:
            problems.append('backoff_delays%r = %r，期望 %r' % (args, got, expected))
    got = api.backoff_delays(6, base=0.5, cap=1.5)
    if got != [0.5, 1.0, 1.5, 1.5, 1.5]:
        problems.append('带 cap 的退避序列 = %r' % (got,))
    return (not problems), '; '.join(problems) or '退避序列长度与数值正确'


def check_summary_order(ctx):
    try:
        api = _load_api(ctx, 'retrykit')
    except Exception as exc:
        return False, '无法导入 retrykit: %r' % (exc,)
    records = [
        {'attempt': 3, 'ok': True, 'duration_ms': 5},
        {'attempt': 1, 'ok': True, 'duration_ms': 900},
        {'attempt': 2, 'ok': False, 'duration_ms': 10},
    ]
    try:
        summary = api.summarize_attempts(records)
    except Exception as exc:
        return False, 'summarize_attempts 抛异常: %r' % (exc,)
    problems = []
    if [item.get('attempt') for item in summary] != [1, 2, 3]:
        problems.append('未按 attempt 升序排列: %r' % ([item.get('attempt') for item in summary],))
    if [item.get('index') for item in summary] != [1, 2, 3]:
        problems.append('index 不是 1..n: %r' % ([item.get('index') for item in summary],))
    if records[0].get('index') is not None or len(records[0]) != 3:
        problems.append('入参 records 被原地修改')
    return (not problems), '; '.join(problems) or '尝试记录按 attempt 升序且不修改入参'
