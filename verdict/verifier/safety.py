"""Read-only URI, authorizer callback, first-pass filter.

The real control is `file:db.sqlite?mode=ro` (+ immutable=1 for static DBs)
plus a set_authorizer callback approving per table AND per column.
The keyword blacklist is DEMOTED to a cheap first-pass filter — writes hide
in CTEs and subqueries (ADR-004, Reconciliation note #4).
"""
