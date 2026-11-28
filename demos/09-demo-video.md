# Project demo video: 3 to 4 minutes, landing page to every feature

What this is: the reading script for the OJT "Project Demo Video". No explainer animation:
the video starts on the landing page and goes through the real app, page by page.
Bold lines in quotes are what you say. Lines starting with "Do" are what you click.

Speak slowly. About 520 words of talking, which is about 3 and a half minutes. If a page
loads slowly, keep talking or cut the wait out later.

---

## Before you record

1. Use the demo copy of the app: `http://127.0.0.1:8765`. It has the demo questions ready,
   so answers come back in about a second.
   - Log in with your **provider account** (the admin email and password in `.env`).
     Only the provider sees the Model Arena and Accounts pages, so one login shows everything.
   - If 8765 is not running, ask Claude to start the demo server again.
2. Pick **Olist** as the database on the Ask page.
3. Browser full screen (F11), zoom about 110%. Close other tabs. Notifications off.
4. Keep these ready to paste:
   - `How many orders were canceled?`
   - `How many orders were delivered late in 2018?`
   - `What was our return on ad spend in 2018?`
   - SQL for the review step:
     `SELECT COUNT(*) FROM orders WHERE order_status = 'delivered' AND order_delivered_customer_date > order_estimated_delivery_date AND strftime('%Y', order_purchase_timestamp) = '2018'`
5. Ask only these three questions, in the order of the script. Other questions are not
   ready and can take a minute. Don't ask any question after you approve the fix: approving
   changes what Verdict knows, so the ready answers no longer apply.

---

## 1. Why this app is needed (0:00 to 0:35)

**Do:** Start on the landing page, top of the page. Don't scroll yet.

> "Hi, I'm [name], from [program] at Polaris School of Technology. My OJT project is called
> Verdict.
>
> Companies make decisions from their data. Today, AI tools let anyone ask a question in plain
> English, and the AI writes the SQL query for them.
>
> But there's a problem. When the AI writes a wrong query, nothing breaks. There's no error.
> It still gives back a clean, believable number. The analyst puts it in a report, and the
> manager decides on a wrong number. Nobody can tell the right answers from the wrong ones."

## 2. How Verdict solves it (0:35 to 1:05)

**Do:** Scroll slowly to "Verdict and the analyst need each other", then to the three cards
Trusted, Review, Reject. Skip past the animated flow diagram without stopping.

> "Verdict is a trust layer for AI answers. It doesn't ask the AI once. It asks 8 times, and
> runs every query in a safe, read-only sandbox, so your data can never be changed.
>
> Then it compares the 8 answers and gives a verdict. Trusted, when most of them agree.
> Review, when they disagree or the question can mean two things, so a person checks it.
> And Reject, when the data simply can't answer the question.
>
> The model behind it is our own. We trained it, and it runs on a laptop without the internet."

## 3. Data page (1:05 to 1:15)

**Do:** Click **Open Verdict**. In the left menu click **Data**. Click **Show tables** on Olist.

> "Here are the databases. Olist is a real online store with about 100,000 orders. I can see
> every table, and I can upload my own CSV, Excel or SQLite file."

## 4. Ask: a Trusted answer (1:15 to 1:35)

**Do:** Click **Ask**. Paste `How many orders were canceled?` and press **Ask**.

> "I ask in plain English. Trusted: 625. Right at the top are the reasons: 6 of 8 attempts
> agree, and the answer has values. Below it is the answer and the SQL that was used."

## 5. The receipt (1:35 to 2:15)

**Do:** Click **Open the receipt**. Scroll slowly, top to bottom. Click one group to show its
SQL. At the end, open the **Event log**. Then close the receipt.

> "Every answer has a receipt. At the top I can copy it, download the result as CSV, export
> the SQL, or save the answer.
>
> 'Where this number came from' explains the number in plain words: which table, which filter.
> It's read from the SQL, not guessed.
>
> Here are the 8 attempts. Each dot is one attempt, and same colour means same answer. I can
> open any group and see its SQL.
>
> These are the checks: was it safe, did it run, do the attempts agree, is it empty. A check
> that didn't run says 'not run', never a green tick.
>
> And the event log shows everything that happened to this answer, step by step."

## 6. When the data can't answer (2:15 to 2:25)

**Do:** Paste `What was our return on ad spend in 2018?` and press **Ask**.

> "Now a question this data can't answer. There's no ad spend anywhere in it. Only 2 of the 8
> attempts could even write a working query. So Verdict rejects it. It doesn't make up a
> number."

## 7. A Reject, and the review queue (2:25 to 3:05)

**Do:** Paste `How many orders were delivered late in 2018?` and press **Ask**.

> "A harder question. All 8 queries ran, but they gave 7 different answers. Any one of them
> would look fine on its own. Verdict doesn't show a number. It sends it to the review queue."

**Do:** In the left menu click **Review queue**. Open the "delivered late in 2018" item. Point
at the reasons and the groups. Paste the SQL into the editor, click **Run** (it shows
**4,944**), then click **Approve my fix**.

> "The analyst only looks at the cases Verdict wasn't sure about. Here's why it wasn't
> trusted, and every group of answers. I write the right query and run it. It runs in the same
> read-only sandbox. 4,944. I approve it. I can also save what a word means, like 'late order'."

## 8. Knowledge and Metrics (3:05 to 3:20)

**Do:** Click **Knowledge** in the left menu, then **Metrics**.

> "What I approved is now on the Knowledge page. Similar questions later use it as an
> example. On Metrics, the team saves what words mean in this data, like 'revenue'. Verdict
> learns from the analyst."

## 9. History, Saved, Arena, Accounts (3:20 to 3:45)

**Do:** Click each page in the left menu, 3 to 5 seconds each: **History**, **Saved**,
**Model Arena**, **Accounts**.

> "History keeps every question. Saved answers can be run again, to check if the number
> changed. In the Model Arena, I can send one question to different models and compare them,
> for example our trained model against the original one. And as the provider, I manage the
> accounts and their credits: each question costs one credit."

## 10. Close (3:45 to 4:00)

**Do:** Go back to the Ask page with the Trusted answer, or the landing page.

> "Behind this is a Python backend, a React frontend, our own trained model, and 321
> automated tests.
>
> Verdict gives every AI answer a verdict, shows the evidence, and learns from the analyst.
> Thank you."

---

## If something goes wrong

- **"Failed to fetch" or the page won't load:** the server stopped. Ask Claude to start it
  again.
- **You approved the 2018 item already and want to record again:** the demo copy has to be
  reset first (ask Claude: "reset the demo copy").
- **An answer takes a long time:** you typed a question that isn't ready. Paste it exactly
  from the list above.

## Recording and the 100 MB limit

- Record with OBS or Windows Game Bar (Win+G). Mic close to you, quiet room.
- Record part by part, then join the clips in Clipchamp (built into Windows 11).
- Export at 720p, or shrink it with HandBrake (preset "Fast 720p30"). A 4 minute video
  usually lands well under 100 MB.
- Watch it once before uploading: sound is there, text is readable, it plays to the end.
