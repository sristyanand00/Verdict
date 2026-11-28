"""Build datasets/olist/olist.sqlite from the Kaggle Olist CSV files.

    python demos/olist/build_olist.py
    python demos/olist/build_olist.py --raw path/to/csvs --out path/to/olist.sqlite

The CSVs come from https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
(9 files). Put them in datasets/olist/raw/ first.

What the build changes, and why (the model only sees table and column names):
- Table names lose "olist_" and "_dataset": olist_orders_dataset -> orders.
- Column typos fixed: product_name_lenght -> product_name_length.
- products gets product_category (English). The Portuguese name stays as
  product_category_pt; the small translation table is folded in.
- geolocation has about 1 million rows, many per zip prefix. It is reduced to
  one row per zip prefix (average lat/lng, most common city and state).
- Empty strings become NULL. Prices and lat/lng are REAL, counts INTEGER.
  Timestamps stay TEXT as 'YYYY-MM-DD HH:MM:SS', so date() and strftime() work.
- Zip prefixes stay TEXT, so leading zeros are kept ('01037').
- Primary and foreign keys are declared, and join keys are indexed.

Running it again replaces the file.
"""

from __future__ import annotations

import argparse
import csv
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

SCHEMA = """
CREATE TABLE customers (
    customer_id              TEXT PRIMARY KEY,
    customer_unique_id       TEXT NOT NULL,
    customer_zip_code_prefix TEXT,
    customer_city            TEXT,
    customer_state           TEXT
);
CREATE TABLE sellers (
    seller_id              TEXT PRIMARY KEY,
    seller_zip_code_prefix TEXT,
    seller_city            TEXT,
    seller_state           TEXT
);
CREATE TABLE products (
    product_id                 TEXT PRIMARY KEY,
    product_category           TEXT,
    product_category_pt        TEXT,
    product_name_length        INTEGER,
    product_description_length INTEGER,
    product_photos_qty         INTEGER,
    product_weight_g           INTEGER,
    product_length_cm          INTEGER,
    product_height_cm          INTEGER,
    product_width_cm           INTEGER
);
CREATE TABLE orders (
    order_id                      TEXT PRIMARY KEY,
    customer_id                   TEXT NOT NULL REFERENCES customers(customer_id),
    order_status                  TEXT NOT NULL,
    order_purchase_timestamp      TEXT NOT NULL,
    order_approved_at             TEXT,
    order_delivered_carrier_date  TEXT,
    order_delivered_customer_date TEXT,
    order_estimated_delivery_date TEXT
);
CREATE TABLE order_items (
    order_id            TEXT NOT NULL REFERENCES orders(order_id),
    order_item_id       INTEGER NOT NULL,
    product_id          TEXT NOT NULL REFERENCES products(product_id),
    seller_id           TEXT NOT NULL REFERENCES sellers(seller_id),
    shipping_limit_date TEXT,
    price               REAL NOT NULL,
    freight_value       REAL NOT NULL,
    PRIMARY KEY (order_id, order_item_id)
);
CREATE TABLE payments (
    order_id             TEXT NOT NULL REFERENCES orders(order_id),
    payment_sequential   INTEGER NOT NULL,
    payment_type         TEXT NOT NULL,
    payment_installments INTEGER,
    payment_value        REAL NOT NULL,
    PRIMARY KEY (order_id, payment_sequential)
);
CREATE TABLE reviews (
    review_id               TEXT NOT NULL,
    order_id                TEXT NOT NULL REFERENCES orders(order_id),
    review_score            INTEGER NOT NULL,
    review_comment_title    TEXT,
    review_comment_message  TEXT,
    review_creation_date    TEXT,
    review_answer_timestamp TEXT,
    PRIMARY KEY (review_id, order_id)
);
CREATE TABLE geolocation (
    zip_code_prefix TEXT PRIMARY KEY,
    lat             REAL,
    lng             REAL,
    city            TEXT,
    state           TEXT
);
CREATE INDEX idx_customers_unique   ON customers(customer_unique_id);
CREATE INDEX idx_customers_state    ON customers(customer_state);
CREATE INDEX idx_sellers_state      ON sellers(seller_state);
CREATE INDEX idx_products_category  ON products(product_category);
CREATE INDEX idx_orders_customer    ON orders(customer_id);
CREATE INDEX idx_orders_status      ON orders(order_status);
CREATE INDEX idx_orders_purchase    ON orders(order_purchase_timestamp);
CREATE INDEX idx_items_product      ON order_items(product_id);
CREATE INDEX idx_items_seller       ON order_items(seller_id);
CREATE INDEX idx_reviews_order      ON reviews(order_id);
"""

EXPECTED_ROWS = {
    "customers": 99441, "sellers": 3095, "products": 32951, "orders": 99441,
    "order_items": 112650, "payments": 103886, "reviews": 99224,
}


