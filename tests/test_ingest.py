import sqlite3

import pandas as pd
import pytest

from tests.fixtures import make_tiny_db
from verdict.engine.ingest import IngestError, MAX_BYTES, clean_name, ingest
from verdict.verifier.execute import execute_query


def write_csv(path, text, encoding="utf-8"):
    path.write_bytes(text.encode(encoding))
    return path


def table_columns(db, table):
    con = sqlite3.connect(db)
    try:
        return [r[1] for r in con.execute(f'PRAGMA table_info("{table}")')]
    finally:
        con.close()


# --- name cleaning --------------------------------------------------------

@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Order Date", "order_date"),
        ("  Amount (INR) ", "amount_inr"),
        ("2024 Sales", "col_2024_sales"),
        ("order", "order_"),
        ("GROUP", "group_"),
        ("", "fallback"),
        ("Unnamed: 3", "fallback"),
        ("%%%", "fallback"),
    ],
)
def test_clean_name(raw, expected):
    assert clean_name(raw, "fallback") == expected


# --- CSV ------------------------------------------------------------------

def test_csv_becomes_queryable_table(tmp_path):
    src = write_csv(
        tmp_path / "Sales Data.csv",
        "Order Date,Amount,City\n2024-03-01,100,Pune\n2024-03-02,250.5,Delhi\n2024-04-01,50,Pune\n",
    )
    result = ingest(src, out_dir=tmp_path / "out")

    assert result.tables == {"sales_data": 3}
    assert result.columns["sales_data"] == {"order_date": "Order Date", "amount": "Amount", "city": "City"}
    # The verifier can query the new database read-only.
    r = execute_query("SELECT SUM(amount) FROM sales_data WHERE city = 'Pune'", result.db_path)
    assert r.ok and r.rows == ((150.0,),)


def test_awkward_headers_are_cleaned_and_deduplicated(tmp_path):
    src = write_csv(tmp_path / "x.csv", "order,Amount,amount,,2024\n1,2,3,4,5\n")
    result = ingest(src, out_dir=tmp_path / "out")
    cols = table_columns(result.db_path, "x")
    assert cols == ["order_", "amount", "amount_2", "column_4", "col_2024"]
    # "Amount" and "amount" are different headers that clean to the same name.
    assert result.columns["x"]["amount"] == "Amount"
    assert result.columns["x"]["amount_2"] == "amount"


def test_windows_encoded_csv(tmp_path):
    src = write_csv(tmp_path / "cafe.csv", "item,price\nCafé latte,120\n", encoding="cp1252")
    result = ingest(src, out_dir=tmp_path / "out")
    r = execute_query("SELECT item FROM cafe", result.db_path)
    assert r.rows == (("Café latte",),)


def test_blank_rows_are_dropped(tmp_path):
    src = write_csv(tmp_path / "s.csv", "a,b\n1,2\n,\n3,4\n")
    assert ingest(src, out_dir=tmp_path / "out").tables == {"s": 2}


def test_empty_csv_is_rejected(tmp_path):
    src = write_csv(tmp_path / "empty.csv", "")
    with pytest.raises(IngestError, match="empty"):
        ingest(src, out_dir=tmp_path / "out")


def test_header_only_csv_is_rejected(tmp_path):
    src = write_csv(tmp_path / "h.csv", "a,b\n")
    with pytest.raises(IngestError, match="no data"):
        ingest(src, out_dir=tmp_path / "out")
    assert list((tmp_path / "out").iterdir()) == []  # no half-built database left behind


# --- Excel ----------------------------------------------------------------

def test_excel_sheets_become_tables(tmp_path):
    src = tmp_path / "book.xlsx"
    with pd.ExcelWriter(src) as w:
        pd.DataFrame({"Product": ["A", "B"], "Qty": [3, 5]}).to_excel(w, sheet_name="Sales", index=False)
        pd.DataFrame({"Name": ["Asha"]}).to_excel(w, sheet_name="Staff List", index=False)
        pd.DataFrame().to_excel(w, sheet_name="Empty", index=False)
    result = ingest(src, out_dir=tmp_path / "out")
    assert result.tables == {"sales": 2, "staff_list": 1}
    r = execute_query("SELECT SUM(qty) FROM sales", result.db_path)
    assert r.rows == ((8,),)


# --- SQLite ---------------------------------------------------------------

def test_sqlite_is_copied_not_moved(tmp_path):
    original = make_tiny_db(tmp_path / "src")
    result = ingest(original, out_dir=tmp_path / "out")
    assert result.db_path != original and original.exists()
    assert result.tables == {"students": 3, "marks": 4}
    assert set(result.columns["marks"]) == {"id", "student_id", "subject", "score"}


def test_fake_sqlite_is_rejected(tmp_path):
    src = tmp_path / "fake.db"
    src.write_text("not a database")
    with pytest.raises(IngestError, match="not a SQLite database"):
        ingest(src, out_dir=tmp_path / "out")


def test_sqlite_without_tables_is_rejected(tmp_path):
    src = tmp_path / "blank.sqlite"
    con = sqlite3.connect(src)
    con.execute("CREATE TABLE t (x)")
    con.execute("DROP TABLE t")  # writes the header but leaves no tables
    con.commit()
    con.close()
    with pytest.raises(IngestError, match="no tables"):
        ingest(src, out_dir=tmp_path / "out")
    assert list((tmp_path / "out").iterdir()) == []


# --- general --------------------------------------------------------------

def test_each_upload_gets_its_own_database(tmp_path):
    src = write_csv(tmp_path / "s.csv", "a\n1\n")
    first = ingest(src, out_dir=tmp_path / "out")
    second = ingest(src, out_dir=tmp_path / "out")
    assert first.db_path != second.db_path


def test_unsupported_and_old_excel(tmp_path):
    for name, msg in [("notes.txt", "Unsupported"), ("old.xls", "Save the file as .xlsx")]:
        src = tmp_path / name
        src.write_text("x")
        with pytest.raises(IngestError, match=msg):
            ingest(src, out_dir=tmp_path / "out")


def test_missing_and_too_large(tmp_path, monkeypatch):
    with pytest.raises(IngestError, match="not found"):
        ingest(tmp_path / "nope.csv", out_dir=tmp_path / "out")
    src = write_csv(tmp_path / "big.csv", "a\n1\n")
    monkeypatch.setattr("verdict.engine.ingest.MAX_BYTES", 1)
    with pytest.raises(IngestError, match="larger than"):
        ingest(src, out_dir=tmp_path / "out")
    assert MAX_BYTES == 50 * 1024 * 1024
