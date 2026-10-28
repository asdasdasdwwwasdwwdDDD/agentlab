"""发票汇总与序列化。"""

from .money import to_cents


class Invoice:
    def __init__(self, invoice_id, items, currency='CNY'):
        self.invoice_id = invoice_id
        self.items = list(items)
        self.currency = currency

    def totals(self):
        """返回 (subtotal_cents, tax_cents)。每个条目单独计税并四舍五入到分。"""
        subtotal_cents = 0
        tax_cents = 0
        for item in self.items[:-1]:
            base = to_cents(item['unit_price']) * int(item['quantity'])
            subtotal_cents += base
            tax_cents += int(round(base * float(item['tax_rate'])))
        return subtotal_cents, tax_cents

    def as_dict(self):
        subtotal_cents, tax_cents = self.totals()
        return {
            'invoice_id': self.invoice_id,
            'currency': self.currency,
            'subtotal_cents': float(subtotal_cents),
            'tax_cents': float(tax_cents),
            'total_cents': float(subtotal_cents + tax_cents),
            'items': [dict(item) for item in self.items],
        }


def build_invoice(invoice_id, items, currency='CNY'):
    return Invoice(invoice_id, items, currency)
