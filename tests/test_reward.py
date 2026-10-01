import pickle

from tests.fixtures import make_tiny_db
from verdict.train.reward import SQLRewardFunction, extract_sql

GOLD = "SELECT name FROM students WHERE year = 2"


def test_extract_sql_takes_last_block():
    text = "first try:\n```sql\nSELECT 1\n```\nactually:\n```sql\nSELECT 2\n```"
    assert extract_sql(text) == "SELECT 2"


def test_extract_sql_bare_text():
    assert extract_sql("SELECT 1") == "SELECT 1"


def test_reward_scale(tmp_path):
    make_tiny_db(tmp_path)
    fn = SQLRewardFunction(db_root=tmp_path)
    out = fn(
        prompts=["q"] * 4,
        completions=[
            "thinking...\n```sql\nSELECT name FROM students WHERE year = 2\n```",  # right
            "```sql\nSELECT name FROM students WHERE year = 3\n```",  # ran, wrong
            "```sql\nSELECT nonsense FROM nowhere\n```",  # broken
            "```sql\nDROP TABLE students\n```",  # attack
        ],
        gold_sql=[GOLD] * 4,
        db_id=["tiny"] * 4,
    )
    assert out == [1.0, 0.1, 0.0, 0.0]


def test_reward_has_variance_in_all_failing_group(tmp_path):
    """The 0.1 tier gives a group of wrong answers non-zero reward variance."""
    make_tiny_db(tmp_path)
    fn = SQLRewardFunction(db_root=tmp_path)
    out = fn(
        prompts=["q"] * 2,
        completions=[
            "```sql\nSELECT name FROM students WHERE year=3\n```",
            "```sql\nSELECT broken FROM\n```",
        ],
        gold_sql=[GOLD] * 2,
        db_id=["tiny"] * 2,
    )
    assert out == [0.1, 0.0]
    assert len(set(out)) > 1


def test_reward_function_pickles(tmp_path):
    """The reward function is sent to worker processes, so it must pickle."""
    fn = pickle.loads(pickle.dumps(SQLRewardFunction(db_root=tmp_path)))
    assert fn.db_root == tmp_path
