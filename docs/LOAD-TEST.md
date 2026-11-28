# Load test, 26 Nov 2026

How many people can use the public server at the same time.

## Setup

- Server: Vultr Shared CPU `vhp-4c-8gb` (4 vCPU, 8 GB RAM, no GPU), Bangalore.
- Model: the trained Qwen 1.5B (`verdict-qwen`, 8-bit GGUF) on Ollama, 8 attempts per question.
- Server settings: at most 2 questions run at the same time (`VERDICT_MAX_CONCURRENT_ASKS=2`); a
  question waits at most 60 s for a free slot, then gets "busy" (503); time limit 180 s.
- Script: `python scripts/load_test.py --base https://139-84-142-13.sslip.io/api --users 1 5 10 --per-user 2`,
  run from a laptop over home internet. Each user starts at the same moment and asks 2 questions,
  one after the other. Every question is different and runs fresh (no cache), through the full
  pipeline: 8 attempts, running the SQL, grouping, checks. Questions come from the demo lists of
  all five databases.
- Raw results: `data/load_test_server_26nov.json` (not in git).

## Results

| Users at once | Questions | Answered | Busy (503) | Time limit (504) | Seconds per answer: average / median / max | Answers per minute |
|---|---|---|---|---|---|---|
| 1 | 2 | 2 | 0 | 0 | 9.4 / 9.4 / 10.1 | 6.4 |
| 5 | 10 | 10 | 0 | 0 | 50.4 / 52.0 / 76.9 | 4.5 |
| 10 | 20 | 8 | 12 | 0 | 65.8 / 67.7 / 98.6 | 3.0 |

During and after the test the server used about 2.8 GB of its 8 GB of memory. No errors and no
time limits were hit.

## What it means

- **One user**: an answer in about 10 seconds.
- **Five users at once**: everyone gets an answer, but waits about 50 seconds, because only two
  questions run at a time and the CPU is shared by them.
- **Ten users at once**: the server cannot keep up. 12 of 20 questions waited more than 60 seconds
  for a slot and got "busy, try again". The rest were answered in about a minute.
- **The limit is the CPU, not the memory.** The machine answers about 4 to 6 fresh questions a
  minute however many people ask. A repeated question comes from the cache in under a second and
  does not count against this.

## What was changed after the test

- The wait for a free slot is now 150 s instead of 60 s (`VERDICT_QUEUE_WAIT_S=150`), so in a
  rush a question waits longer instead of failing. Caddy allows 300 s per request, so this fits.

## Options for more users

1. A GPU server: the model part of each answer (most of the time) becomes many times faster.
2. Fewer attempts per question (`VERDICT_ATTEMPTS=4`): about half the model time, with weaker
   agreement evidence. The receipt shows the number of attempts, so this stays visible.
3. A bigger CPU plan (8 vCPU): helps less than a GPU, because the model already uses the cores
   it has.
4. Answer the expected questions ahead of time (`scripts/warm_cache.py`), so they come from the cache.

## Usage statistics

The provider sees the same numbers for real use at `GET /api/admin/stats` (see docs/API.md):
questions today, this week and in total, average and p95 time, model time, tokens per model,
failures by kind, and the machine's CPU, memory and disk.
