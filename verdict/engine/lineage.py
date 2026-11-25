"""Answer lineage: where the number came from, read only from the chosen SQL.

    lineage("SELECT SUM(p.payment_value) FROM orders o JOIN payments p ON ...
             WHERE o.status = 'delivered' AND o.purchase_date >= '2017-01-01'")
    -> {"output": "SUM(p.payment_value)", "formula": "SUM(payments.payment_value)",
        "tables": ["orders", "payments"], "columns": ["orders.status", ...],
        "filters": ["orders.status = 'delivered'", "orders.purchase_date >= '2017-01-01'"],
        "period": "orders.purchase_date >= '2017-01-01'", "group_by": []}

Nothing here asks a model. Every line is a part of the SQL that ran, with
table aliases replaced by table names so the analyst can read it. If the SQL
cannot be read, lineage is None and the frontend hides the section.

"period" lists the filters on date-like columns (a name holding date, time,
year, month or day, or a date function such as strftime). It is a reading of
the SQL, not a guarantee about the data.
"""

from __future__ import annotations

import re

import sqlglot
from sqlglot import exp

_DATE_NAME = re.compile(r"date|time|year|month|day|_at$|_on$", re.IGNORECASE)
_DATE_FUNCS = {"strftime", "date", "datetime", "julianday", "year", "month"}
_DATE_LITERAL = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?")


def _alias_map(select: exp.Select) -> dict[str, str]:
    """alias -> real table name, for every table in the query (subqueries too)."""
    out = {}
    for t in select.find_all(exp.Table):
        if t.name:
            out[t.alias_or_name] = t.name
    return out


def _readable(node: exp.Expression, aliases: dict[str, str]) -> str:
    """The SQL of ``node`` with table aliases replaced by table names."""
    node = node.copy()
    for col in node.find_all(exp.Column):
        if col.table and col.table in aliases:
            col.set("table", exp.to_identifier(aliases[col.table]))
    return node.sql(dialect="sqlite")


def _split_and(cond: exp.Expression | None) -> list[exp.Expression]:
    if cond is None:
        return []
    if isinstance(cond, exp.And):
        return _split_and(cond.left) + _split_and(cond.right)
    if isinstance(cond, exp.Paren):
        return _split_and(cond.this) if isinstance(cond.this, exp.And) else [cond]
    return [cond]


def _is_date_filter(cond: exp.Expression) -> bool:
    for col in cond.find_all(exp.Column):
        if _DATE_NAME.search(col.name or ""):
            return True
    for fn in cond.find_all(exp.Func):
        name = (fn.sql_name() or "").lower()
        if name in _DATE_FUNCS or (isinstance(fn, exp.Anonymous) and str(fn.this).lower() in _DATE_FUNCS):
            return True
    for lit in cond.find_all(exp.Literal):
        if lit.is_string and _DATE_LITERAL.match(lit.this or ""):
            return True
    return False


def _unique(items: list[str]) -> list[str]:
    seen, out = set(), []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def lineage(sql: str) -> dict | None:
    """Lineage of one SELECT, or None if it cannot be read."""
    if not sql or not sql.strip():
        return None
    try:
        tree = sqlglot.parse_one(sql, read="sqlite")
    except Exception:
        return None
    select = tree if isinstance(tree, exp.Select) else tree.find(exp.Select)
    if select is None:
        return None
    try:
        aliases = _alias_map(tree)
        projections = select.expressions
        # The result's column names, as the analyst sees them in the table.
        output = ", ".join(
            p.alias_or_name if (p.alias or isinstance(p, exp.Column)) else p.sql(dialect="sqlite")
            for p in projections
        )
        formula = ", ".join(_readable(p.unalias() if p.alias else p, aliases) for p in projections)

        tables = _unique([t.name for t in tree.find_all(exp.Table) if t.name])
        columns = _unique([
            f"{aliases.get(c.table, c.table)}.{c.name}" if c.table else c.name
            for c in tree.find_all(exp.Column) if c.name and c.name != "*"
        ])

        where = select.args.get("where")
        having = select.args.get("having")
        conds = _split_and(where.this if where else None) + _split_and(having.this if having else None)
        filters = [_readable(c, aliases) for c in conds]
        dated = [_readable(c, aliases) for c in conds if _is_date_filter(c)]

        group = select.args.get("group")
        group_by = [_readable(g, aliases) for g in group.expressions] if group else []
    except Exception:
        return None
    return {
        "output": output,
        "formula": formula,
        "tables": tables,
        "columns": columns,
        "filters": filters,
        "period": " and ".join(dated) if dated else None,
        "group_by": group_by,
    }
