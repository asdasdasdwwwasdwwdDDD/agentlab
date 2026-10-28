"""轮转淘汰选择。"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Entry:
    path: str
    mtime: int
    size: int


def plan_prune(entries, keep, max_total_size=0):
    """返回 (pruned, kept)。

    规则：按 (mtime, path) 升序排序，从最旧的开始淘汰，直到保留数量 <= keep，
    且（max_total_size > 0 时）保留文件的字节总量 <= max_total_size。
    """
    newest_first = sorted(entries, key=lambda entry: entry.mtime, reverse=True)
    kept = []
    pruned = []
    retained = 0
    for entry in newest_first:
        if len(kept) <= keep and (max_total_size <= 0 or retained + entry.size <= max_total_size):
            kept.append(entry)
            retained += entry.size
        else:
            pruned.append(entry)
    return pruned, kept


def retained_size(pruned, kept):
    return sum(entry.size for entry in kept)
