from verdict.engine.ambiguity import find_split, label_meanings, split_min_size
from verdict.engine.group import AnswerGroup, Grouping
from verdict.verifier.types import ExecutionResult


def grp(value, size):
    rows = () if value is None else ((value,),)
    return AnswerGroup(ExecutionResult("ok", rows=rows, columns=("x",)),
                       members=list(range(size)), sqls=[f"SELECT {value}"] * size)


def grouping(*groups, n=8):
    return Grouping(n_attempts=n, groups=list(groups), n_cannot_answer=0, n_failed=0, results=[])


def test_split_min_size_scales_with_attempts():
    assert split_min_size(8) == 3
    assert split_min_size(4) == 2
    assert split_min_size(16) == 6


def test_four_four_is_a_split():
    a, b = grp(1, 4), grp(2, 4)
    assert find_split(grouping(a, b)) == [a, b]


def test_three_three_two_is_a_split():
    assert find_split(grouping(grp(1, 3), grp(2, 3), grp(3, 2))) is not None


def test_six_two_is_not_a_split():
    assert find_split(grouping(grp(1, 6), grp(2, 2))) is None


def test_single_group_is_not_a_split():
    assert find_split(grouping(grp(1, 8))) is None


def test_empty_groups_do_not_count():
    # 4 attempts with an answer and 4 with an empty one: the empty group is
    # a failed filter, not a second meaning.
    assert find_split(grouping(grp(1, 4), grp(None, 4))) is None


def test_label_names_the_extra_column():
    a = "SELECT SUM(price) FROM items"
    b = "SELECT SUM(price + freight_value) FROM items"
    la, lb = label_meanings(a, b)
    assert la == "Without freight_value"
    assert lb == "Uses freight_value"


def test_label_names_the_extra_filter():
    la, lb = label_meanings("SELECT COUNT(*) FROM orders WHERE status = 'delivered'",
                            "SELECT COUNT(*) FROM orders")
    assert "status = 'delivered'" in la and la.startswith("Only where")
    assert lb.startswith("Does not filter on")


def test_label_names_distinct():
    la, lb = label_meanings("SELECT COUNT(DISTINCT c) FROM t", "SELECT COUNT(c) FROM t")
    assert la == "With DISTINCT" and lb == "Without DISTINCT"


def test_unreadable_sql_gets_plain_labels():
    assert label_meanings("not sql (((", "SELECT 1") == ("Meaning A", "Meaning B")


def test_labels_are_short():
    cond = " AND ".join(f"col_{i} = {i}" for i in range(30))
    la, _ = label_meanings(f"SELECT 1 FROM t WHERE {cond}", "SELECT 1 FROM t")
    assert len(la) <= 80 and la.endswith("...")
