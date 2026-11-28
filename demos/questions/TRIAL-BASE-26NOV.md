# Trial run, 26 Nov 2026: olist questions with base Qwen

Model: base `qwen2.5-coder:1.5b` (Q4_K_M) on Ollama, laptop CPU, 8 attempts. Not the fine-tuned
model, which is not on the laptop yet. Separate app database, so the real cache was not touched.
Another server was using Ollama at the same time, so times are slower than normal.

| Question | Got | Correct answer | Time |
|---|---|---|---|
| How many orders are there? | Trusted 99,441 | 99441, right | 58 s |
| How many orders were canceled? | **Trusted 0** | 625, **wrong** | 61 s |
| Which payment type is used most often? | Trusted credit_card | right | 40 s |
| What is the average review score? | Trusted 4.09 | right | 10 s |
| How many sellers are in the state SP? | Trusted 1,849 | right | 14 s |
| Which product category has the most products? | Trusted bed_bath_table | right | 21 s |
| How many customers do we have? | Trusted 99,441 | one of the two readings; no split shown | 9 s |
| What was the total revenue in 2017? | Reject (failed) | - | 33 s |
| How many orders were delivered late in 2018? | Reject (low agreement) | - | 28 s |
| How many orders were delivered late in 2017? | Reject (failed) | - | 208 s |
| What was our return on ad spend in 2018? | Reject (failed, 4 of 8 said cannot answer) | right level | 28 s |
| How many people visited the website last month? | Reject (failed) | right level | 36 s |

What we learned:

1. **Wrong but Trusted.** For "canceled", 6 of 8 attempts wrote `order_status = 'CANCELED'`
   (capitals), got 0, and 0 counts as "the answer has values". The one right attempt (625) was
   outvoted. This is the known weakness: the model sees column names, not values, and shared
   mistakes pass. For the backend: a count of 0 could be treated like an empty answer.
2. **Joins break the base model.** Revenue failed 8 of 8: it invents `p.price` on payments.
3. **No two-meanings split** for customers: all 8 used `customers` rows.
4. **Learning loop did not work on base.** After fixing "late in 2018" with the right SQL
   (4944), "late in 2017" gave Reject: 5 of 8 attempts said CANNOT_ANSWER, 1 wrote exactly the
   right SQL (2878). The approved example was in the prompt. For backend and training: the base
   model seems to read the example as a reason to refuse. Check again with the fine-tuned model.

Before demo day: run the same trial with `verdict-qwen` and pick the stage questions from what
really comes out.
