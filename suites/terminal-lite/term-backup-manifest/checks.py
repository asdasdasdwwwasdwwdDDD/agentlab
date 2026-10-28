import hashlib
import json

EXPECTED = {'file_count': 5, 'total_bytes': 183, 'files': [{'path': 'app/data.json', 'size': 31, 'sha256': 'a5a9738ad9ba8919c518fe369921a6f435ed5107b0ced5d5203ac87d30632f5f'}, {'path': 'app/main.py', 'size': 44, 'sha256': 'c41adbf68df115e99aa0a27f4c5ec415ff026972ebf595d86634aff9d6dc0f32'}, {'path': 'app/util.py', 'size': 51, 'sha256': '09745d2477035e0face2ceacc1be5eddebfa6c4faafdd7b751b02d664b20cfcb'}, {'path': 'docs/readme.md', 'size': 45, 'sha256': '5847cc6983930200de5d73947f83a1705bf61748d21271a591de27057bb7ad07'}, {'path': 'license', 'size': 12, 'sha256': '267f7a2e19dfa9df99af774520985a0e521925293ea5b7e767ab06969d06bf91'}]}


def check_manifest(ctx):
    try:
        data = json.loads(ctx.read('backup/manifest.json'))
    except Exception as exc:
        return False, 'backup/manifest.json 无法解析: ' + str(exc)
    if not isinstance(data, dict):
        return False, 'manifest 顶层必须是对象'
    if data != EXPECTED:
        return False, 'manifest 内容与期望不符（检查排除规则、size/sha256、排序与合计）'
    return True, 'manifest 的 path/size/sha256/file_count/total_bytes 全部正确'


def check_copies(ctx):
    root = ctx.workspace / 'backup'
    if not root.is_dir():
        return False, 'backup/ 目录不存在'
    actual = sorted(path.relative_to(root).as_posix() for path in root.rglob('*') if path.is_file())
    expected = sorted([item['path'] for item in EXPECTED['files']] + ['manifest.json'])
    if actual != expected:
        return False, 'backup/ 文件集合不符：期望 %r，实际 %r' % (expected, actual)
    bad = []
    for item in EXPECTED['files']:
        digest = hashlib.sha256((root / item['path']).read_bytes()).hexdigest()
        if digest != item['sha256']:
            bad.append(item['path'])
    if bad:
        return False, '备份内容与源文件不一致: ' + ', '.join(bad)
    return True, '备份文件集合与字节内容全部一致'
