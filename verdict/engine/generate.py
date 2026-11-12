"""Step 2 of the trust engine: ask the AI for SQL and read its replies.

    build_prompt(schema, question) -> the text sent to the AI
    parse_reply(text)              -> Attempt("sql", "SELECT ...") or Attempt("cannot_answer")
    generate_attempts(writer, schema, question, n=8) -> list[Attempt]

The prompt gives the AI a way out: if the tables cannot answer the question,
it replies CANNOT_ANSWER instead of inventing a query. Without that option a
model asked "how happy are our customers?" about a sales table will still
write some SQL, and the SQL will return some number.

SQL is pulled out of the reply with the same rule used in training
(verdict.train.reward.extract_sql), so the product and the research read model
output the same way.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from verdict.engine.llm import SQLWriter
from verdict.train.reward import extract_sql

CANNOT_ANSWER = "CANNOT_ANSWER"

PROMPT_TEMPLATE = """You write SQLite queries that answer questions about a database.

Database tables:
{schema}

Question: {question}

Rules:
- Use only the tables and columns listed above.
- Write one SQLite SELECT query that answers the question.
- Put the query in a ```sql code block.
- If these tables cannot answer the question, reply with only the word {cannot}.
"""

_CANNOT_RE = re.compile(rf"\b{CANNOT_ANSWER}\b")


@dataclass(frozen=True)
class Attempt:
    """One reply from the AI, already read.

    kind:
      sql            - the reply contains a query (``sql`` is set)
      cannot_answer  - the AI said the data cannot answer the question
      empty          - the reply had nothing usable (or the API call failed)
    """

    kind: Literal["sql", "cannot_answer", "empty"]
    sql: str = ""
    raw: str = ""


def build_prompt(schema: str, question: str) -> str:
    return PROMPT_TEMPLATE.format(schema=schema, question=question.strip(), cannot=CANNOT_ANSWER)


def parse_reply(text: str) -> Attempt:
    """Turn one AI reply into an Attempt.

    A reply that has a SQL block counts as SQL even if it also mentions
    CANNOT_ANSWER, because the query is what would actually run.
    """
    text = text or ""
    has_block = "```" in text
    if not has_block and _CANNOT_RE.search(text):
        return Attempt("cannot_answer", raw=text)

    sql = extract_sql(text)
    if not sql or sql == CANNOT_ANSWER:
        return Attempt("cannot_answer" if sql == CANNOT_ANSWER else "empty", raw=text)
    return Attempt("sql", sql=sql, raw=text)


def generate_attempts(writer: SQLWriter, schema: str, question: str, n: int = 8) -> list[Attempt]:
    """Ask ``writer`` for ``n`` independent replies and parse each one."""
    replies = writer.write(build_prompt(schema, question), n)
    return [parse_reply(r) for r in replies]
