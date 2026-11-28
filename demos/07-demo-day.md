# Demo day: 3 minutes, laptop, wifi off

Kya hai: stage pe chalne wala 3 minute ka flow, uski taiyari, aur backup video ka plan.
Saare sawaal aur unke sahi jawab: [questions/EXPECTED.md](questions/EXPECTED.md).

## Ek din pehle: taiyari (wifi on chalega)

1. Asli model chahiye. `ollama list` mein `verdict-qwen` hona chahiye (fine-tuned). Base
   `qwen2.5-coder:1.5b` se cache mat bharo: cache model ke id se bandhta hai, aur stage pe
   wahi jawab dikhega.
2. Server band karo. `data/app.db` ki copy rakh lo: `data/app.backup.db`.
3. `.env` mein `VERDICT_ADMIN_EMAIL`, `VERDICT_ADMIN_PASSWORD`. Server chalao:
   `uvicorn verdict.api.main:app --port 8000` (frontend build ho, `VITE_USE_MOCK=false`).
4. Cache bharo (admin ke naam se; admin ke sawaal free hain):
   ```
   python scripts/warm_cache.py --db olist datasets/olist/demo_questions.txt
   python scripts/warm_cache.py --db financial demos/questions/financial.txt
   ```
   Har line ka level dekho. Jo EXPECTED.md se alag aaye, use note karo (neeche "Agar level alag aaye").
5. Browser mein ek naya analyst account banao: `demo@verdict.local` (signup, 20 credits).
   Admin ki review queue warm-up ke items se bhari hogi; analyst ki queue saaf rahegi.
   Cache sabke liye common hai, isliye analyst ko bhi turant jawab milega.
6. Server band. Copy: `data/app.db` -> `data/app.clean.db` (yeh stage wali state hai).
7. **Rehearsal**: server chalao, analyst se poora flow ek baar karo (neeche wala). Isse "2017"
   wala sawaal approval ke baad wale knowledge version pe cache ho jaata hai.
8. Server band. `data/app.db` -> `data/app.rehearsed.db`. Phir clean wapas lao aur rehearsal ka
   cache usme daalo:
   ```
   copy data\app.clean.db data\app.db
   python demos/olist/keep_rehearsal_cache.py --rehearsed data/app.rehearsed.db --into data/app.db
   ```
   Ab stage pe approve karte hi 2017 wala sawaal bhi cache se aayega. Screen pe "Answered from cache, first checked at ..."
   dikhega; poochhe toh seedha bolo: "rehearsal mein yahi chala tha, same knowledge ke saath".
9. Wifi band karke ek baar aur check: `/api/health` mein `qwen: true`, `olist: true`.

## Stage pe: 3 minute

Pehle se khula: browser `http://localhost:8000/ask`, analyst se logged in, DB = Olist,
model = Verdict (Qwen). Doosra tab: `/arena`. Wifi band.

| Time | Screen | Karo | Bolo (short) |
|---|---|---|---|
| 0:00-0:20 | Ask | - | "Analyst plain English mein sawaal poochhta hai. Hamara apna model, laptop pe, internet band. Model 8 baar SQL likhta hai, har SQL sandbox mein read-only chalta hai." |
| 0:20-0:50 | Ask | Poochho: **How many orders were canceled?** -> Trusted, 625. Receipt kholo. | "8 mein se itne ek hi jawab pe aaye. Receipt: kaunse checks chale, kaunsi table, kaunsa filter. Jo check nahi chala woh 'off' dikhta hai, tick nahi." |
| 0:50-1:20 | Ask | Poochho: **How many orders were delivered late in 2018?** -> Review. Reasons padho. | "Yahan Verdict pakka nahi hai: 'late' ke do matlab, saal purchase ka ya delivery ka. Isliye jawab chhupaya nahi, review queue mein bheja." |
| 1:20-1:50 | Review -> item | Draft SQL dekho (status delivered, purchase year 2018, 4944). **Approve the draft**. | "Analyst sirf Review items dekhta hai. Approve kiya toh yeh knowledge ban gaya: agle sawaal ke prompt mein example." |
| 1:50-2:15 | Ask | Poochho: **How many orders were delivered late in 2017?** -> Trusted, 2878. | "Milta-julta sawaal ab Trusted. Knowledge checks skip nahi karta: phir bhi 8 attempts chale, bas ab woh ek hi matlab pe agree karte hain." |
| 2:15-2:45 | Arena | Saved run kholo (ya live: apna model free). | "Same sawaal pe base model, SFT, aur hamara model. BIRD dev pe base 24.6%, SFT ke baad 43.5%." |
| 2:45-3:00 | - | - | "Verdict jawab ke saath saboot deta hai, aur jab pakka nahi hota toh bata deta hai. Kamzori bhi batate hain: yeh ek model ka khud se agree karna hai, sahi hone ki guarantee nahi." |

Time bache toh (ya sawaal aaye): **What was our return on ad spend in 2018?** -> Reject,
"data mein ad spend hai hi nahi". Aur **How many customers do we have?** -> do matlab
(99441 orders ke customer ids, 96096 asli log).

## Agar level alag aaye

Pehle padho: [questions/TRIAL-BASE-26NOV.md](questions/TRIAL-BASE-26NOV.md). Base model pe
"canceled" galat Trusted (0) aaya, "late in 2018" Reject aaya (Review nahi), aur approve ke
baad bhi "late in 2017" Reject raha. Yeh flow fine-tuned model pe rehearsal mein pakka karo.

- "canceled" galat aaye: stage pe mat poochho, "How many orders are there?" ya "Which payment
  type is used most often?" lo. Judge kamzori poochhe toh yahi example sach mein dikhao.
- "late in 2018" Reject aaye: tab bhi review queue mein jaata hai. Draft na ho toh sahi SQL
  (EXPECTED.md olist 9) paste karke Run, phir **Approve my fix**.
- Trusted wala Review aaye: koi aur Trusted sawaal lo (EXPECTED.md, olist 1-6). Rehearsal mein
  jo Trusted aaye, wahi stage pe use karo.
- "late in 2018" Trusted aa jaaye: Review ke liye "How many customers do we have?" ya
  "What was the total revenue in 2017?" lo. Learning loop tab bhi same: approve karo, phir
  "What was the total revenue in 2018?" poochho. Isko rehearsal mein pehle check karo.
- Model hi na chale: backup video chalao, ruko mat.

## Backup video plan

Kab banana: rehearsal ke din, cache bharne ke baad, asli model ke saath.

1. Record: OBS (ya Windows Game Bar, Win+G), 1920x1080, 30 fps, browser full screen (F11),
   zoom 125% taaki peeche tak padha jaaye. Mouse highlight on.
2. Wahi upar wala flow, bina awaaz ke ek take. Galti ho toh poora dobara, edit kam se kam.
3. Awaaz alag se record karo (upar ka "Bolo" column), phir jodo. Ya bina awaaz, aur stage pe
   live bolo: yeh zyada safe hai, video ki speed aapke hisaab se.
4. Har step pe 1-2 second ruko, taaki receipt padhne ka time mile. Total 2:45 se kam.
5. Do jagah rakho: laptop pe (`demos/video/` nahi, git mein video mat daalo; Desktop pe) aur
   pen drive pe. Ek copy phone pe bhi.
6. Stage pe video ek tab mein pehle se khula aur paused, taaki 5 second mein switch ho jaaye.

## Stage ke baad

`data/app.backup.db` wapas laana ho toh server band karke copy karo.
