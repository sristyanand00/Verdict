"""Answer lineage is read only from the SQL, with aliases turned into table names."""

from verdict.engine.lineage import lineage

REVENUE = (
    "SELECT SUM(p.payment_value) AS revenue FROM orders o"
    " JOIN order_payments p ON p.order_id = o.order_id"
    " WHERE o.order_status = 'delivered' AND o.order_purchase_timestamp >= '2017-01-01'"
)


def test_aliases_become_table_names():
    lin = lineage(REVENUE)
    assert lin["output"] == "revenue"
    assert lin["formula"] == "SUM(order_payments.payment_value)"
    assert lin["tables"] == ["orders", "order_payments"]
    assert "orders.order_status" in lin["columns"]
    assert lin["filters"] == [
        "orders.order_status = 'delivered'", "orders.order_purchase_timestamp >= '2017-01-01'",
    ]


def test_period_is_only_the_date_filters():
    assert lineage(REVENUE)["period"] == "orders.order_purchase_timestamp >= '2017-01-01'"
    lin = lineage("SELECT COUNT(*) FROM orders WHERE strftime('%Y', created) = '2018'")
    assert lin["period"] is not None
    assert lineage("SELECT COUNT(*) FROM orders WHERE status = 'x'")["period"] is None


def test_group_by_and_having():
    lin = lineage(
        "SELECT c.state, COUNT(*) FROM customers c GROUP BY c.state HAVING COUNT(*) > 100"
    )
    assert lin["output"] == "state, COUNT(*)"
    assert lin["group_by"] == ["customers.state"]
    assert lin["filters"] == ["COUNT(*) > 100"]


def test_unreadable_sql_gives_none():
    assert lineage("") is None
    assert lineage("this is not sql") is None
