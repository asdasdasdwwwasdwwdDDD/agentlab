from ledger import load_entries, to_dict

DATA = """date,account,description,amount
2024-01-03,office,"Paper, A4",12.50
2024-01-04,travel,Taxi (airport),-30.00
2024-01-05,office,Pen set,8.25
"""


def test_entries_and_totals():
    entries = load_entries(DATA)
    assert len(entries) == 3
    assert entries[0]['description'] == 'Paper, A4'
    summary = to_dict(entries)
    assert [item['account'] for item in summary['accounts']] == ['office', 'travel']
    assert summary['accounts'][0]['total_cents'] == 2075
    assert summary['accounts'][1]['total_cents'] == -3000