def rows(raw: Path, name: str) -> list[dict]:
    with open(raw / name, encoding="utf-8-sig", newline="") as f:
        return [{k: (v if v != "" else None) for k, v in r.items()} for r in csv.DictReader(f)]


def num(v, kind=float):
    return None if v is None else kind(float(v))


def build(raw: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".building")
    tmp.unlink(missing_ok=True)
    con = sqlite3.connect(tmp)
    con.executescript(SCHEMA)

    def put(table: str, data: list[tuple]) -> None:
        marks = ",".join("?" * len(data[0]))
        con.executemany(f"INSERT INTO {table} VALUES ({marks})", data)

    put("customers", [(r["customer_id"], r["customer_unique_id"], r["customer_zip_code_prefix"],
                       r["customer_city"], r["customer_state"])
                      for r in rows(raw, "olist_customers_dataset.csv")])
    put("sellers", [(r["seller_id"], r["seller_zip_code_prefix"], r["seller_city"], r["seller_state"])
                    for r in rows(raw, "olist_sellers_dataset.csv")])

    english = {r["product_category_name"]: r["product_category_name_english"]
               for r in rows(raw, "product_category_name_translation.csv")}
    # Two categories have no English name in the Kaggle file; these are ours.
    english.setdefault("pc_gamer", "pc_gamer")
    english.setdefault("portateis_cozinha_e_preparadores_de_alimentos", "portable_kitchen_food_processors")
    put("products", [(r["product_id"], english.get(r["product_category_name"]), r["product_category_name"],
                      num(r["product_name_lenght"], int), num(r["product_description_lenght"], int),
                      num(r["product_photos_qty"], int), num(r["product_weight_g"], int),
                      num(r["product_length_cm"], int), num(r["product_height_cm"], int),
                      num(r["product_width_cm"], int))
                     for r in rows(raw, "olist_products_dataset.csv")])

    put("orders", [(r["order_id"], r["customer_id"], r["order_status"], r["order_purchase_timestamp"],
                    r["order_approved_at"], r["order_delivered_carrier_date"],
                    r["order_delivered_customer_date"], r["order_estimated_delivery_date"])
                   for r in rows(raw, "olist_orders_dataset.csv")])
    put("order_items", [(r["order_id"], int(r["order_item_id"]), r["product_id"], r["seller_id"],
                         r["shipping_limit_date"], float(r["price"]), float(r["freight_value"]))
                        for r in rows(raw, "olist_order_items_dataset.csv")])
    put("payments", [(r["order_id"], int(r["payment_sequential"]), r["payment_type"],
                      num(r["payment_installments"], int), float(r["payment_value"]))
                     for r in rows(raw, "olist_order_payments_dataset.csv")])
    put("reviews", [(r["review_id"], r["order_id"], int(r["review_score"]), r["review_comment_title"],
                     r["review_comment_message"], r["review_creation_date"], r["review_answer_timestamp"])
                    for r in rows(raw, "olist_order_reviews_dataset.csv")])

    by_zip: dict[str, list[dict]] = defaultdict(list)
    for r in rows(raw, "olist_geolocation_dataset.csv"):
        by_zip[r["geolocation_zip_code_prefix"]].append(r)
    geo = []
    for z, rs in sorted(by_zip.items()):
        city = Counter(r["geolocation_city"] for r in rs).most_common(1)[0][0]
        state = Counter(r["geolocation_state"] for r in rs).most_common(1)[0][0]
        geo.append((z, round(statistics.fmean(float(r["geolocation_lat"]) for r in rs), 6),
                    round(statistics.fmean(float(r["geolocation_lng"]) for r in rs), 6), city, state))
    put("geolocation", geo)

    con.commit()
    bad = con.execute("PRAGMA foreign_key_check").fetchall()
    counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in [*EXPECTED_ROWS, "geolocation"]}
    con.execute("VACUUM")
    con.close()

    for t, n in EXPECTED_ROWS.items():
        if counts[t] != n:
            raise SystemExit(f"{t}: {counts[t]} rows, expected {n}")
    if bad:
        raise SystemExit(f"{len(bad)} foreign key problems, first: {bad[0]}")
    out.unlink(missing_ok=True)
    tmp.rename(out)
    for t, n in counts.items():
        print(f"{t:12} {n:>7}")
    print(f"foreign keys: ok\nwrote {out} ({out.stat().st_size / 1e6:.1f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=REPO / "datasets" / "olist" / "raw")
    ap.add_argument("--out", type=Path, default=REPO / "datasets" / "olist" / "olist.sqlite")
    args = ap.parse_args()
    build(args.raw, args.out)


if __name__ == "__main__":
    main()
