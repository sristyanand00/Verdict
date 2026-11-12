# Demo 01: Trust engine

> Tum ek file aur ek sawaal dete ho. Engine AI se 8 baar SQL likhwata hai, sab SQL tumhare database pe chalata hai, aur ginta hai ki kitne attempts agree karte hain. Usi hisaab se 🟢 / 🟡 / 🔴 / 🚫 deta hai.

**Code:** [verdict/engine/](../verdict/engine/) · **Demo script:** [scripts/trace_ask.py](../scripts/trace_ask.py) · **Sample data:** [examples/sales.csv](../examples/sales.csv)

---

## 1. Kya hai, ek nazar mein

```
 👤 Tum: sales.csv + "Pune mein total sales?"
  │
  ▼
 STEP 0  ingest.py     file → SQLite database (asli file ko haath nahi lagta)
  ▼
 STEP 1  schema.py     tables + columns ke naam (data nahi)
  ▼
 STEP 2  generate.py   prompt banao ("ya SQL likho, ya CANNOT_ANSWER")
  ▼
 STEP 3  llm.py        Gemini se 8 jawab lo          ← sirf yahan AI se baat hoti hai
  ▼
 STEP 4  generate.py   har jawab se SQL nikaalo
  ▼
 STEP 5  group.py      8 SQL chalao (verifier), same answer = same group
  ▼
 STEP 6  trust.py      kitne % agree? thresholds.json ke rules lagao
  ▼
 STEP 7  ask.py        final answer + trust level + SQL
```

### Kaun kya karta hai

| Kaun | Kaam | Kya nahi karta |
|---|---|---|
| **Gemini** | Sirf SQL **likhta** hai | Data nahi dekhta, answer calculate nahi karta, trust decide nahi karta |
| **Verifier** | SQL ko safely **chalata** hai aur answers **compare** karta hai | SQL nahi likhta |
| **trust.py** | **Decide** karta hai ki answer pe kitna bharosa karein | |
| **Database** | Asli **calculation** karta hai (jaise 50000 + 60000 + 40000) | |

> Answer **predict nahi hota, calculate hota hai.** Gemini sirf tarika (SQL) batata hai. Number hamesha tumhare asli data se nikalta hai.

### Har file kyun aisi bani

| File | Kya karti hai | Kyun aise |
|---|---|---|
| [schema.py](../verdict/engine/schema.py) | `sales(order_date TEXT, amount INTEGER, ...)` | Sirf naam bhejte hain, values nahi, taaki user ka data Google tak na jaaye. SQL keywords (jaise `order`) quote hote hain. |
| [generate.py](../verdict/engine/generate.py) | Prompt banana + jawab se SQL nikaalna | `CANNOT_ANSWER` ka raasta deta hai, warna AI har sawaal pe kuch na kuch SQL bana deta. SQL nikaalne ka rule training wala hi hai (`extract_sql`). |
| [llm.py](../verdict/engine/llm.py) | Gemini ko 8 calls, ek saath | Sirf yahi file AI se baat karti hai, toh Qwen lagana ho toh bas yahi badlegi. 429 aaye toh ruk ke retry. Aadhe se zyada calls fail hon toh **error deta hai, jhootha 🔴 nahi**. Cache se dobara chalana free hai. |
| [group.py](../verdict/engine/group.py) | 8 SQL chalao + group banao | Group **answer** se banta hai, SQL ke text se nahi. Har query alag process mein chalti hai aur 5 sec mein kill ho jaati hai. |
| [trust.py](../verdict/engine/trust.py) | 🟢🟡🔴🚫 decide karna | **Khaali answer kabhi 🟢 nahi hota.** Rules code mein nahi, `thresholds.json` mein hain. |
| [thresholds.json](../verdict/engine/thresholds.json) | 🟢 ≥ 75%, 🟡 ≥ 50%, 🚫 > 50% refused | Abhi **placeholder** hain. Phase 2 mein BIRD pe naap ke badlenge. |
| [ask.py](../verdict/engine/ask.py) | Sab steps jodta hai | Har attempt aur group saath rakhta hai, receipt page ke liye. |

