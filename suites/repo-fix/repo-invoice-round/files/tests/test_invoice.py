from invoicelib import build_invoice


def test_totals_include_last_line_item():
    invoice = build_invoice('INV-1001', [
        {'sku': 'A', 'unit_price': '10.00', 'quantity': 1, 'tax_rate': 0.1},
        {'sku': 'B', 'unit_price': '5.00', 'quantity': 2, 'tax_rate': 0.1},
    ])
    totals = invoice.as_dict()
    assert totals['subtotal_cents'] == 2000
    assert totals['tax_cents'] == 200
    assert totals['total_cents'] == 2200
