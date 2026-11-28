"""Demo questions for the five databases, with the SQL we checked by hand.

    python demos/questions/questions.py

Runs every SQL below on its database, prints the result, and writes:
- demos/questions/<db>.txt          one question per line, for scripts/warm_cache.py
- datasets/olist/demo_questions.txt  the same list for olist
- demos/questions/EXPECTED.md       the table of questions and expected answers

Kinds:
- trusted:   one clear reading; we expect Trusted (a hope, not a promise: the
             model can still disagree with itself).
- two:       two fair readings with different answers; we expect Review with
             "two meanings". Both SQLs are given.
- not_data:  the data cannot answer it; we expect Reject ("not in the data").
             expected is None.
- loop:      the learning-loop pair for the demo. The first is expected to be
             Review; after the analyst approves it, the second is asked.

The script stops with an error if a SQL fails or gives a different answer
than the one written here, so the table cannot go stale silently.
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def db_file(db: str) -> Path:
    if db == "olist":
        return REPO / "datasets" / "olist" / "olist.sqlite"
    return REPO / "datasets" / "dev_databases" / db / f"{db}.sqlite"


# Each entry: (kind, question, expected answer text, [sql, ...], note)
# For "two" the first SQL is reading A and the second reading B.
QUESTIONS: dict[str, list[tuple]] = {
    "olist": [
        ("trusted", "How many orders are there?", "99441",
         ["SELECT COUNT(*) FROM orders"], ""),
        ("trusted", "How many orders were canceled?", "625",
         ["SELECT COUNT(*) FROM orders WHERE order_status = 'canceled'"],
         "status text is 'canceled' (one l)"),
        ("trusted", "Which payment type is used most often?", "credit_card",
         ["SELECT payment_type FROM payments GROUP BY payment_type ORDER BY COUNT(*) DESC LIMIT 1"],
         "76,795 of 103,886 payment rows"),
        ("trusted", "What is the average review score?", "4.09",
         ["SELECT ROUND(AVG(review_score), 2) FROM reviews"], "scores are 1 to 5"),
        ("trusted", "How many sellers are in the state SP?", "1849",
         ["SELECT COUNT(*) FROM sellers WHERE seller_state = 'SP'"], ""),
        ("trusted", "Which product category has the most products?", "bed_bath_table",
         ["SELECT product_category FROM products GROUP BY product_category ORDER BY COUNT(*) DESC LIMIT 1"],
         "3,029 products"),
        ("two", "How many customers do we have?", "99441 or 96096",
         ["SELECT COUNT(*) FROM customers",
          "SELECT COUNT(DISTINCT customer_unique_id) FROM customers"],
         "customer_id is one per order; customer_unique_id is the real person"),
        ("two", "What was the total revenue in 2017?", "6155806.98 or 7142672.43",
         ["SELECT ROUND(SUM(oi.price), 2) FROM order_items oi JOIN orders o ON o.order_id = oi.order_id "
          "WHERE strftime('%Y', o.order_purchase_timestamp) = '2017'",
          "SELECT ROUND(SUM(oi.price + oi.freight_value), 2) FROM order_items oi JOIN orders o ON o.order_id = oi.order_id "
          "WHERE strftime('%Y', o.order_purchase_timestamp) = '2017'"],
         "price only, or price plus freight. Payments give a third number, 7249746.73"),
        ("loop", "How many orders were delivered late in 2018?", "4944",
         ["SELECT COUNT(*) FROM orders WHERE order_status = 'delivered' "
          "AND order_delivered_customer_date > order_estimated_delivery_date "
          "AND strftime('%Y', order_purchase_timestamp) = '2018'"],
         "late = delivered after the estimated date; year of purchase. Readings differ "
         "(year of delivery: 5676; compare dates only: 4079), so expect Review. Approve this SQL."),
        ("loop", "How many orders were delivered late in 2017?", "2878",
         ["SELECT COUNT(*) FROM orders WHERE order_status = 'delivered' "
          "AND order_delivered_customer_date > order_estimated_delivery_date "
          "AND strftime('%Y', order_purchase_timestamp) = '2017'"],
         "ask after approving the 2018 one; the approved example should make it Trusted"),
        ("not_data", "What was our return on ad spend in 2018?", None, [],
         "no marketing or ad spend table"),
        ("not_data", "How many people visited the website last month?", None, [],
         "no web traffic data; the data also ends in October 2018"),
    ],
    "financial": [
        ("trusted", "How many accounts are there?", "4500",
         ["SELECT COUNT(*) FROM account"], ""),
        ("trusted", "How many clients are women?", "2645",
         ["SELECT COUNT(*) FROM client WHERE gender = 'F'"], ""),
        ("trusted", "How many gold cards are there?", "88",
         ["SELECT COUNT(*) FROM card WHERE type = 'gold'"], ""),
        ("trusted", "How many accounts were opened in 1996?", "1363",
         ["SELECT COUNT(*) FROM account WHERE strftime('%Y', date) = '1996'"], ""),
        ("trusted", "What is the average loan amount?", "151410.18",
         ["SELECT ROUND(AVG(amount), 2) FROM loan"], ""),
        ("two", "How many loans are not paid back?", "76 or 479",
         ["SELECT COUNT(*) FROM loan WHERE status IN ('B', 'D')",
          "SELECT COUNT(*) FROM loan WHERE status != 'A'"],
         "A = finished OK, B = finished not paid, C = running OK, D = running in debt. "
         "'Not paid back' can mean in trouble (B, D) or simply not finished yet (B, C, D)"),
        ("trusted", "Which region has the most accounts?", "north Moravia",
         ["SELECT d.A3 FROM account a JOIN district d ON d.district_id = a.district_id "
          "GROUP BY d.A3 ORDER BY COUNT(*) DESC LIMIT 1"],
         "region is the coded column A3; hard for the model because names are coded"),
        ("not_data", "What is the credit score of each client?", None, [],
         "no credit score column"),
    ],
    "formula_1": [
        ("trusted", "How many drivers are there?", "840",
         ["SELECT COUNT(*) FROM drivers"], ""),
        ("trusted", "How many races were held in 2009?", "17",
         ["SELECT COUNT(*) FROM races WHERE year = 2009"], ""),
        ("trusted", "How many drivers are British?", "162",
         ["SELECT COUNT(*) FROM drivers WHERE nationality = 'British'"], ""),
        ("trusted", "Which driver has won the most races?", "Michael Schumacher",
         ["SELECT d.forename || ' ' || d.surname FROM results r JOIN drivers d ON d.driverId = r.driverId "
          "WHERE r.position = 1 GROUP BY r.driverId ORDER BY COUNT(*) DESC LIMIT 1"], "91 wins"),
        ("trusted", "Which constructor has the most race wins?", "Ferrari",
         ["SELECT c.name FROM results r JOIN constructors c ON c.constructorId = r.constructorId "
          "WHERE r.position = 1 GROUP BY c.constructorId ORDER BY COUNT(*) DESC LIMIT 1"], "229 wins"),
        ("trusted", "How many races did Lewis Hamilton win in 2008?", "5",
         ["SELECT COUNT(*) FROM results r JOIN races ra ON ra.raceId = r.raceId "
          "JOIN drivers d ON d.driverId = r.driverId "
          "WHERE d.forename = 'Lewis' AND d.surname = 'Hamilton' AND ra.year = 2008 AND r.position = 1"], ""),
        ("two", "Which country has the most circuits?", "USA or Italy",
         ["SELECT country FROM circuits GROUP BY country ORDER BY COUNT(*) DESC LIMIT 1",
          "SELECT c.country FROM races r JOIN circuits c ON c.circuitId = r.circuitId "
          "GROUP BY c.country ORDER BY COUNT(*) DESC LIMIT 1"],
         "distinct circuits (USA 11) or races held there (Italy 95)"),
        ("not_data", "What was the average ticket price at the 2017 races?", None, [],
         "no ticket data"),
    ],
    "european_football_2": [
        ("trusted", "How many players are there?", "11060",
         ["SELECT COUNT(*) FROM Player"], ""),
        ("trusted", "How many leagues are there?", "11",
         ["SELECT COUNT(*) FROM League"], ""),
        ("trusted", "How many matches did the home team win?", "11917",
         ["SELECT COUNT(*) FROM Match WHERE home_team_goal > away_team_goal"], ""),
        ("trusted", "Who is the tallest player?", "Kristof van Hout",
         ["SELECT player_name FROM Player ORDER BY height DESC LIMIT 1"], "208.28 cm"),
        ("trusted", "How many matches were played in the England Premier League in the 2015/2016 season?", "380",
         ["SELECT COUNT(*) FROM Match m JOIN League l ON l.id = m.league_id "
          "WHERE l.name = 'England Premier League' AND m.season = '2015/2016'"], ""),
        ("trusted", "Which player has the highest overall rating?", "Lionel Messi",
         ["SELECT p.player_name FROM Player p JOIN Player_Attributes a ON a.player_api_id = p.player_api_id "
          "ORDER BY a.overall_rating DESC LIMIT 1"], "rating 94"),
        ("two", "How many players are left-footed?", "44733 or 3202",
         ["SELECT COUNT(*) FROM Player_Attributes WHERE preferred_foot = 'left'",
          "SELECT COUNT(DISTINCT player_api_id) FROM Player_Attributes WHERE preferred_foot = 'left'"],
         "Player_Attributes has one row per player per rating date: rows or distinct players"),
        ("not_data", "What is the salary of Lionel Messi?", None, [],
         "no salary data"),
    ],
    "card_games": [
        ("trusted", "How many sets are there?", "551",
         ["SELECT COUNT(*) FROM sets"], ""),
        ("trusted", "Which artist illustrated the most cards?", "John Avon",
         ["SELECT artist FROM cards GROUP BY artist ORDER BY COUNT(*) DESC LIMIT 1"], "1,128 cards"),
        ("trusted", "How many mythic rarity cards are there?", "3200",
         ["SELECT COUNT(*) FROM cards WHERE rarity = 'mythic'"], ""),
        ("trusted", "Which set was released first?", "Limited Edition Alpha",
         ["SELECT name FROM sets ORDER BY releaseDate LIMIT 1"], "1993-08-05"),
        ("trusted", "Which language has the most foreign card entries?", "Japanese",
         ["SELECT language FROM foreign_data GROUP BY language ORDER BY COUNT(*) DESC LIMIT 1"], ""),
        ("two", "How many cards are there?", "56822 or 21738",
         ["SELECT COUNT(*) FROM cards",
          "SELECT COUNT(DISTINCT name) FROM cards"],
         "every printing, or every distinct card name"),
        ("two", "How many cards are banned in modern?", "199 or 46",
         ["SELECT COUNT(DISTINCT l.uuid) FROM legalities l WHERE l.format = 'modern' AND l.status = 'Banned'",
          "SELECT COUNT(DISTINCT c.name) FROM cards c JOIN legalities l ON l.uuid = c.uuid "
          "WHERE l.format = 'modern' AND l.status = 'Banned'"],
         "printings or distinct names, same trap as above"),
        ("not_data", "What is the market price of Black Lotus?", None, [],
         "no price column (purchaseUrls is only links)"),
    ],
}

KIND_LABEL = {"trusted": "Trusted", "two": "Review (two meanings)", "not_data": "Reject (not in the data)",
              "loop": "Learning loop"}


def answer_text(con: sqlite3.Connection, sql: str) -> str:
    rows = con.execute(sql).fetchall()
    if len(rows) != 1 or len(rows[0]) != 1:
        raise ValueError(f"expected one value, got {rows[:3]}")
    return str(rows[0][0])


def check() -> list[str]:
    problems = []
    for db, items in QUESTIONS.items():
        uri = db_file(db).as_uri() + "?mode=ro"
        with sqlite3.connect(uri, uri=True) as con:
            print(f"== {db}")
            for kind, q, expected, sqls, _ in items:
                got = []
                for sql in sqls:
                    try:
                        got.append(answer_text(con, sql))
                    except Exception as e:  # noqa: BLE001 - report every problem, then stop
                        got.append(f"ERROR {e}")
                shown = " or ".join(got) if got else "-"
                print(f"  {kind:<8} {shown:<28} {q}")
                if sqls and shown != expected:
                    problems.append(f"{db}: {q!r} gave {shown}, table says {expected}")
    return problems


def write_files() -> None:
    for db, items in QUESTIONS.items():
        lines = [f"# Demo questions for {db}. One per line. Expected answers: demos/questions/EXPECTED.md",
                 *[q for _, q, *_ in items]]
        text = "\n".join(lines) + "\n"
        (HERE / f"{db}.txt").write_text(text, encoding="utf-8")
        if db == "olist":
            (REPO / "datasets" / "olist" / "demo_questions.txt").write_text(text, encoding="utf-8")

    md = ["# Demo questions and expected answers", "",
          "Made by `python demos/questions/questions.py`; do not edit by hand. "
          "Every SQL here was run on the database and gives the answer shown.", "",
          "Expected level is what we hope Verdict shows. It is not a promise: the model can still "
          "disagree with itself, or agree on a wrong answer.", ""]
    for db, items in QUESTIONS.items():
        md += [f"## {db}", "", "| # | Question | Expected level | Expected answer | Note |",
               "|---|---|---|---|---|"]
        for i, (kind, q, expected, _, note) in enumerate(items, 1):
            md.append(f"| {i} | {q} | {KIND_LABEL[kind]} | {expected or 'cannot answer'} | {note} |")
        md += ["", "SQL checked:", ""]
        for i, (_, q, _, sqls, _) in enumerate(items, 1):
            for j, sql in enumerate(sqls):
                tag = f"{i}" + ("" if len(sqls) == 1 else "AB"[j])
                md.append(f"- {tag}. `{sql}`")
        md.append("")
    (HERE / "EXPECTED.md").write_text("\n".join(md), encoding="utf-8")


if __name__ == "__main__":
    bad = check()
    if bad:
        print("\n".join(["", "Answers do not match the table:", *bad]))
        sys.exit(1)
    write_files()
    print("wrote demos/questions/*.txt, EXPECTED.md and datasets/olist/demo_questions.txt")
