# Deployment plan

How Verdict runs in each of its three setups. The same code runs in all of them. Only a few settings change, and they are all environment variables.

## Settings

| Variable | What it sets | Default |
|---|---|---|
| `VERDICT_QWEN_URL` | Address of the Qwen server (vLLM or Ollama, OpenAI-compatible) | `http://127.0.0.1:11434/v1` (Ollama on this machine). Use 127.0.0.1, not localhost: on Windows, localhost first tries IPv6 and adds about 2 seconds to every call. |
| `VERDICT_QWEN_MODEL` | Model name on that server | `verdict-qwen` |
| `VERDICT_QWEN_BASE_MODEL` | The untrained Qwen shown in the Model Arena next to the trained one. `off` hides it. | `qwen2.5-coder:1.5b` |
| `OPENAI_API_KEY`, `OPENAI_MODEL` | With a key, ChatGPT joins the Model Arena | not set; model `gpt-4o-mini` |
| `GROQ_API_KEY`, `GROQ_MODEL` | With a key, a large open model on Groq (free tier) joins the Model Arena: by default OpenAI's GPT-OSS 120B. Groq retires models; check `GET https://api.groq.com/openai/v1/models` if it stops working. | not set; model `openai/gpt-oss-120b` |
| `VERDICT_MODELS_FILE` | Optional JSON list of models. Replaces the two defaults, for example to list base, SFT and GRPO separately. | not set |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Only if Gemini is used (cloud mode or second model) | read from `.env` |
| `VERDICT_ATTEMPTS` | Attempts per question | `8` |
| `VERDICT_DATABASES` | Databases offered to analysts, comma-separated ids: `olist`, and BIRD dev databases (`financial`, `formula_1`, `european_football_2`, `card_games`, `california_schools`, `codebase_community`, `debit_card_specializing`, `student_club`, `superhero`, `thrombosis_prediction`, `toxicology`) | `olist,financial,formula_1,european_football_2,card_games` |
| `VERDICT_WARM_DATABASES` | `off` skips reading the database files once at start. On by default: the first query on a large file not yet in memory can otherwise take seconds and hit the 5 s query limit. | `on` |
| `VERDICT_OLIST_PATH` | Location of the Olist SQLite file | `datasets/olist/olist.sqlite` |
| `VERDICT_APP_DB` | Location of the app's own database (asks, review queue, knowledge) | `data/app.db` |
| `VERDICT_CORS_ORIGINS` | Website addresses allowed to call the API, comma-separated | `http://localhost:5173,http://127.0.0.1:5173` |
| `VERDICT_DATA_ROOT`, `VERDICT_RESULTS_ROOT`, `VERDICT_UPLOADS_ROOT` | Where BIRD, results files and uploads live | `datasets/`, `results/`, `uploads/` |
| `VERDICT_ADMIN_EMAIL`, `VERDICT_ADMIN_PASSWORD` | The provider (admin) account. Made on server start if no account has that email. Without both, no admin is made; there is no default password. Changing the password here later does not change an existing account. | not set |
| `VERDICT_SIGNUP_CREDITS` | Starting credits for a new account. Set 0 to hand out every credit yourself. | `20` |
| `VERDICT_PRICE_ASK` | Credits for one question (flat, however many attempts) | `1` |
| `VERDICT_CACHE` | `off` answers every question fresh. When on, a repeated question on the same database is answered from the cache until that database's knowledge changes. | `on` |
| `VERDICT_UPLOADS` | `off` turns file uploads off (do this on a public server) | `on` |
| `VERDICT_UPLOAD_TTL_HOURS` | Delete uploaded databases older than this many hours; `0` keeps them | `0` |
| `VERDICT_ASK_TIMEOUT_S` | Stop a question after this many seconds (504, not charged) | `180` |
| `VERDICT_ASK_RATE` | Questions per user per minute (429 after that) | `10` |
| `VERDICT_MAX_CONCURRENT_ASKS` | Fresh questions running at the same time; the rest wait. Keep it low on a CPU-only machine. | `2` |
| `VERDICT_QUEUE_WAIT_S` | How long a question waits for a free slot before 503 "busy" | `60` |
| `VERDICT_ARENA_OUTSIDE` | `off` stops the Model Arena from calling outside models (Gemini, ChatGPT, Groq). Only the provider can run the Arena. | `on` |
| `VERDICT_ARENA_OUTSIDE_ATTEMPTS` | Attempts asked of an outside model in the Arena (8 gives a full verdict; 1 saves quota) | `8` |
| `VERDICT_AUTH_RATE` | Login and signup tries per minute from one address | `10` |
| `VERDICT_TRUST_PROXY` | Set to `1` behind Cloudflare Tunnel, so the rate limit sees each visitor's address (`CF-Connecting-IP`) instead of the tunnel's. Leave unset when the server is reached directly. | not set |

Put these in a `.env` file or the shell, never in code or in git. For example, on the laptop (PowerShell):