---

## 2. Kaise chalayein

```powershell
cd C:\Users\Dell\OneDrive\Desktop\verdict

# Har step pe rukta hai, Enter dabao aage badhne ke liye
.venv\Scripts\python.exe scripts\trace_ask.py examples\sales.csv "What is the total sales in Pune?" --model gemini-3.5-flash-lite --pause
```

| Option | Kya karta hai |
|---|---|
| `--pause` | Har step ke baad Enter ka intezaar karta hai |
| `--model gemini-3.5-flash-lite` | Kaunsa Gemini model use karna hai (default: `.env` ka `GEMINI_MODEL`) |
| `--offline` | Gemini ke bina, 8 pehle se likhe jawab use karta hai. Quota khatam ho tab kaam aata hai. |
| `--no-cache` | Gemini se naye jawab lo. Default mein wahi sawaal dobara chalane pe purane jawab (`scratch/llm_cache`) dikhte hain aur paisa nahi lagta. |
| `-n 8` | Kitne attempts (default 8) |

Bina step-by-step ke, sirf final answer chahiye toh:
```powershell
.venv\Scripts\python.exe scripts\ask.py examples\sales.csv "What is the total sales in Pune?" --show-attempts
```

---

## 3. Step-by-step: asli output

### Sample data ([examples/sales.csv](../examples/sales.csv))

```
Order Date | Amount | City   | Product
2024-01-05 | 50000  | Pune   | Laptop
2024-01-09 | 20000  | Mumbai | Phone
2024-02-11 | 60000  | Pune   | Laptop
2024-02-15 | 15000  | Delhi  | Tablet
2024-03-02 | 40000  | Pune   | Phone
2024-03-20 | 30000  | Mumbai | Laptop
```

### Run A: Offline, "What is the total sales in Pune?"

Isme 8 jawab jaan-boojh ke mixed rakhe gaye hain (5 sahi, 1 galat city, 1 galat column, 1 mana), taaki har cheez dikhe.

**STEP 0: File → database**
```
Built: uploads\479377e57fa0.sqlite
Table 'sales': 6 rows
   column 'Order Date' -> order_date
   column     'Amount' -> amount
   column       'City' -> city
   column    'Product' -> product
```
➡ Space wale naam (`Order Date`) AI baar-baar galat likhta hai, isliye unhe saaf kar diya.

**STEP 1: Tables ka naksha**
```
sales(order_date TEXT, amount INTEGER, city TEXT, product TEXT)
```
➡ "Pune" ya "50000" jaisi koi value nahi bheji gayi.

**STEP 2: Prompt**
```
You write SQLite queries that answer questions about a database.

Database tables:
sales(order_date TEXT, amount INTEGER, city TEXT, product TEXT)

Question: What is the total sales in Pune?

Rules:
- Use only the tables and columns listed above.
- Write one SQLite SELECT query that answers the question.
- Put the query in a ```sql code block.
- If these tables cannot answer the question, reply with only the word CANNOT_ANSWER.
```

**STEP 3: 8 jawab**
```
Reply 1: SELECT SUM(amount) FROM sales WHERE city = 'Pune'
Reply 2: SELECT SUM(amount) FROM sales WHERE city = 'Pune';
Reply 3: SELECT TOTAL(amount) FROM sales WHERE city = 'Pune'        ← alag SQL
Reply 4: Sure. SELECT SUM(amount) AS total ... city IN ('Pune')     ← faltu baat bhi hai
Reply 5: SELECT SUM(s.amount) FROM sales s WHERE s.city = 'Pune'
Reply 6: SELECT SUM(amount) FROM sales WHERE city = 'Mumbai'        ← galat city
Reply 7: SELECT SUM(price) FROM sales WHERE city = 'Pune'           ← galat column
Reply 8: CANNOT_ANSWER                                               ← mana kiya
```

**STEP 4: Har jawab padho**
```
1–7. sql
8.   cannot_answer
```
➡ Reply 4 se "Sure." hat gaya, sirf SQL bacha.

**STEP 5: Chalao + group banao**
```
1. ok      ((150000,),)
2. ok      ((150000,),)
3. ok      ((150000.0,),)      ← .0 hai, phir bhi same group
4. ok      ((150000,),)
5. ok      ((150000,),)
6. ok      ((50000,),)
7. error   OperationalError: no such column: price
8. not run (cannot_answer)

