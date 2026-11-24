# Training session handoff (24 Nov 2026)

Context for a new Claude session that takes over the **Training** work of Verdict.
Read this file fully, then `docs/TRAINING_RUNBOOK.md` (the step-by-step commands and
status table), then `docs/TRAINING_PROTOCOL.md`. `docs/HANDOFF.md` has the older Kaggle history.

---

## 1. What Verdict is and what Training owns

Verdict is a "trust layer for AI-generated analytics": a model writes SQL for a question
over a database, and Verdict decides how far the answer can be trusted (Trusted / Review /
Reject) using several attempts, receipt checks and a review queue. Arena and Trust Report
pages stay in the product.

The Training part: fine-tune **Qwen2.5-Coder-1.5B-Instruct** on the BIRD text-to-SQL
benchmark (LoRA SFT, then GRPO with an execution reward), and compare fairly, on all
**1,534 BIRD dev questions** with identical settings: base, SFT, SFT+GRPO, optionally an
untrained 7B, Gemini and GPT.

Five parallel Claude sessions, each owns its folders. Do not edit other sessions' files.

- **Training (this one):** `verdict/train/`, `scripts/train_*.py`, `scripts/pass_rate.py`,
  `scripts/evaluate.py`, `scripts/export_model.py`, `scripts/train_run.py`,
  `docs/TRAINING_RUNBOOK.md`, `docs/TRAINING_PROTOCOL.md`, this file, model files and their tests
  (`tests/test_train_run.py`, `tests/test_rollout.py`, `tests/test_grpo.py`, `tests/test_export_model.py`, ...).
- **Frontend:** `frontend/`.
- **Backend + deployment:** `verdict/api`, `verdict/store`, `verdict/engine` (except
  `thresholds.json`), `docs/API.md`, `docs/DEPLOYMENT.md`, `pyproject.toml`, `.gitignore`.
- **Evaluation:** `verdict/eval`, `results/`, `thresholds.json`.
- **Data / demo / testing:** `datasets/olist`, demo questions, slides, plan and review docs, LOG.md housekeeping.

There are many uncommitted files from other sessions in the laptop working tree
(frontend, backend, docs). Never stage, revert or delete them. Commit only your own files,
by path (`git add <paths>`), never `git add -A`.

## 2. Deadlines

- **Demo: 26 Nov 2026.** Uses **SFT v2** (ready). GRPO is not needed for the demo.
- **Whole product finished and deployed: 29 Nov 2026.** The user has promised everything in
  the plan and does not want to drop anything.

## 3. How the user works (important)

- Two machines:
  - **Laptop** (this repo, `c:\Users\Dell\OneDrive\Desktop\verdict`, Windows 11): Claude
    writes and tests code here, commits and **pushes** to GitHub (the user has authorized
    commit and push for training files). The remote moved to `https://github.com/sristyanand00/Verdict.git`;
    pushes still work.
  - **College PC** (Windows 11, RTX 3060 **12 GB**, only the **E:** drive may be used):
    repo at `E:\verdict`, venv `E:\verdict\.venv`, BIRD at `E:\bird\train_dir` and the dev
    set, outputs in `E:\verdict_runs\...`. The PC has no GitHub login: it only does `git pull`.
- On the college PC the user is helped by a **browser Claude** ("computer wala agent").
  The usual output from this session is a **copy-paste prompt for that agent** (in English),
  with exact commands, what to check, and what to report back. The user re-uploads the
  runbook to it after each push.
- Results and big files travel PC -> laptop by Google Drive or pen drive into
  `results\college\` (not committed unless the Eval session decides).
- **Never commit** model weights, adapters, GGUF files, large jsonl files, `.env` files or API keys.
  API keys only as environment variables, never in files under `E:\verdict`, never pasted in chat.
- Shared college PC: never delete other people's files; log out of Google Drive when done.
- Talk to the user in **plain, short, simple Hinglish**, one step at a time, no dense tables.
- No emojis or stickers in code, logs, notebook cells or commit messages.
- Commit messages end with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Keep the user's personal details private (no email in any external request).

## 4. Fixed settings (use the same everywhere)

- Model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`. LoRA r16, alpha 32.
- Prompt: `SYSTEM_INSTRUCTION` plus the "### Database Schema / ### Question / ### Hint" layout
  from `verdict/train/data_prep.py` (`build_prompt`, `render_prompt`). The app must send the
  same prompt or accuracy drops.
