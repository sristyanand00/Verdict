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

## 3. Public link on a cloud server (done 26 Nov, tested)

Live at `https://139-84-142-13.sslip.io`. One server runs everything: Caddy (HTTPS) in front of the
backend, which also serves the website; Ollama with the trained and the base Qwen; the databases.
No GPU: an ask with 8 attempts took 13 to 25 seconds.

**Server**: Vultr Cloud Compute, Shared CPU, plan `vhp-4c-8gb` (4 vCPU, 8 GB RAM, 180 GB NVMe,
$48 a month), Bangalore, Ubuntu 24.04 LTS, login by SSH key only. Automatic backups off.
A stopped server is still billed; only destroying it stops the bill.

Steps, as run (as root over SSH):

1. Packages and code:
   ```
   apt-get update && apt-get install -y git python3-venv python3-pip sqlite3 unzip
   git clone https://github.com/sristyanand00/Verdict.git /opt/verdict
   cd /opt/verdict && python3 -m venv .venv && .venv/bin/pip install -e ".[app]"
   ```
2. Ollama and the models:
   ```
   curl -fsSL https://ollama.com/install.sh | sh
   systemctl enable --now ollama
   ollama pull qwen2.5-coder:1.5b                       # the base model, for the Arena
   ollama create verdict-qwen -f /opt/verdict/deploy/Modelfile
   ```
   The trained GGUF (1.6 GB) is not online, so it is copied from the laptop. A home upload line
   dropped a single 1.6 GB `scp` more than once, so it was split into 100 MB parts
   (`split -b 100M`), each part copied with retries, joined with `cat`, and checked with
   `sha256sum`: Ollama's blob file name is the file's SHA-256, so the two must match.
   `deploy/Modelfile` is the laptop's (`ollama show verdict-qwen --modelfile`) with `FROM` changed
   to `/opt/model/verdict-qwen.gguf`.
3. Databases: Olist (`datasets/olist/olist.sqlite`) is copied from the laptop. The BIRD dev
   databases are downloaded on the server (much faster than uploading):
   `curl -LO https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip`, unzip it, unzip the
   `dev_databases.zip` inside, and copy each `<id>.sqlite` to `datasets/dev_databases/<id>/`.
   Check each copy: `sqlite3 <file> "pragma integrity_check"`. An upload cut off half way gives a
   short file that still opens.
4. Website: build it on the laptop (`cd frontend && npm run build`) and copy `frontend/dist` to
   `/opt/verdict/frontend/dist`. The server has no Node.
5. `/opt/verdict/.env` (`chmod 600`), never in git:
   ```
   VERDICT_ADMIN_EMAIL=...
   VERDICT_ADMIN_PASSWORD=...
   GEMINI_API_KEY=...          GEMINI_MODEL=...
   GROQ_API_KEY=...
   VERDICT_UPLOADS=off
   VERDICT_TRUST_PROXY=1
   VERDICT_CORS_ORIGINS=https://139-84-142-13.sslip.io
   VERDICT_MAX_CONCURRENT_ASKS=2
   VERDICT_QUEUE_WAIT_S=150      # from the load test: wait in a rush instead of failing
   ```
6. The app as a service, `/etc/systemd/system/verdict.service`, then
   `systemctl daemon-reload && systemctl enable --now verdict`:
   ```
   [Unit]
   Description=Verdict API and website
   After=network-online.target ollama.service
   Wants=ollama.service

   [Service]
   WorkingDirectory=/opt/verdict
   ExecStart=/opt/verdict/.venv/bin/uvicorn verdict.api.main:app --host 127.0.0.1 --port 8000
   Restart=always
   RestartSec=3

   [Install]
   WantedBy=multi-user.target
   ```
   Bound to 127.0.0.1, so only Caddy can reach it.
7. HTTPS with Caddy (install from Caddy's apt repository). `sslip.io` turns the IP into a name, so
   no domain is needed. `/etc/caddy/Caddyfile`, then `systemctl restart caddy`; Caddy gets the
   Let's Encrypt certificate by itself and renews it:
   ```
   139-84-142-13.sslip.io {
       encode gzip
       reverse_proxy 127.0.0.1:8000 {
           header_up -CF-Connecting-IP
           transport http {
               response_header_timeout 300s
           }
       }
   }
   ```
   Caddy sends each visitor's address in `X-Forwarded-For`, which `VERDICT_TRUST_PROXY=1` reads for
   the login limit. The `CF-Connecting-IP` header is removed so a visitor cannot fake it.
8. Firewall: `ufw allow 22/tcp; ufw allow 80/tcp; ufw allow 443/tcp; ufw --force enable`.
9. Check: `curl -s http://127.0.0.1:8000/api/health` on the server, then the public link, then log
   in and ask one question.
10. Demo cache: `scripts/warm_cache.py --db <id> <questions.txt>` on the server for each database.

**Updating**: `cd /opt/verdict && git pull && systemctl restart verdict`. If the website changed,
build it on the laptop and copy `frontend/dist` again. After changing which model an id points to,
empty the answer cache (`DELETE /api/admin/cache` as the provider): cached answers are keyed by the
model id, not by the file behind it.

## Who provides what

| From | What |
|---|---|
| Training | vLLM server on the GPU PC (address, port, model names) |
| Training | GGUF file and Ollama `Modelfile` |
| Data and demo | `datasets/olist/olist.sqlite` |
| Data and demo | Demo question list for the cache |
| Evaluation | `verdict/engine/thresholds.json` (measured), `results/results.json` with a `tested_trust` entry, `results/arena.json` |
| Frontend | A build that works when served from the backend (`npm run build`) |