```
$env:VERDICT_ADMIN_EMAIL = "you@example.com"
$env:VERDICT_ADMIN_PASSWORD = "<a long password>"
uvicorn verdict.api.main:app --port 8000
```

Run the server as one process (no `--workers`): the login rate limit and the credit hold for running asks live in that process.

Example `VERDICT_MODELS_FILE`, with vLLM serving three versions of Qwen:

```json
[
  {"id": "qwen-grpo", "label": "Qwen 1.5B SFT+GRPO", "kind": "openai", "private": true,
   "base_url": "http://gpu-pc:8000/v1", "model": "qwen-grpo"},
  {"id": "qwen-sft", "label": "Qwen 1.5B SFT", "kind": "openai", "private": true,
   "base_url": "http://gpu-pc:8000/v1", "model": "qwen-sft"},
  {"id": "gemini", "label": "Gemini (cloud)", "kind": "gemini", "private": false}
]
```

## Install (once per machine)

```
python -m venv .venv
.venv\Scripts\activate          (Windows)   or   source .venv/bin/activate
pip install -e ".[app,dev]"
```

## 1. While building

- **Backend** runs on the laptop: `uvicorn verdict.api.main:app --reload --port 8000`
- **Frontend** runs on the laptop: `cd frontend` then `npm run dev`. Vite passes `/api` calls to port 8000.
- **Model**:
  - Qwen on a college GPU PC with vLLM. vLLM needs Linux, so on a Windows PC it runs inside WSL2.
  - Point the backend at it with `VERDICT_QWEN_URL=http://<gpu-pc>:8000/v1`.
  - If the college network blocks the port, use an SSH tunnel: `ssh -L 8001:localhost:8000 <user>@<gpu-pc>`, then use `http://localhost:8001/v1`.
- If the GPU is busy with training, the backend still works with Gemini, or with the tests (which need no model).
- Check: `curl http://localhost:8000/api/health` shows `"qwen": true` under `models`.

## 2. Demo day: everything on the laptop, wifi off

The college computer is not needed on demo day. It is only needed before that, for training and the full evaluation.

1. **Model**:
   - The training step merges the LoRA weights, converts the model to a GGUF file (8-bit q8_0, about 1.6 GB; see docs/TRAINING_RUNBOOK.md) and writes an Ollama `Modelfile`.
   - On the laptop: `ollama create verdict-qwen -f Modelfile`, then `ollama serve`.
   - The default `VERDICT_QWEN_URL` already points at Ollama.
2. **One server for everything**:
   - Build the website once with `cd frontend` then `npm run build`.
   - The backend serves `frontend/dist` itself, so the whole product is one process at `http://localhost:8000`.
3. **Start**: `uvicorn verdict.api.main:app --port 8000`, then open `http://localhost:8000`.
4. **Proof pages**: `results/results.json` and `results/arena.json` come from the evaluation step. They are plain files, so they work offline.
5. **Speed**:
   - Measure how long 8 attempts take on the laptop.
   - If it is too slow, set `VERDICT_ATTEMPTS=4`. The evidence view shows the number of attempts, so this is visible, not hidden.
6. **Demo cache**:
   - The scripted demo questions are answered ahead of time and saved, so a slow or unlucky run cannot break the demo on stage.
   - Build it with `scripts/warm_cache.py` once the demo question list exists.
7. **Rehearsal checklist**:
   - Reboot, turn the wifi off, start Ollama and the backend.
   - Run the full demo 10 times in a row.
   - Check `/api/health`: `qwen` is reachable and `olist` is available.
   - Check the database file hashes are unchanged after the runs.
   - Record the backup video.
8. **Backups**:
   - If the laptop is too slow: the GPU PC over a cable or local network (set `VERDICT_QWEN_URL`).
   - If anything else fails: the recorded video.

## 3. A shareable link (after the demo, if there is time)

- **Frontend** on Vercel (free). Set `VITE_USE_MOCK=false` and point `/api` at the backend address.
- **Backend and vLLM** on the college GPU PC.
  - A Cloudflare Tunnel gives it a public address without opening ports on the college network.
  - Set `VERDICT_CORS_ORIGINS` to the Vercel address.
- **Must add before sharing**, because strangers will use it:
  - a limit on questions per visitor per minute
  - a time limit on every request
  - uploads turned off, or deleted after a day
  - no error details shown to users
- **Weak point**: the link only works while that PC is on. Say so wherever the link is shared.

## Who provides what

| From | What |
|---|---|
| Training | vLLM server on the GPU PC (address, port, model names) |
| Training | GGUF file and Ollama `Modelfile` |
| Data and demo | `datasets/olist/olist.sqlite` |
| Data and demo | Demo question list for the cache |
| Evaluation | `verdict/engine/thresholds.json` (measured), `results/results.json` with a `tested_trust` entry, `results/arena.json` |
| Frontend | A build that works when served from the backend (`npm run build`) |