- Schema limit: `--max-schema-chars 12000` for SFT, pass rate, GRPO and evaluation.
- Precision: bf16 on the 3060 (Ampere), chosen via `VERDICT_PRECISION` / `amp_dtype()`.
- Validation split: `--val-size 200 --split-seed 0` (must match across SFT, pass rate, GRPO).
- Dev evaluation: greedy, `--max-schema-chars 12000 --timeout 30 --workers 4 --gen-batch 8`;
  report accuracy with a Wilson range, compare models with McNemar (`--baseline`).
- Pass rate / GRPO: 8 samples per question, temperature 0.9. Reward: 1 correct, 0.1 runs but wrong, 0 error.
- Always launch long runs through `scripts/train_run.py <log> python scripts/...`: it shows
  output live, saves a log, uses the venv Python, and one Ctrl+C only warns (two presses within 5 s stop it).

## 5. Done so far

- Kaggle phase (older): base 20.7%, SFT v1 34.9% (6000-char schema, 5 s timeout).
  GRPO practice on a 0.5B model only (it learned to farm the 0.1 "runs" reward; see
  `docs/19-reward-hacking-case-study.md`). GRPO has **never** run on the 1.5B yet.
- College PC setup done (19 Nov), BIRD data in place.
- **Base v2 dev eval** (23 Nov): **24.6%** (22.6-26.9), 54.9% of queries ran, 47.6 min.
- **SFT v2** (19-23 Nov): 2 epochs, 1146 steps of 16, lr 1e-4; resumed at step 500;
  validation 23.0% -> 49.5% (79.0% ran). Adapter: `E:\verdict_runs\sft_v2\best`
  (also zipped to `E:\sft_v2_best.zip`, 206 MB).
- **SFT v2 dev eval** (24 Nov): **43.5%** (41.0-46.0), 87.9% ran; simple 52.0 /
  moderate 33.0 / challenging 22.8; vs base: +353 / -64, net +289 questions; 38.4 min.
  Output `E:\verdict_runs\eval\eval_sft_v2.jsonl`. Biggest remaining error type: unknown column (167).
  43.5% is about the published untrained 7B level (43-51%).
- **Version 1 for the demo = SFT v2.**

Code commits from this session (newest first):

- `8267a07` generation retries in smaller pieces on CUDA out-of-memory (`verdict/train/rollout.py`:
  `generate_ids` -> inner `run()` splits prompts, then completions; `_generate_batch` helper; test added).
- `0f1df04` `scripts/export_model.py` (merge LoRA on CPU, fp16, write Ollama Modelfile) + runbook.
- `57f3bca` runbook status table.
- `db673e9` `train_run.py`: StopGuard (one Ctrl+C warns, two within 5 s stop), child in its own process group.
- `5453f11` `train_run.py`: leading `python` uses `sys.executable` (the venv).
- `ff03593`, `ec0217a`, `cd5d078`: live logs, bf16, schema flag, batched generation, eval timeout and rescore, runbook.

