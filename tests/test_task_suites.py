"""任务包契约测试：schema、唯一 id、oracle 一致性 + 端到端 oracle validate。

端到端用例打了 `e2e` marker（约 30-60s），可用 `python -m pytest -m "not e2e"` 跳过。
"""
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
SUITES = ('terminal-lite', 'repo-fix', 'tool-use')
CHECK_PARAMS = {
    'file_exists': {'path'}, 'file_absent': {'path'}, 'dir_exists': {'path'},
    'file_contains': {'path', 'pattern'}, 'file_not_contains': {'path', 'pattern'},
    'file_equals': {'path'}, 'file_line_count': {'path'}, 'shell': {'command'},
    'state_changed': {'paths'}, 'state_unchanged': {'paths'},
    'tool_called': {'tool'}, 'python': {'func'},
}
ACTIONS = {'shell', 'read_file', 'write_file', 'list_dir', 'ask_user', 'tool', 'finish', 'give_up'}
BUILTIN = {'shell', 'read_file', 'write_file', 'list_dir', 'ask_user', 'finish', 'give_up'}
CATEGORIES = {'terminal', 'repo', 'tools', 'rebound'}
DIFFICULTIES = {'easy', 'medium', 'hard'}

CASES = [
    (path.parent.name, yaml.safe_load(path.read_text(encoding='utf-8')), path)
    for path in sorted(p for suite in SUITES for p in (ROOT / 'suites' / suite).glob('*/task.yaml'))
]
PARAMS = pytest.mark.parametrize('task_id,task,path', CASES, ids=[case[0] for case in CASES])


def merged(action):
    """兼容 {kind, args:{...}} 与 DESIGN 的扁平写法。"""
    flat = dict(action)
    nested = flat.pop('args', None)
    if isinstance(nested, dict):
        flat.update(nested)
    return flat


@PARAMS
def test_schema(task_id, task, path):
    assert task['id'] == task_id
    assert task['category'] in CATEGORIES
    assert task['difficulty'] in DIFFICULTIES
    assert task['visibility'] in ('public', 'hidden')
    assert 8 <= int(task['max_steps']) <= 16
    assert float(task['timeout_s']) <= 120
    assert task['prompt'].strip()
    assert task['solution']['actions']
    assert not task.get('faults')
    workspace = task.get('workspace') or {}
    if workspace.get('copy_files'):
        files_dir = path.parent / 'files'
        assert files_dir.is_dir() and any(files_dir.rglob('*'))


@PARAMS
def test_tools_and_checks(task_id, task, path):
    names = []
    for tool in task['tools']:
        if isinstance(tool, str):
            assert tool in BUILTIN
            names.append(tool)
            continue
        names.append(tool['name'])
        if tool.get('kind') == 'mock_tool':
            assert tool.get('mock')
            for entry in tool['mock']:
                assert ('match' in entry) != ('default' in entry)
                if 'match' in entry:
                    assert entry.get('response')
                    re.compile(entry['match'])
    assert len(names) == len(set(names))
    verifier = task['verifier']
    assert verifier['pass_threshold'] == 1.0
    check_names = [check['name'] for check in verifier['checks']]
    assert len(check_names) == len(set(check_names))
    for check in verifier['checks']:
        assert check['kind'] in CHECK_PARAMS
        assert float(check['weight']) > 0
        assert 'required' in check
        assert not CHECK_PARAMS[check['kind']] - set(check)
        if check['kind'] == 'python':
            text = (path.parent / 'checks.py').read_text(encoding='utf-8')
            assert ('def %s(' % check['func']) in text


@PARAMS
def test_oracle_consistency(task_id, task, path):
    actions = task['solution']['actions']
    assert len(actions) <= int(task['max_steps'])
    for action in actions:
        assert action['kind'] in ACTIONS
        flat = merged(action)
        if action['kind'] == 'shell':
            assert flat.get('command')
        elif action['kind'] == 'write_file':
            assert flat.get('path') and 'content' in flat
        elif action['kind'] in ('read_file', 'list_dir'):
            assert flat.get('path')
        elif action['kind'] == 'tool':
            assert flat.get('name') and isinstance(flat.get('args'), dict)
    counted = sum(1 for action in actions if action['kind'] in ('shell', 'tool'))
    assert task['budget']['oracle_tool_calls'] == counted


def test_ids_unique():
    ids = [task['id'] for _, task, _ in CASES]
    assert not {task_id for task_id in ids if ids.count(task_id) > 1}
    assert len(ids) >= 14


def test_mock_patterns_ascii():
    for task_id, task, path in CASES:
        for tool in task['tools']:
            if isinstance(tool, dict) and tool.get('kind') == 'mock_tool':
                for entry in tool['mock']:
                    pattern = entry.get('match')
                    if pattern:
                        assert all(ord(char) < 128 for char in pattern), tool['name']
        for check in task['verifier']['checks']:
            pattern = check.get('args_contains')
            if pattern:
                assert all(ord(char) < 128 for char in pattern), check['name']


@pytest.mark.e2e
def test_e2e_oracle_validate():
    pytest.importorskip('agentlab')
    from agentlab.core.registry import Registry
    from agentlab.eval.validate import validate_tasks

    registry = Registry(ROOT / 'suites').scan()
    assert not registry.errors, registry.errors
    tasks = [task for suite in SUITES for task in registry.by_suite(suite)]
    assert len(tasks) >= 14
    results = validate_tasks(tasks, policy='oracle', workers=3)
    failures = ['%s: %s' % (item.task_id, item.failed_checks) for item in results if not item.success]
    assert not failures, failures
    assert len(results) == len(tasks)
