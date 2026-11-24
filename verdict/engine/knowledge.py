"""What the analyst has taught Verdict, and how it is used on new questions.

Three kinds of knowledge, all saved per database in data/app.db:

    meanings       "revenue = SUM(payment_value), delivered orders only"
    examples       an approved question with its SQL and answer
    known numbers  an approved answer that later answers must not contradict

Two uses:

  1. Prompt help. Meanings whose term appears in the question, and the 3 most
     similar approved examples, are added to the prompt. This makes a right
     answer more likely. It never makes an answer trusted by itself: the
     checks still decide the level (plan section 2, "learning loop never
     skips checks").

  2. A check. If a near-identical question was approved before and the new
     answer is different, the new answer goes to review. "This quarter" and
     "last quarter" look similar but must not share an answer, so only
     near-identical questions count, and a difference can only lower trust.

Similarity is TF-IDF over words and word pairs. It needs no model and works
offline. Word pairs make "last quarter" and "this quarter" differ more.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from verdict.verifier.compare import compare_results, gold_has_order_by
from verdict.verifier.types import ExecutionResult

#: Similar enough to show as a prompt example.
EXAMPLE_MIN_SIMILARITY = 0.2
TOP_EXAMPLES = 3

#: Similar enough that the approved answer should be the same answer.
NEAR_IDENTICAL = 0.9


def normalize(question: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", question.lower())).strip()


def similarities(question: str, others: list[str]) -> list[float]:
    """Cosine similarity of ``question`` to each of ``others``, 0.0 to 1.0."""
    if not others:
        return []
    q = normalize(question)
    docs = [normalize(o) for o in others]
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        vec = TfidfVectorizer(ngram_range=(1, 2), token_pattern=r"(?u)\b\w+\b", sublinear_tf=True)
        m = vec.fit_transform(docs + [q])
        sims = cosine_similarity(m[-1], m[:-1])[0]
    except ValueError:  # every text was empty
        sims = [0.0] * len(docs)
    # An exact match is 1.0 even if rounding says 0.9999.
    return [1.0 if d == q else float(s) for d, s in zip(docs, sims)]


def similar_examples(
    question: str, examples: list[dict], top_k: int = TOP_EXAMPLES,
    min_similarity: float = EXAMPLE_MIN_SIMILARITY,
) -> list[tuple[dict, float]]:
    """The approved examples most like ``question``, most similar first."""
    sims = similarities(question, [e["question"] for e in examples])
    ranked = sorted(zip(examples, sims), key=lambda p: -p[1])
    return [(e, s) for e, s in ranked if s >= min_similarity][:top_k]


def matching_meanings(question: str, meanings: list[dict]) -> list[dict]:
    """Meanings whose term appears in the question as a word (plural allowed)."""
    q = normalize(question)
    out = []
    for m in meanings:
        term = normalize(m["term"])
        if term and re.search(rf"\b{re.escape(term)}(s|es)?\b", q):
            out.append(m)
    return out


def meaning_text(m: dict) -> str:
    return f"{m['term']} = {m['definition']}"


@dataclass
class PromptKnowledge:
    """Knowledge picked for one question."""

    meanings: list[dict]
    examples: list[tuple[dict, float]]

    @property
    def used(self) -> list[str]:
        """Plain lines for the evidence view: what was added to the prompt."""
        lines = [meaning_text(m) for m in self.meanings]
        lines += [f'Approved example: "{e["question"]}"' for e, _ in self.examples]
        return lines

    def prompt_block(self) -> str:
        """Text added to the prompt; "" when there is nothing to add."""
        parts = []
        if self.meanings:
            parts.append("Meanings agreed with the analyst:\n" + "\n".join(
                f"- {meaning_text(m)}" + (f" (SQL hint: {m['sql_hint']})" if m.get("sql_hint") else "")
                for m in self.meanings
            ))
        if self.examples:
            parts.append("Approved examples for this database:\n" + "\n".join(
                f"Q: {e['question']}\nSQL: {e['sql']}" for e, _ in self.examples
            ))
        return "\n\n".join(parts)


def pick_knowledge(question: str, meanings: list[dict], examples: list[dict]) -> PromptKnowledge:
    return PromptKnowledge(matching_meanings(question, meanings), similar_examples(question, examples))


def _as_result(columns: list, rows: list) -> ExecutionResult:
    return ExecutionResult(
        status="ok", columns=tuple(columns or ()), rows=tuple(tuple(r) for r in rows or ())
    )


def same_answer(result: ExecutionResult, columns: list, rows: list, sql: str) -> bool:
    """Is ``result`` the same answer as a saved one? Same rules as grouping."""
    order_sql = sql if gold_has_order_by(sql) else "SELECT 1"
    return compare_results(result, _as_result(columns, rows), order_sql).verdict == "correct"


@dataclass
class Conflict:
    """A near-identical approved question whose answer differs."""

    kind: str          # "example" or "known_number"
    item: dict
    similarity: float

    @property
    def text(self) -> str:
        what = "approved answer" if self.kind == "example" else f'known number "{self.item["name"]}"'
        return f'Differs from the {what} for "{self.item["question"]}".'


def find_conflict(
    question: str, result: ExecutionResult | None, examples: list[dict], known_numbers: list[dict],
    near: float = NEAR_IDENTICAL,
) -> tuple[Conflict | None, int]:
    """Check the answer against approved answers to near-identical questions.

    Returns (the first conflict or None, how many approved answers were compared).
    """
    if result is None:
        return None, 0
    items = [("example", e, e["columns"], e["rows"]) for e in examples]
    items += [("known_number", k, k["columns"], k["value"]) for k in known_numbers]
    sims = similarities(question, [it[1]["question"] for it in items])
    compared = 0
    for (kind, item, cols, rows), s in sorted(zip(items, sims), key=lambda p: -p[1]):
        if s < near:
            break
        compared += 1
        if not same_answer(result, cols, rows, item["sql"]):
            return Conflict(kind, item, s), compared
    return None, compared
