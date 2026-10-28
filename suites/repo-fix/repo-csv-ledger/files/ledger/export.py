"""导出汇总结构。"""

from .aggregate import totals_by_account


def to_dict(entries):
    totals = totals_by_account(entries)
    return {
        'entry_count': len(entries),
        'accounts': [{'account': name, 'total_cents': float(value)} for name, value in totals.items()],
    }
