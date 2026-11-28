# Demo questions and expected answers

Made by `python demos/questions/questions.py`; do not edit by hand. Every SQL here was run on the database and gives the answer shown.

Expected level is what we hope Verdict shows. It is not a promise: the model can still disagree with itself, or agree on a wrong answer.

## olist

| # | Question | Expected level | Expected answer | Note |
|---|---|---|---|---|
| 1 | How many orders are there? | Trusted | 99441 |  |
| 2 | How many orders were canceled? | Trusted | 625 | status text is 'canceled' (one l) |
| 3 | Which payment type is used most often? | Trusted | credit_card | 76,795 of 103,886 payment rows |
| 4 | What is the average review score? | Trusted | 4.09 | scores are 1 to 5 |
| 5 | How many sellers are in the state SP? | Trusted | 1849 |  |
| 6 | Which product category has the most products? | Trusted | bed_bath_table | 3,029 products |
| 7 | How many customers do we have? | Review (two meanings) | 99441 or 96096 | customer_id is one per order; customer_unique_id is the real person |
| 8 | What was the total revenue in 2017? | Review (two meanings) | 6155806.98 or 7142672.43 | price only, or price plus freight. Payments give a third number, 7249746.73 |
| 9 | How many orders were delivered late in 2018? | Learning loop | 4944 | late = delivered after the estimated date; year of purchase. Readings differ (year of delivery: 5676; compare dates only: 4079), so expect Review. Approve this SQL. |
| 10 | How many orders were delivered late in 2017? | Learning loop | 2878 | ask after approving the 2018 one; the approved example should make it Trusted |
| 11 | What was our return on ad spend in 2018? | Reject (not in the data) | cannot answer | no marketing or ad spend table |
| 12 | How many people visited the website last month? | Reject (not in the data) | cannot answer | no web traffic data; the data also ends in October 2018 |

SQL checked:

- 1. `SELECT COUNT(*) FROM orders`
- 2. `SELECT COUNT(*) FROM orders WHERE order_status = 'canceled'`
- 3. `SELECT payment_type FROM payments GROUP BY payment_type ORDER BY COUNT(*) DESC LIMIT 1`
- 4. `SELECT ROUND(AVG(review_score), 2) FROM reviews`
- 5. `SELECT COUNT(*) FROM sellers WHERE seller_state = 'SP'`
- 6. `SELECT product_category FROM products GROUP BY product_category ORDER BY COUNT(*) DESC LIMIT 1`
- 7A. `SELECT COUNT(*) FROM customers`
- 7B. `SELECT COUNT(DISTINCT customer_unique_id) FROM customers`
- 8A. `SELECT ROUND(SUM(oi.price), 2) FROM order_items oi JOIN orders o ON o.order_id = oi.order_id WHERE strftime('%Y', o.order_purchase_timestamp) = '2017'`
- 8B. `SELECT ROUND(SUM(oi.price + oi.freight_value), 2) FROM order_items oi JOIN orders o ON o.order_id = oi.order_id WHERE strftime('%Y', o.order_purchase_timestamp) = '2017'`
- 9. `SELECT COUNT(*) FROM orders WHERE order_status = 'delivered' AND order_delivered_customer_date > order_estimated_delivery_date AND strftime('%Y', order_purchase_timestamp) = '2018'`
- 10. `SELECT COUNT(*) FROM orders WHERE order_status = 'delivered' AND order_delivered_customer_date > order_estimated_delivery_date AND strftime('%Y', order_purchase_timestamp) = '2017'`

## financial

| # | Question | Expected level | Expected answer | Note |
|---|---|---|---|---|
| 1 | How many accounts are there? | Trusted | 4500 |  |
| 2 | How many clients are women? | Trusted | 2645 |  |
| 3 | How many gold cards are there? | Trusted | 88 |  |
| 4 | How many accounts were opened in 1996? | Trusted | 1363 |  |
| 5 | What is the average loan amount? | Trusted | 151410.18 |  |
| 6 | How many loans are not paid back? | Review (two meanings) | 76 or 479 | A = finished OK, B = finished not paid, C = running OK, D = running in debt. 'Not paid back' can mean in trouble (B, D) or simply not finished yet (B, C, D) |
| 7 | Which region has the most accounts? | Trusted | north Moravia | region is the coded column A3; hard for the model because names are coded |
| 8 | What is the credit score of each client? | Reject (not in the data) | cannot answer | no credit score column |

SQL checked:

- 1. `SELECT COUNT(*) FROM account`
- 2. `SELECT COUNT(*) FROM client WHERE gender = 'F'`
- 3. `SELECT COUNT(*) FROM card WHERE type = 'gold'`
- 4. `SELECT COUNT(*) FROM account WHERE strftime('%Y', date) = '1996'`
- 5. `SELECT ROUND(AVG(amount), 2) FROM loan`
- 6A. `SELECT COUNT(*) FROM loan WHERE status IN ('B', 'D')`
- 6B. `SELECT COUNT(*) FROM loan WHERE status != 'A'`
- 7. `SELECT d.A3 FROM account a JOIN district d ON d.district_id = a.district_id GROUP BY d.A3 ORDER BY COUNT(*) DESC LIMIT 1`

## formula_1

