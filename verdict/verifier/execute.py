"""Isolated execution, timeout, kill escalation.

Hard wall-clock timeout -> terminate() -> kill(). Open the sqlite3 connection
INSIDE each worker: connections are neither picklable nor thread-safe.
"""
