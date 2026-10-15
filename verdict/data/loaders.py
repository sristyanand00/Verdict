
"""Load BIRD benchmark tasks from dev.json.

BIRD ek benchmark dataset hai jisme 1,534 SQL questions hain.
Har question ke paas:
  - question_id: unique number (0 se 1533 tak)
  - question: English mein sawaal
  - SQL (gold_sql): sahi SQL answer
  - db_id: kis database ko use karna hai
  - difficulty: simple, moderate, ya challenging

Ye file jo karta hai:
1. dev.json ko read karta hai
2. Validate karta hai ke sab fields hain
3. Python objects mein convert karta hai (BirdTask)
"""

import json
from dataclasses import dataclass
from pathlib import Path

from verdict import config


@dataclass
class BirdTask:
    """
    DATACLASS kya hota hai:
    - Ye ek template jaise hota hai
    - Har task mein ye exact ye fields hote hain
    - Easy access ke liye structured data
    
    Example:
        task = BirdTask(
            question_id=1,
            db_id="california_schools",
            question="How many schools are there?",
            evidence="",
            gold_sql="SELECT COUNT(*) FROM schools",
            difficulty="simple",
            db_path=Path("datasets/dev_databases/california_schools/california_schools.sqlite")
        )
        
        # Ab tum easily task.question_id likha kar access kar sakte ho
    """

    question_id: int  # Unique ID (0-1533)
    db_id: str  # Database ka naam (ex: "california_schools")
    question: str  # English sawaal
    evidence: str  # Extra hint (kabhi empty hota hai)
    gold_sql: str  # Sahi SQL answer
    difficulty: str  # "simple", "moderate", "challenging"
    db_path: Path  # Database file ka path


def load_bird_dev(dev_json: Path | None = None, data_root: Path | None = None, check_db: bool = True) -> list[BirdTask]:
    """
    FUNCTION kya karta hai:
    1. dev.json file ko read karta hai
    2. Sab questions ko validate karta hai (kya koi field missing to nahi)
    3. BirdTask objects mein convert karta hai
    4. Python list mein return karta hai
    
    EXAMPLE USE:
        from verdict.data.loaders import load_bird_dev
        from verdict import config
        
        tasks = load_bird_dev(config.dev_json())
        print(f"Loaded {len(tasks)} questions")  # Output: Loaded 1534 questions
        
        # Ab tum loop mein iterate kar sakte ho:
        for task in tasks:
            print(task.question)  # Har question print hoga
    
    ARGUMENTS (parameters):
        - dev_json: Path to dev.json file
        - data_root: Jahan databases hain (defaults to config.data_root())
        - check_db: Kya database files exist check karna hai?
    
    RETURNS:
        List of BirdTask objects (1,534 for BIRD dev set)
    
    ERRORS:
        Agar kuch galat ho, ye function error throw karta hai:
        - FileNotFoundError: dev.json nahi mila
        - ValueError: Koi field missing, ya invalid difficulty, ya db file nahi
    """

    if data_root is None:
        # Default value: VERDICT_DATA_ROOT environment variable ya "datasets" folder
        data_root = config.data_root()

    if dev_json is None:
        # Default value: config.dev_json() = datasets/dev.json
        dev_json = config.dev_json()

    dev_json = Path(dev_json)
    if not dev_json.exists():
        raise FileNotFoundError(f"dev.json nahi mila: {dev_json}")

    # JSON file ko read karo
    print(f"📂 Reading {dev_json}...")
    with open(dev_json, encoding="utf-8") as f:
        raw_tasks = json.load(f)  # JSON ko Python dict/list mein convert karo

    if not isinstance(raw_tasks, list):
        raise ValueError("dev.json must be a list of tasks")

    tasks = []
    seen_ids = set()  # Duplicates check karne ke liye
    missing_dbs = []  # Missing database files track karo
    valid_difficulties = {"simple", "moderate", "challenging"}

    # Har task ko loop mein process karo
    for i, raw in enumerate(raw_tasks):
        # ============ STEP 1: Check ke sab required fields hain ============
        required = ["question_id", "db_id", "question", "evidence", "SQL", "difficulty"]
        missing = [f for f in required if f not in raw]
        if missing:
            # Agar koi field missing hai, error throw karo
            raise ValueError(f"Task {i}: missing {missing}")

        # ============ STEP 2: Difficulty validate karo ============
        diff = raw["difficulty"]
        if diff not in valid_difficulties:
            raise ValueError(f"Task {i}: unknown difficulty '{diff}'")

        # ============ STEP 3: Duplicate question_id check karo ============
        qid = raw["question_id"]
        if qid in seen_ids:
            raise ValueError(f"Task {i}: duplicate question_id {qid}")
        seen_ids.add(qid)

        # ============ STEP 4: Database path resolve karo ============
        # config.db_path() yeh function use karta hai:
        # "california_schools" -> "datasets/dev_databases/california_schools/california_schools.sqlite"
        db_path = config.db_path(raw["db_id"], root=data_root)
        
        # Agar file exist nahi karti, list mein add karo (bad mein report karne ke liye)
        if check_db and not db_path.exists():
            missing_dbs.append(f"  {raw['db_id']}: {db_path}")

        # ============ STEP 5: BirdTask object banao ============
        # .strip() matlab: surrounding whitespace remove karo
        # Example: "  SELECT COUNT(*) FROM schools  ".strip() -> "SELECT COUNT(*) FROM schools"
        task = BirdTask(
            question_id=qid,
            db_id=raw["db_id"],
            question=raw["question"].strip(),  # Whitespace remove karo
            evidence=raw["evidence"].strip(),
            gold_sql=raw["SQL"].strip(),
            difficulty=diff,
            db_path=db_path,
        )
        tasks.append(task)

    # ============ STEP 6: Report missing databases ============
    if missing_dbs:
        raise FileNotFoundError(
            f"Missing {len(missing_dbs)} database files:\n" + "\n".join(missing_dbs)
        )

    print(f"✓ Loaded {len(tasks)} tasks")
    return tasks