Group 1: [#####...] 5/8  answer=((150000,),)   attempts [1, 2, 3, 4, 5]
Group 2: [#.......] 1/8  answer=((50000,),)    attempts [6]

Refused (CANNOT_ANSWER): 1    Failed: 1
```
➡ Reply 1 aur 3 ka SQL alag hai, par answer same hai, toh ek hi group. Verifier jaanta hai ki `150000 = 150000.0`.
➡ Galat column (reply 7) se crash nahi hua, bas "failed" gina gaya.

**STEP 6: Rules lagao**
```
more than 50% refused  -> CANNOT ANSWER
agreement >= 75% (6/8) -> GREEN
agreement >= 50% (4/8) -> YELLOW
otherwise              -> RED (no answer shown)

Refused 1/8 = 12%
Largest group 5/8 = 62%   empty answer: False
```

**STEP 7: Final answer**
```
Trust:    YELLOW - check before using
Reason:   5 of 8 attempts agree, but not enough agreement to be sure.
Answer:   ((150000,),)
SQL:      SELECT SUM(amount) FROM sales WHERE city = 'Pune'
```
➡ Answer sahi hai, par 3 attempts gadbad the, isliye 🟢 nahi, 🟡 mila. **Doubt ho toh user ko batao**, yahi Verdict ka point hai.

### Run B: Live Gemini, "How many orders were placed in each city?"

```
Model: gemini-3.5-flash-lite
Reply 1–8: SELECT city, COUNT(*) FROM sales GROUP BY city;      (8 ke 8 bilkul same)

Group 1: [########] 8/8  answer=(('Delhi', 1), ('Mumbai', 2), ('Pune', 3))

Trust:    GREEN - trusted
Reason:   8 of 8 attempts agree.
Answer:   (('Delhi', 1), ('Mumbai', 2), ('Pune', 3))
```

### Run C: Live Gemini, "Which city sold the most laptops?" ⚠️ sabse zaroori example

```
Model: gemini-3.5-flash-lite
Reply 1–8: SELECT city FROM sales WHERE product = 'laptops' GROUP BY city ORDER BY ...
                                                   ^^^^^^^^^ data mein 'Laptop' hai

Trust:    YELLOW - check before using
Reason:   8 of 8 attempts agree, but the answer is empty. Check before using.
Answer:   ()
```
➡ **8 ke 8 same the, aur 8 ke 8 galat the.** Agreement 100% tha. Sirf "khaali answer kabhi 🟢 nahi" wale rule ne bachaya. Agar galti se koi galat number aata, toh yeh 🟢 ho jaata.

### Run D: Live Gemini, "How satisfied are customers in Pune?"

```
Trust:    CANNOT ANSWER from this data
Reason:   8 of 8 attempts said this data cannot answer the question.
```
➡ Data mein satisfaction ka column hi nahi hai, toh AI ne sahi se mana kiya.

---

## 4. Khud try karo

| Sawaal | Kya expect karo |
|---|---|
| `How many orders are there?` | 🟢, answer 6 |
| `What is the total sales in Pune?` | 🟢, answer 150000 |
| `How many orders were placed in each city?` | 🟢, 3 rows |
| `Which city sold the most laptops?` | 🟡, khaali answer (laptop/Laptop wali galti) |
| `How satisfied are customers?` | 🚫 |
| `What will sales be next year?` | 🚫 ya 🔴 |
| `What is the average order amount per month?` | Mushkil sawaal, dekho attempts alag aate hain ya nahi |

**Rules badal ke dekho:** [thresholds.json](../verdict/engine/thresholds.json) mein `"green": 0.75` ko `0.5` karo aur Run A (`--offline`) dobara chalao. Ab 5/8 wala answer 🟢 ho jaayega. Isse samajh aata hai ki threshold kitna farak daalta hai. Test ke baad wapas `0.75` kar dena.

**Apni file:**
```powershell
.venv\Scripts\python.exe scripts\trace_ask.py "C:\path\to\file.csv" "tumhara sawaal" --model gemini-3.5-flash-lite --pause
```

---

## 5. Kya seekha (research findings)

**1. Ek model se 8 baar poochna, 8 alag logon se poochne jaisa nahi hai.**
5 sawaal × 2 temperatures pe naapa (`gemini-3.5-flash-lite`):

| Sawaal | Temp 0.8: alag SQL / groups | Temp 1.5: alag SQL / groups |
|---|---|---|
| Sales: Pune total | 1 / [8] | 1 / [8] |
| Sales: most laptops | 1 / [8] | 1 / [8] |
| BIRD challenging #1 | 4 / [6, 2] | 6 / [6, 2] |
| BIRD challenging #2 | 5 / [6] + 2 fail | 3 / [4] + 4 fail |
| BIRD moderate | 4 / [6, 2] | 5 / [4, 3, 1] |

- Aasaan sawaal: 8 ke 8 same, chahe sahi hon ya galat (Run C).
- Mushkil sawaal: attempts bant jaate hain, toh wahan agreement asli signal deta hai.
- Temperature badhane se variety thodi badhi, par **galat SQL bhi zyada** aaye. Isliye 0.8 hi rakha hai.

**2. Agreement ≠ sahi.** Run C mein 8/8 agree karke bhi galat tha. Isliye Phase 2 mein naapna hai ki har agreement level asal mein kitni baar sahi hota hai.

**3. Sudhaarne ke raaste (aage ke experiments):**
- Text columns ki kuch sample values bhejo (`product: Laptop, Phone, Tablet`). Isse Run C wali galti jad se khatam hogi, par thoda data Google tak jaayega (privacy decision).
- Har attempt mein prompt thoda badlo (tables ka order, wording).
- Do alag models se poocho (Gemini + Qwen).

> **Interview line:** "Sampling one model repeatedly gives little real diversity: on easy questions all 8 attempts are identical, even when they're all wrong. So I don't assume agreement means correctness. I measure it, and I add checks like flagging empty answers."

---

## 6. Kharcha

`gemini-3.5-flash-lite`, asli token counts se ($0.30 input / $2.50 output, har 10 lakh tokens pe; $1 ≈ ₹88):

| Kaam | Kharcha |
|---|---|
| 1 call (sales wala sawaal: 102 in, 40 out) | ≈ 1 paisa |
| 1 sawaal, 8 attempts | ≈ 9 paise |
| 1 BIRD sawaal, 8 attempts (avg 540 in) | ≈ 29 paise |
| Phase 2: 200 BIRD sawaal | ≈ ₹58 |

Free tier pe ₹0. Cache wale jawab dobara chalane pe ₹0.

---

## 7. Problems aur unka hal

| Dikha | Matlab | Kya karo |
|---|---|---|
| `429 RESOURCE_EXHAUSTED` / "N of 8 Gemini calls failed" | Gemini ka free quota khatam | Thodi der baad chalao, `--model gemini-3.5-flash-lite` try karo, ya `--offline` |
| `404 NOT_FOUND` model ka | Woh model ab available nahi (jaise `gemini-2.5-flash-lite`) | `--model gemini-3.5-flash-lite` |
| `GEMINI_API_KEY is not set` | `.env` mein key nahi hai | `.env` mein `GEMINI_API_KEY=...` jodo |
| "cached replies reused" aur jawab nahi badle | Purane save kiye jawab dikh rahe hain | `--no-cache` lagao |
| Kuch `[empty]` attempts | Kuch calls fail hui (aadhe se kam) | Normal hai, woh agreement ke khilaaf gine jaate hain |

**Tests:** `.venv\Scripts\python.exe -m pytest -q`. Engine ke tests: `test_engine_schema.py`, `test_generate.py`, `test_llm.py`, `test_group.py`, `test_trust.py`, `test_ask.py`.
