# Training handoff (updated 26 Nov 2026)

Context for whoever takes over the **Training** work of Verdict.
Read, in this order:

1. this file;
2. `docs/PROJECT-CONTEXT.md` (the short, current picture of the whole project);
3. `docs/TRAINING_RUNBOOK.md` (exact commands, status table in section 10);
4. `docs/TRAINING_STATUS_FOR_BOOK.md` (every training fact with its date and source);
5. `docs/TRAINING_PROTOCOL.md` (method, settings, the Phase 1 Kaggle results).

`VERDICT-MASTER-CONTEXT.md` (15 Sept) is history only: it describes an older framing and planned
Unsloth + vLLM, which the code does not use. Older guides were removed on 25 Nov (commit `ed0a08a`);
their useful facts are in the files above.

---

## 1. What Verdict is and what Training owns

Verdict is "the trust layer for AI-generated analytics". An analyst asks a question; Verdict's own
model writes the SQL 8 times, runs each attempt read-only, groups equal results, and gives one of
three levels with reasons and a receipt: **Trusted**, **Review** (goes to the analyst's review queue),
**Reject**. Approvals become knowledge. Model Arena and Trust Report pages stay in the product.
Business model (decided 25 Nov): offered as a service; an admin gives analysts accounts with credits.

The Training part: fine-tune **Qwen2.5-Coder-1.5B-Instruct** on BIRD (LoRA SFT, then GRPO with an
execution reward), export it for Ollama on the laptop, and compare fairly on all **1,534 BIRD dev
questions** with identical settings: base, SFT, SFT+GRPO, optionally an untrained 7B, Gemini and GPT.

The project has five parts; each owns its files. Never edit, stage, revert or delete another part's files.

- **Training (this one):** `verdict/train/`, `scripts/train_sft.py`, `scripts/train_grpo.py`,
  `scripts/train_run.py`, `scripts/pass_rate.py`, `scripts/evaluate.py`, `scripts/export_model.py`,
  `docs/TRAINING_RUNBOOK.md`, `docs/TRAINING_PROTOCOL.md`, `docs/TRAINING_STATUS_FOR_BOOK.md`, this file,
  model files, and their tests (`tests/test_train_run.py`, `tests/test_rollout.py`, `tests/test_grpo.py`,
  `tests/test_export_model.py`, ...).
- **Frontend:** `frontend/`.
- **Backend + deployment:** `verdict/api`, `verdict/store`, `verdict/engine` (except `thresholds.json`),
  `docs/API.md`, `docs/DEPLOYMENT.md`, `pyproject.toml`, `.gitignore`.
- **Evaluation:** `verdict/eval`, `results/`, `thresholds.json`.
- **Data / demo / testing:** `datasets/olist`, demo questions, slides, plan and review docs, LOG.md housekeeping.

There is also a study book on Verdict ("The Verdict Book", `docs/VERDICT-BOOK.html` / `.pdf`). It takes
its training facts only from `docs/TRAINING_STATUS_FOR_BOOK.md`, so keep that file correct after every result.

The laptop working tree usually has uncommitted files from other parts. Commit only your own
files, by path (`git add <paths>`), never `git add -A`.

## 2. Time

**No fixed deadlines.** Older notes mention "26 Nov demo" and "29 Nov final"; the user said to ignore
those dates. There are roughly 5 to 10 days of work left from 25 Nov 2026. Order work by importance:
first a working model in the product end to end (export to Ollama), then GRPO and the comparison
numbers, then extras.

## 3. How the user works (important)

- Two machines:
  - **Laptop** (this repo, `c:\Users\Dell\OneDrive\Desktop\verdict`, Windows 11): code is written and tested
    here, and training files are committed and pushed from here (only after the user says yes). Remote:
    `https://github.com/sristyanand00/Verdict.git`.
  - **College PC** (Windows 11, RTX 3060 **12 GB**, only the **E:** drive may be used): repo `E:\verdict`,
    venv `E:\verdict\.venv`, BIRD at `E:\bird\train_dir` and the dev set, outputs in `E:\verdict_runs\...`.
    The PC has no GitHub login: it only does `git pull`.
- Work for the college PC is handed over as a **copy-paste block in English**, with exact commands, what
  to check, and what to report back. After each push the PC needs `git pull` to get the new runbook.
- Results and big files travel PC -> laptop by Google Drive or pen drive into `results\college\`
  (does not exist yet; nothing from the PC has been copied so far).
- **Never commit** weights, adapters, GGUF files, large jsonl files, `.env` files or API keys. API keys only
  as environment variables, never in files under `E:\verdict`, never pasted in messages.
- Shared college PC: never delete other people's files; log out of Google Drive when done.
- Talk to the user in **plain, short, simple Hinglish**, one step at a time, no dense tables.
- No emojis or stickers in code, logs, notebook cells or commit messages.
- **Commit messages: plain, with no `Co-Authored-By` line and no other attribution line.**
  The history was rewritten on 25-26 Nov to remove such lines (all commit ids changed; the ids below
  are the new ones).
- Keep the user's personal details private (no email in any external request).

## 4. Fixed settings (use the same everywhere)

- Model: `Qwen/Qwen2.5-Coder-1.5B-Instruct`. LoRA r16, alpha 32, dropout 0.05.
- Prompt: `SYSTEM_INSTRUCTION` plus the "### Database Schema / ### Question / ### Hint" layout from
  `verdict/train/data_prep.py` (`build_prompt`, `render_prompt`). The app must send the same prompt.
- Schema limit `--max-schema-chars 12000` for SFT, pass rate, GRPO and evaluation.
- Precision: bf16 on the 3060 (`VERDICT_PRECISION` / `amp_dtype()`).
- Validation split `--val-size 200 --split-seed 0` (same for SFT, pass rate, GRPO).
- Dev evaluation: greedy, `--max-schema-chars 12000 --timeout 30 --workers 4 --gen-batch 8`; Wilson range;
  McNemar against a baseline (`--baseline`).
- Pass rate / GRPO: 8 samples per question, temperature 0.9, top-p 0.95, 256 new tokens.
  Reward "sparse": 1.0 correct, 0.1 ran but wrong, 0.0 did not run. Reward query timeout 5 s
  (code default; no flag), while the dev eval uses 30 s.
- GRPO: lr 1e-5 (LoRA), 4 questions per batch, micro-batch 4, advantage = reward - group mean
  (no std division, Dr. GRPO), no KL penalty, checkpoints `latest/` and `best/` only at the end of an epoch.
- Launch every long run through `scripts/train_run.py <log> python scripts/...`: live output, a log file,
  the venv Python, and one Ctrl+C only warns (two within 5 s stop the run).

## 5. Done so far

- Kaggle phase (older): base 20.7%, SFT v1 34.9% (6000-char schema, 5 s timeout). GRPO practice on
  Qwen2.5-0.5B only: it learned to collect the 0.1 "ran" reward (ran-but-wrong 12 -> 29 of 61, correct
  3 -> 5); details in `docs/TRAINING_PROTOCOL.md` sections 9.4-9.5. **GRPO has never run on the 1.5B.**
- College PC setup and BIRD data done (19 Nov).
- **Base v2 dev eval** (23 Nov): **24.6%** (22.6-26.9), 54.9% ran, 47.6 min.
- **SFT v2** (19-23 Nov): 2 epochs, 1146 steps of 16, lr 1e-4, resumed at step 500; validation 23.0% -> 49.5%
  (79.0% ran). Adapter `E:\verdict_runs\sft_v2\best`, also zipped as `E:\sft_v2_best.zip` (206 MB).
- **SFT v2 dev eval** (24 Nov): **43.5%** (41.0-46.0), 87.9% ran; simple 52.0 / moderate 33.0 / challenging 22.8;
  vs base +353 / -64, net +289, McNemar p about 1.7e-49; 38.4 min. Output `E:\verdict_runs\eval\eval_sft_v2.jsonl`.
  Most common error: unknown column (167). 43.5% is about the published untrained 7B level (43-51%).
- **Version 1 for the product = SFT v2.**
- **Pass rate, first try** (24 Nov): 20-question test took 4.2 min (5 never / 4 always / 11 kept). The full run
  (`--num-tasks 2000 --gen-batch 2 --time-limit-hours 9`) crashed after **48/2000** with CUDA out of memory
  (tried to allocate 12.08 GiB in attention prefill; 2 questions x 8 samples with one very long prompt),
  exit 1 after 33.8 min, about 30-33 s per question. Fixed in `e9f3a5b`.
- `docs/TRAINING_STATUS_FOR_BOOK.md` written (25 Nov) for the study book.

Training commits (new ids after the history rewrite, newest first):

- `8d8ee3b` book status file and runbook status (25 Nov).
- `d89feb8` first version of this handoff (24 Nov).
- `e9f3a5b` generation retries in smaller pieces on CUDA out of memory (`verdict/train/rollout.py`: inner
  `run()` splits prompts, then completions; `_generate_batch` helper; test
  `test_out_of_memory_retries_in_smaller_pieces`).
- `82ba8d6` `scripts/export_model.py` (merge LoRA on CPU, fp16, write the Ollama Modelfile) + runbook section 9.
- `bafdc38` runbook status table.
- `9c3ce8e` `train_run.py`: StopGuard (one Ctrl+C warns), child in its own process group.
- `eba24b2` `train_run.py`: a leading `python` runs with `sys.executable` (the venv).
- `1f2aea8`, `38778b9`, `ed315e4`: live logs, bf16, schema flag, batched generation, eval timeout and rescore, runbook.

Other parts since then (for context, not yours): accounts and credits (`f11fe01`), receipt check status
"info" (`0131635`), verifier fix for slow child exit (`6d5ed8f`), answer cache, faster Ollama calls and a demo
cache script `scripts/warm_cache.py` (`3904f9b`), limits for a public server (`adb8c58`), cleanup of unused
files and README fixed to no longer claim Unsloth/vLLM (`ed0a08a`).

Laptop tests on 24 Nov: 272 passed, 4 skipped (the laptop's main Python needed `pip install sqlglot`).

## 6. Current state (unclear parts)

The last output from the college PC was reported on **24 Nov around 14:00**. Since then:

- The pass rate was to be restarted with the same command plus `--resume`:
  ```
  python scripts/train_run.py E:\verdict_runs\logs\pass_rate.log python scripts/pass_rate.py --train-dir E:\bird\train_dir --model E:\verdict_runs\sft_v2\best --out E:\verdict_runs\pass_rate --max-schema-chars 12000 --gen-batch 2 --num-tasks 2000 --time-limit-hours 9 --resume
  ```
  Its start should say "1952 questions to measure (48 already done)". Whether it ran and what it produced:
  **unclear**. Expected: about 1,000 questions in 9 h, about 500-600 kept; exit code 2 = time limit (fine).
- GGUF export: commands given, result **unclear**. Ollama is installed on the laptop (26 Nov, it has
  `qwen2.5-coder:1.5b`) but `verdict-qwen` is not created yet, so no real end-to-end ask with the own model
  has run yet (`docs/PROJECT-CONTEXT.md` section 7 lists this as a blocker).

First thing to do: ask the user for the pass rate summary and the export state, and to copy
`E:\verdict_runs\logs\`, `E:\verdict_runs\pass_rate\` and `E:\verdict_runs\eval\*.jsonl` into `results\college\`.

## 7. What is left (Training), in order of importance

1. **Export SFT v2 for the laptop** (product blocker; CPU only, can run while the GPU is busy; runbook section 9):
   - `python scripts/export_model.py --adapter E:\verdict_runs\sft_v2\best --out E:\verdict_runs\export\sft_v2`
   - `git clone --depth 1 https://github.com/ggml-org/llama.cpp E:\llama.cpp`, `pip install E:\llama.cpp\gguf-py`
   - `python E:\llama.cpp\convert_hf_to_gguf.py E:\verdict_runs\export\sft_v2\merged --outfile E:\verdict_runs\export\sft_v2\verdict-qwen.gguf --outtype q8_0` (~1.6 GB)
   - Bring `verdict-qwen.gguf` + `Modelfile` to the laptop, install Ollama, `ollama create verdict-qwen -f Modelfile`.
   - Check on the laptop: 50 dev questions through Ollama should match the PC eval closely; record seconds for
     1 answer and for 8 answers. Tell Backend: model `verdict-qwen` at `http://127.0.0.1:11434/v1`, prompt must match.
   - `docs/DEPLOYMENT.md` (Backend's file) still says "Q4 or Q5"; ask Backend to change it to q8_0 once done.
     Why q8_0 was picked is not written down anywhere: write the reason in the runbook when you decide it.
2. **Pass rate result** -> check `kept_ids.json` exists and is not empty; record measured, kept, and the spread
   (how many had 1..7 of 8 correct) in the book status file.
3. **GRPO quick check (~15 min):** the GRPO command below plus `--num-tasks 20 --epochs 1` and
   `--checkpoint-dir E:\verdict_runs\grpo_check`. It checks memory in the **training (backward) pass** on long
   prompts, which `e9f3a5b` does not protect. If it runs out of memory: `--micro-batch-size 2` or 1, or
   `--batch-size 2`; a code fix (skip or split an over-long group) is in Training's scope.
4. **GRPO v1, one epoch (~6-8 h, one night; estimate, not measured):**
   ```
   python scripts/train_run.py E:\verdict_runs\logs\grpo_v1.log python scripts/train_grpo.py --train-dir E:\bird\train_dir --init-adapter E:\verdict_runs\sft_v2\best --task-ids E:\verdict_runs\pass_rate\kept_ids.json --lr 1e-5 --epochs 1 --checkpoint-dir E:\verdict_runs\grpo_v1 --max-schema-chars 12000
   ```
   No mid-epoch resume: PC sleep Never, Windows Update paused. Watch reward hacking: if the "ran" share rises
   while "correct" does not, it is the Phase 1 problem again.
5. **GRPO v1 dev eval (~40 min):**
   ```
   python scripts/train_run.py E:\verdict_runs\logs\eval_grpo_v1.log python scripts/evaluate.py --model E:\verdict_runs\grpo_v1\best --label grpo_v1 --max-schema-chars 12000 --timeout 30 --workers 4 --gen-batch 8 --baseline E:\verdict_runs\eval\eval_sft_v2.jsonl
   ```
   If better than SFT v2, export it too and it becomes Version 2.
6. **Scripts promised to the Evaluation part:** 8 samples per dev question for the trust run (format from
   Eval), and a Gemini / GPT comparison on the same 1,534 questions with the same prompt and scoring
   (keys from environment variables).
7. **Optional untrained 7B eval** (waiting for the user's yes/no): 4-bit loading via bitsandbytes (add a
   `--load-4bit` flag to evaluate.py), ~15 GB download, 3-5 h eval. Competes with GRPO for the one GPU.
8. **Wrap-up:** final model table, runbook status, `docs/TRAINING_STATUS_FOR_BOOK.md`, a training line in LOG.md,
   numbers handed to Eval and Data/demo.

## 8. Things learned the hard way

- `train_run.py` must use the venv Python (old failure: "No module named sqlglot").
- Exit code 1 with no traceback = accidental Ctrl+C while copying; fixed by StopGuard. Tell the user to select
  text before copying, or copy from a second window.
- Long prompts x many samples can need more than 12 GB; generation now splits itself, the backward pass does not.
- Writing Windows paths through a Python heredoc turns `\v`, `\b`, `\n` into escapes; use a quoted heredoc or the Write tool.
- If a new script is missing on the college PC, it has not done `git pull` yet.
- "8 answers and a score" was only GRPO practice on 0.5B on Kaggle; on 1.5B, pass rate and GRPO are first runs.
- Do not report anything to the book that did not come from a file or a pasted output; mark the rest "unclear".

## 9. Product requests touching Training only lightly

The mentor asked for an Admin / usage panel (requests, latency p50/p95, tokens, cost, CPU/RAM/GPU,
Trusted/Review/Reject split, errors) and a small load test (1, 5, 10 users). Backend and Frontend build it.
Training only supplies model speed numbers (Ollama on the laptop, GPU on the PC) when asked.