| # | Question | Expected level | Expected answer | Note |
|---|---|---|---|---|
| 1 | How many drivers are there? | Trusted | 840 |  |
| 2 | How many races were held in 2009? | Trusted | 17 |  |
| 3 | How many drivers are British? | Trusted | 162 |  |
| 4 | Which driver has won the most races? | Trusted | Michael Schumacher | 91 wins |
| 5 | Which constructor has the most race wins? | Trusted | Ferrari | 229 wins |
| 6 | How many races did Lewis Hamilton win in 2008? | Trusted | 5 |  |
| 7 | Which country has the most circuits? | Review (two meanings) | USA or Italy | distinct circuits (USA 11) or races held there (Italy 95) |
| 8 | What was the average ticket price at the 2017 races? | Reject (not in the data) | cannot answer | no ticket data |

SQL checked:

- 1. `SELECT COUNT(*) FROM drivers`
- 2. `SELECT COUNT(*) FROM races WHERE year = 2009`
- 3. `SELECT COUNT(*) FROM drivers WHERE nationality = 'British'`
- 4. `SELECT d.forename || ' ' || d.surname FROM results r JOIN drivers d ON d.driverId = r.driverId WHERE r.position = 1 GROUP BY r.driverId ORDER BY COUNT(*) DESC LIMIT 1`
- 5. `SELECT c.name FROM results r JOIN constructors c ON c.constructorId = r.constructorId WHERE r.position = 1 GROUP BY c.constructorId ORDER BY COUNT(*) DESC LIMIT 1`
- 6. `SELECT COUNT(*) FROM results r JOIN races ra ON ra.raceId = r.raceId JOIN drivers d ON d.driverId = r.driverId WHERE d.forename = 'Lewis' AND d.surname = 'Hamilton' AND ra.year = 2008 AND r.position = 1`
- 7A. `SELECT country FROM circuits GROUP BY country ORDER BY COUNT(*) DESC LIMIT 1`
- 7B. `SELECT c.country FROM races r JOIN circuits c ON c.circuitId = r.circuitId GROUP BY c.country ORDER BY COUNT(*) DESC LIMIT 1`

## european_football_2

| # | Question | Expected level | Expected answer | Note |
|---|---|---|---|---|
| 1 | How many players are there? | Trusted | 11060 |  |
| 2 | How many leagues are there? | Trusted | 11 |  |
| 3 | How many matches did the home team win? | Trusted | 11917 |  |
| 4 | Who is the tallest player? | Trusted | Kristof van Hout | 208.28 cm |
| 5 | How many matches were played in the England Premier League in the 2015/2016 season? | Trusted | 380 |  |
| 6 | Which player has the highest overall rating? | Trusted | Lionel Messi | rating 94 |
| 7 | How many players are left-footed? | Review (two meanings) | 44733 or 3202 | Player_Attributes has one row per player per rating date: rows or distinct players |
| 8 | What is the salary of Lionel Messi? | Reject (not in the data) | cannot answer | no salary data |

SQL checked:

- 1. `SELECT COUNT(*) FROM Player`
- 2. `SELECT COUNT(*) FROM League`
- 3. `SELECT COUNT(*) FROM Match WHERE home_team_goal > away_team_goal`
- 4. `SELECT player_name FROM Player ORDER BY height DESC LIMIT 1`
- 5. `SELECT COUNT(*) FROM Match m JOIN League l ON l.id = m.league_id WHERE l.name = 'England Premier League' AND m.season = '2015/2016'`
- 6. `SELECT p.player_name FROM Player p JOIN Player_Attributes a ON a.player_api_id = p.player_api_id ORDER BY a.overall_rating DESC LIMIT 1`
- 7A. `SELECT COUNT(*) FROM Player_Attributes WHERE preferred_foot = 'left'`
- 7B. `SELECT COUNT(DISTINCT player_api_id) FROM Player_Attributes WHERE preferred_foot = 'left'`

## card_games

| # | Question | Expected level | Expected answer | Note |
|---|---|---|---|---|
| 1 | How many sets are there? | Trusted | 551 |  |
| 2 | Which artist illustrated the most cards? | Trusted | John Avon | 1,128 cards |
| 3 | How many mythic rarity cards are there? | Trusted | 3200 |  |
| 4 | Which set was released first? | Trusted | Limited Edition Alpha | 1993-08-05 |
| 5 | Which language has the most foreign card entries? | Trusted | Japanese |  |
| 6 | How many cards are there? | Review (two meanings) | 56822 or 21738 | every printing, or every distinct card name |
| 7 | How many cards are banned in modern? | Review (two meanings) | 199 or 46 | printings or distinct names, same trap as above |
| 8 | What is the market price of Black Lotus? | Reject (not in the data) | cannot answer | no price column (purchaseUrls is only links) |

SQL checked:

- 1. `SELECT COUNT(*) FROM sets`
- 2. `SELECT artist FROM cards GROUP BY artist ORDER BY COUNT(*) DESC LIMIT 1`
- 3. `SELECT COUNT(*) FROM cards WHERE rarity = 'mythic'`
- 4. `SELECT name FROM sets ORDER BY releaseDate LIMIT 1`
- 5. `SELECT language FROM foreign_data GROUP BY language ORDER BY COUNT(*) DESC LIMIT 1`
- 6A. `SELECT COUNT(*) FROM cards`
- 6B. `SELECT COUNT(DISTINCT name) FROM cards`
- 7A. `SELECT COUNT(DISTINCT l.uuid) FROM legalities l WHERE l.format = 'modern' AND l.status = 'Banned'`
- 7B. `SELECT COUNT(DISTINCT c.name) FROM cards c JOIN legalities l ON l.uuid = c.uuid WHERE l.format = 'modern' AND l.status = 'Banned'`
