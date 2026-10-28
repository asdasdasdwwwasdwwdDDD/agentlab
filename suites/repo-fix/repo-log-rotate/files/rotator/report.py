"""淘汰清单渲染。"""


def render_prune_log(pruned):
    """每条一行：path<TAB>mtime<TAB>size，末尾一个换行；空列表返回空字符串。"""
    lines = []
    for entry in pruned:
        lines.append('%s\t%d' % (entry.path, entry.mtime))
    return '\n'.join(lines) + '\n'