Laptop tests: `python -m pytest tests -q` -> 272 passed, 4 skipped (24 Nov).
(The laptop's main Python needed `pip install sqlglot`; there is also a `.venv` in the repo.)

## 6. Running right now

**Pass rate** on the college PC (started again 24 Nov after an out-of-memory crash at 48/2000):

```
python scripts/train_run.py E:\verdict_runs\logs\pass_rate.log python scripts/pass_rate.py --train-dir E:\bird\train_dir --model E:\verdict_runs\sft_v2\best --out E:\verdict_runs\pass_rate --max-schema-chars 12000 --gen-batch 2 --num-tasks 2000 --time-limit-hours 9 --resume
```

- About 30 s per question (slower than the 12.6 s seen in a 20-question test), so 9 hours
  measures about 1,000 of the 2,000 questions; expect ~500-600 kept. That is enough for one GRPO night.
  The report must say GRPO used a subset. More can be measured later with the same command (`--resume`).
- Exit code 2 = time limit reached (fine). It still writes `E:\verdict_runs\pass_rate\kept_ids.json`.
- The user will paste the summary: "Measured N: never solved A, always solved B, sometimes solved C (kept for GRPO)".

## 7. What is left (Training), in order

1. **Pass rate finishes** -> check the summary and that `kept_ids.json` exists and is non-empty.
2. **GRPO quick check (~15 min):** same command as below plus `--num-tasks 20 --epochs 1`,
   into a separate `--checkpoint-dir E:\verdict_runs\grpo_check`. Purpose: catch out-of-memory in the
   **training (backward) pass** on long prompts. The 8267a07 fix only protects generation, not backward.
   If backward runs out of memory: lower `--micro-batch-size` (default 4) to 2 or 1, and/or `--batch-size`
   (default 4 questions); a code fix (skip or split an over-long group) is in Training's scope.
3. **GRPO v1, one epoch (~6-8 h, one night):**
   ```
   python scripts/train_run.py E:\verdict_runs\logs\grpo_v1.log python scripts/train_grpo.py --train-dir E:\bird\train_dir --init-adapter E:\verdict_runs\sft_v2\best --task-ids E:\verdict_runs\pass_rate\kept_ids.json --lr 1e-5 --epochs 1 --checkpoint-dir E:\verdict_runs\grpo_v1 --max-schema-chars 12000
   ```
   Estimate: ~40-45 s per question (generation ~30 s + learning). Default is 3 epochs (~20 h): too long.
   Checkpoints (`latest/`, `best/`) are saved only at the end of an epoch; there is **no mid-epoch
   resume**, so the PC must not sleep or update (set sleep to Never, pause Windows Update).
   Watch for reward hacking: if the share of "runs but wrong" (0.1) goes up while correct does not,
   that is the Kaggle problem again.
4. **GRPO dev eval (~40 min):**
   ```
   python scripts/train_run.py E:\verdict_runs\logs\eval_grpo_v1.log python scripts/evaluate.py --model E:\verdict_runs\grpo_v1\best --label grpo_v1 --max-schema-chars 12000 --timeout 30 --workers 4 --gen-batch 8 --baseline E:\verdict_runs\eval\eval_sft_v2.jsonl
   ```
   Report accuracy, Wilson range, McNemar vs SFT v2. If GRPO is better, it becomes Version 2.
5. **Export for the laptop (Ollama), CPU only, can run while the GPU is busy** (runbook section 9):
   - `python scripts/export_model.py --adapter E:\verdict_runs\sft_v2\best --out E:\verdict_runs\export\sft_v2`
   - `git clone --depth 1 https://github.com/ggml-org/llama.cpp E:\llama.cpp` and `pip install E:\llama.cpp\gguf-py`
   - `python E:\llama.cpp\convert_hf_to_gguf.py E:\verdict_runs\export\sft_v2\merged --outfile E:\verdict_runs\export\sft_v2\verdict-qwen.gguf --outtype q8_0` (~1.6 GB)
   - Bring `verdict-qwen.gguf` + `Modelfile` (+ `eval_sft_v2.jsonl`) to the laptop; install Ollama;
     `ollama create verdict-qwen -f Modelfile`.
   - Not yet run for real. The merge uses the same code path as evaluate.py, which works on the PC.
   - Laptop check: 50 dev questions through Ollama should match the PC eval closely (parity) and give a
     speed number. Tell Backend: model `verdict-qwen` at `http://localhost:11434/v1`, prompt must match training.
   - If GRPO wins, repeat the export for `grpo_v1\best`.
6. **Scripts promised to the Evaluation session:**
   - generate 8 samples per dev question for the trust engine (format to be given by Eval);
   - Gemini / GPT comparison on the same 1,534 dev questions with the same prompt and scoring
     (API keys only from environment variables).
7. **7B option (waiting for the user's yes/no):** untrained Qwen2.5-Coder-7B needs 4-bit loading
   (bitsandbytes, add a `--load-4bit` flag to evaluate.py); ~15 GB download + 3-5 h eval.
   QLoRA training would be 1.5-2 days; no GRPO on 7B. It competes with GRPO for the single GPU.
   Recommendation given: an untrained 7B eval only if a GPU day is free.
8. **Wrap-up:** final model table (base, SFT v2, GRPO v1, optional 7B, Gemini, GPT) for the report;
   update the runbook status table and LOG.md (training lines only); hand numbers to Eval and Data/demo.

## 8. Things learned the hard way

- `train_run.py` must use the venv Python (old failure: "No module named sqlglot").
- Exit code 1 with no traceback = accidental Ctrl+C while copying text; fixed by StopGuard.
  Tell the user to select text before copying or copy from a second window.
- Pass rate with `--gen-batch 2` x 8 samples crashed on one long prompt (12 GB attention in prefill);
  fixed in 8267a07. GRPO's backward pass has no such protection yet.
- Writing Windows paths through a Python heredoc turned `\v`, `\b`, `\n` into escapes; write such
  text with a quoted heredoc or the Write tool.
- The browser agent may say a new script is missing: the PC has not done `git pull` yet.
- "8 answers and a score" was done only as GRPO practice on 0.5B on Kaggle; on 1.5B, pass rate and GRPO are first runs.

## 9. Product requests that touch Training only lightly

The mentor asked for an Admin / usage analytics panel (requests, latency p50/p95, tokens, cost,
CPU/RAM/GPU, Trusted/Review/Reject split, errors) plus a small load test (1, 5, 10 users).
That is Backend + Frontend work; prompts were already given to those sessions. Training only supplies
model speed numbers (Ollama on the laptop, GPU on the PC) when asked.
