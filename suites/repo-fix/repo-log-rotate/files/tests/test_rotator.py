from rotator import Entry, plan_prune


def test_keeps_newest_entries_in_ascending_order():
    entries = [Entry('a.log', 10, 100), Entry('b.log', 20, 100), Entry('c.log', 30, 100)]
    pruned, kept = plan_prune(entries, 2)
    assert [entry.path for entry in kept] == ['b.log', 'c.log']
    assert [entry.path for entry in pruned] == ['a.log']
