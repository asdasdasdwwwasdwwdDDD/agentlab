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


def check_keep_count_and_order(ctx):
    try:
        api = _load_api(ctx, 'rotator')
    except Exception as exc:
        return False, '无法导入 rotator: %r' % (exc,)
    entries = [api.Entry('a.log', 10, 100), api.Entry('b.log', 20, 100), api.Entry('c.log', 30, 100)]
    problems = []
    pruned, kept = api.plan_prune(entries, 2)
    if [entry.path for entry in kept] != ['b.log', 'c.log']:
        problems.append('keep=2 的 kept = %r' % ([entry.path for entry in kept],))
    if [entry.path for entry in pruned] != ['a.log']:
        problems.append('keep=2 的 pruned = %r' % ([entry.path for entry in pruned],))
    pruned, kept = api.plan_prune(entries, 3)
    if pruned or [entry.path for entry in kept] != ['a.log', 'b.log', 'c.log']:
        problems.append('keep=3 应全部保留: pruned=%r kept=%r' % ([e.path for e in pruned], [e.path for e in kept]))
    pruned, kept = api.plan_prune(entries, 1)
    if [entry.path for entry in kept] != ['c.log'] or [entry.path for entry in pruned] != ['a.log', 'b.log']:
        problems.append('keep=1 结果错误: pruned=%r kept=%r' % ([e.path for e in pruned], [e.path for e in kept]))
    return (not problems), '; '.join(problems) or '保留数量与升序排列正确'


def check_tie_break_stability(ctx):
    try:
        api = _load_api(ctx, 'rotator')
    except Exception as exc:
        return False, '无法导入 rotator: %r' % (exc,)
    entries = [api.Entry('c.log', 5, 10), api.Entry('a.log', 5, 10), api.Entry('b.log', 5, 10)]
    pruned, kept = api.plan_prune(entries, 2)
    problems = []
    if [entry.path for entry in kept] != ['b.log', 'c.log']:
        problems.append('mtime 并列时 kept = %r（应为按 path 升序的后两个）' % ([entry.path for entry in kept],))
    if [entry.path for entry in pruned] != ['a.log']:
        problems.append('mtime 并列时 pruned = %r (应为 [a.log])' % ([entry.path for entry in pruned],))
    pruned, kept = api.plan_prune(entries, 1)
    if [entry.path for entry in kept] != ['c.log']:
        problems.append('并列且 keep=1 时 kept = %r（应为 [c.log]）' % ([entry.path for entry in kept],))
    return (not problems), '; '.join(problems) or 'mtime 并列时的淘汰顺序稳定'


def check_size_cap(ctx):
    try:
        api = _load_api(ctx, 'rotator')
    except Exception as exc:
        return False, '无法导入 rotator: %r' % (exc,)
    entries = [api.Entry('a.log', 10, 100), api.Entry('b.log', 20, 100), api.Entry('c.log', 30, 100)]
    pruned, kept = api.plan_prune(entries, 10, max_total_size=250)
    problems = []
    if [entry.path for entry in kept] != ['b.log', 'c.log']:
        problems.append('max_total_size=250 时 kept = %r' % ([entry.path for entry in kept],))
    if [entry.path for entry in pruned] != ['a.log']:
        problems.append('max_total_size=250 时 pruned = %r' % ([entry.path for entry in pruned],))
    kept_total = sum(entry.size for entry in kept)
    if kept_total > 250:
        problems.append('保留总字节 %d 超过上限 250' % kept_total)
    return (not problems), '; '.join(problems) or '字节上限约束正确'


def check_render_prune_log(ctx):
    try:
        api = _load_api(ctx, 'rotator')
    except Exception as exc:
        return False, '无法导入 rotator: %r' % (exc,)
    problems = []
    pruned = [api.Entry('a.log', 10, 100), api.Entry('b.log', 20, 200)]
    got = api.render_prune_log(pruned)
    expected = 'a.log\t10\t100\nb.log\t20\t200\n'
    if got != expected:
        problems.append('render_prune_log 输出 %r，期望 %r' % (got, expected))
    if api.render_prune_log([]) != '':
        problems.append('空列表应返回空字符串，实际 %r' % (api.render_prune_log([]),))
    return (not problems), '; '.join(problems) or '淘汰清单格式正确'
