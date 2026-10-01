"""A small fixture database with fully known contents.

Unit tests do not run against BIRD: it is large and slow, and its expected
answers are not known by construction.

Aisha's OS score is NULL on purpose, to exercise NULL handling. The layout
tiny/tiny.sqlite mirrors BIRD's dev_databases/<db_id>/<db_id>.sqlite.
"""

import sqlite3
from pathlib import Path

SETUP = """
CREATE TABLE students (id INTEGER PRIMARY KEY, name TEXT, year INTEGER);
CREATE TABLE marks (id INTEGER PRIMARY KEY, student_id INTEGER,
                    subject TEXT, score REAL);
INSERT INTO students VALUES (1,'Priya',2), (2,'Rahul',2), (3,'Aisha',3);
INSERT INTO marks VALUES (1,1,'DBMS',94.0), (2,2,'DBMS',71.0),
                         (3,1,'OS',88.0), (4,3,'OS',NULL);
"""


def make_tiny_db(folder: Path, db_id: str = "tiny") -> Path:
    d = Path(folder) / db_id
    d.mkdir(parents=True, exist_ok=True)
    db = d / f"{db_id}.sqlite"
    con = sqlite3.connect(db)
    con.executescript(SETUP)
    con.commit()
    con.close()
    return db
