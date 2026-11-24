from verdict.engine.knowledge import (
    find_conflict,
    matching_meanings,
    pick_knowledge,
    similar_examples,
    similarities,
)
from verdict.verifier.types import ExecutionResult


def ex(q, rows, sql="SELECT 1", cols=("x",)):
    return {"question": q, "sql": sql, "columns": list(cols), "rows": rows}


def res(*rows):
    return ExecutionResult("ok", rows=tuple(rows), columns=("x",))


def test_rewording_is_near_identical():
    s = similarities("Revenue from Rio last quarter?", ["revenue from rio, last quarter"])
    assert s == [1.0]


def test_this_quarter_and_last_quarter_are_not_near_identical():
    [s] = similarities("Revenue from Rio this quarter?", ["Revenue from Rio last quarter?"])
    assert 0.2 < s < 0.9


def test_similar_examples_ranks_and_limits():
    exs = [ex("orders in 2017", []), ex("customers in Rio", []), ex("orders in 2018", []),
           ex("how many orders in 2017", []), ex("weather today", [])]
    got = [e["question"] for e, _ in similar_examples("orders in 2017?", exs)]
    assert got[0] == "orders in 2017"
    assert len(got) == 3 and "weather today" not in got


def test_meanings_match_whole_words_and_plurals():
    ms = [{"term": "revenue", "definition": "SUM(price)"}, {"term": "order", "definition": "x"},
          {"term": "rev", "definition": "y"}]
    got = [m["term"] for m in matching_meanings("Total revenue from orders?", ms)]
    assert got == ["revenue", "order"]


def test_prompt_block_and_used_lines():
    pk = pick_knowledge(
        "revenue in 2017",
        [{"term": "revenue", "definition": "SUM(price), delivered only", "sql_hint": None}],
        [ex("revenue in 2018", [[5]], sql="SELECT SUM(price) FROM t")],
    )
    block = pk.prompt_block()
    assert "revenue = SUM(price), delivered only" in block
    assert "Q: revenue in 2018\nSQL: SELECT SUM(price) FROM t" in block
    assert pk.used[0] == "revenue = SUM(price), delivered only"


def test_empty_knowledge_adds_nothing():
    assert pick_knowledge("anything", [], []).prompt_block() == ""


def test_conflict_with_near_identical_example():
    conflict, n = find_conflict("Orders in 2017?", res((10,)), [ex("orders in 2017", [[12]])], [])
    assert conflict is not None and conflict.kind == "example" and n == 1
    assert "orders in 2017" in conflict.text


def test_same_answer_is_not_a_conflict():
    # 12 and 12.0 are the same answer, as in grouping.
    conflict, n = find_conflict("Orders in 2017?", res((12.0,)), [ex("orders in 2017", [[12]])], [])
    assert conflict is None and n == 1


def test_different_question_is_never_compared():
    conflict, n = find_conflict("Orders in 2018?", res((10,)), [ex("orders in 2017", [[12]])], [])
    assert conflict is None and n == 0


def test_conflict_with_known_number():
    k = {"name": "Orders 2017", "question": "orders in 2017", "sql": "SELECT 1",
         "columns": ["x"], "value": [[45101]]}
    conflict, _ = find_conflict("orders in 2017", res((45000,)), [], [k])
    assert conflict.kind == "known_number" and "Orders 2017" in conflict.text


def test_no_answer_no_conflict():
    assert find_conflict("q", None, [ex("q", [[1]])], []) == (None, 0)
