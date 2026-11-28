# Olist database

`datasets/olist/olist.sqlite` (124 MB), built by `python demos/olist/build_olist.py` from the
Kaggle "Brazilian E-Commerce Public Dataset by Olist" (9 CSV files in `datasets/olist/raw/`).
Real orders from a Brazilian online marketplace, September 2016 to October 2018.
`datasets/` is not in git, so this folder keeps the build script and this note.

## Tables

| Table | Rows | One row is | Key |
|---|---|---|---|
| customers | 99,441 | a customer for one order | customer_id |
| orders | 99,441 | an order | order_id |
| order_items | 112,650 | one item in an order | (order_id, order_item_id) |
| payments | 103,886 | one payment of an order (an order can be split) | (order_id, payment_sequential) |
| reviews | 99,224 | a review of an order | (review_id, order_id) |
| products | 32,951 | a product | product_id |
| sellers | 3,095 | a seller | seller_id |
| geolocation | 19,015 | a zip code prefix | zip_code_prefix |

## Foreign keys (declared in the file, checked by `PRAGMA foreign_key_check`: 0 problems)

- orders.customer_id -> customers.customer_id
- order_items.order_id -> orders.order_id
- order_items.product_id -> products.product_id
- order_items.seller_id -> sellers.seller_id
- payments.order_id -> orders.order_id
- reviews.order_id -> orders.order_id

Soft link, not declared (some zip prefixes are missing from geolocation):
customers.customer_zip_code_prefix and sellers.seller_zip_code_prefix -> geolocation.zip_code_prefix.

## What changed from the CSVs

- Table names: `olist_orders_dataset` -> `orders`, `olist_order_payments_dataset` -> `payments`,
  `olist_order_reviews_dataset` -> `reviews`, and so on.
- Typos fixed: `product_name_lenght`, `product_description_lenght` -> `..._length`.
- `products.product_category` is the English name; `product_category_pt` keeps the Portuguese one.
  The translation table is folded in. Two categories had no English name in Kaggle; we named them
  `pc_gamer` and `portable_kitchen_food_processors`. 610 products have no category (NULL).
- geolocation: the CSV has about 1 million rows, many per zip prefix. Now one row per prefix:
  average lat/lng, most common city and state.
- Empty values are NULL. Money and lat/lng are REAL, counts and sizes INTEGER.
- Timestamps are TEXT `YYYY-MM-DD HH:MM:SS`, so `strftime('%Y', ...)` and `julianday()` work.
- Zip prefixes are TEXT so leading zeros stay (`01037`).
- Indexes on every join key and on order status, purchase time, states and category.

## Traps worth knowing (good for demo questions)

- `customer_id` is one per order. The real person is `customer_unique_id`
  (99,441 ids, 96,096 people).
- Revenue can be `price`, `price + freight_value`, or `payments.payment_value`. They differ.
- `order_status` has 8 values: delivered 96,478, shipped, canceled (one l, 625), unavailable,
  invoiced, processing, created, approved.
- `review_id` is not unique alone: 789 reviews cover more than one order.
- Payment types: credit_card, boleto, voucher, debit_card, not_defined.
- No marketing, ad spend, website traffic or stock data.
