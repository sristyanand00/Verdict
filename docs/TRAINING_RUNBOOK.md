# Verdict training runbook (college PC, 19 Nov to 5 Dec 2026)

This file is the full plan for the training part of Verdict, written so that a
new Claude Code session on the college PC can pick it up and run it with the
user. Read this file first, then `docs/HANDOFF.md` (what was done before) and
`docs/TRAINING_PROTOCOL.md` (method and all numbers so far).

---

## 0. Rules for the Claude session running this

- Explain to the user in **Hinglish**, in plain, short, simple words. One step
  at a time. No dense tables in chat.
- **No emoji or "sticker" characters** anywhere: code, logs, notebook cells,
  commit messages. No AI attribution lines in commits.
- Commit or push **only when the user asks**.
- Stay inside the training files: `verdict/train/`, `scripts/train_*.py`,
  `scripts/pass_rate.py`, `scripts/evaluate.py`, `docs/TRAINING_PROTOCOL.md`,
  this file, and `results/training/`. Other folders belong to other chats
  (frontend, backend, eval, data/demo). If something there must change, tell
  the user which chat should do it.
- After each finished step, add one line to `LOG.md` and update the status
  table in section 10 of this file.
- The college PC is shared. **Work only on drive E:.** C: had only 80 MB free
  on 19 Nov (about 8 GB after cleanup). Never delete anything on C: except temp
  files. Never delete other people's files anywhere.
- Never commit model weights, large `.jsonl` files or API keys.
- Before starting any GPU job, run `nvidia-smi` and check nobody else is using
  the GPU.

---

## 1. The goal

Train the best possible small Qwen model for text-to-SQL and compare it fairly
against:

- Qwen base (no training)
- Qwen SFT
- Qwen SFT + GRPO (our final model)
- Gemini and an OpenAI GPT model (big cloud models, for reference)

All on the **1,534 BIRD dev questions**, with the **same prompt, same time
limit and same scoring** for every model.

### Honest expectations

- Our model: 34.9% on BIRD dev after the first SFT (Kaggle, 5 s limit).
- Realistic target for 1.5B after this plan: about 42 to 48%. With more data
  or a 3B model, maybe 46 to 52%.
- Gemini / GPT will probably score higher (perhaps 55 to 60%; measure it, do
  not assume). That is fine. Our story is: private, free, much better than
  base, and with Verdict its green answers are trustworthy.
- Every number is reported with its 95% range. No win is claimed for a gap
  under 3 to 5 points or one that the paired test does not support.

---

## 2. The machine

- Windows 11, NVIDIA RTX 3060, 12 GB GPU memory. Supports bf16 (Ampere).
- Python 3.11.9, git 2.53, internet and pip work.
- Drives: C: almost full (do not use), **E: 246 GB free (use this)**, F: 17 GB.
- vLLM does not run on Windows. Use Hugging Face generation.
- Speed is roughly a Kaggle T4 or a bit faster. A 7B model is too slow here
  for the deadline; 1.5B is the main track, 3B is an option in week 2.

Environment variables (already set on 19 Nov with `setx`, check they exist):

```
HF_HOME       = E:\hf_cache
PIP_CACHE_DIR = E:\pip_cache
TEMP, TMP     = E:\tmp
```

Check with: `echo $env:HF_HOME $env:TEMP`. If empty, set them again with
`setx` and open a new terminal.

---

## 3. Folder layout on E:

```
E:\verdict\                  the repo (git clone)
E:\verdict\.venv\            Python environment
E:\bird\dev\                 dev.json + dev_databases\
E:\bird\train_dir\           train_all.json + schemas.json + train_databases\
E:\verdict_runs\             all outputs (checkpoints, eval files, logs)
    sft_v2\                  SFT checkpoints (best\, latest\)
    pass_rate\               pass rate output, kept_ids.json
    grpo_v1\                 GRPO checkpoints
    eval\                    eval_<label>.jsonl and _summary.json
    logs\                    one .log file per run
```

---

## 4. Setup (once)

Use a normal PowerShell (admin not needed for this part).

```
E:
cd E:\
git clone https://github.com/sristyanand00/verdict.git
cd E:\verdict
python -m venv .venv
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -e ".[train,dev]"
```

Check the GPU from Python:

```
python -c "import torch; print(torch.__version__, torch.cuda.is_available(), torch.cuda.get_device_name(0), torch.cuda.is_bf16_supported())"
```

Expected: `... True NVIDIA GeForce RTX 3060 True`.

Run the tests:

```
python -m pytest -q
```

Expected: about 210 pass (some may be skipped).

Every new terminal needs:

```
cd E:\verdict
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
$env:VERDICT_DATA_ROOT = "E:\bird\dev"
$env:VERDICT_RESULTS_ROOT = "E:\verdict_runs\eval"
```

---

## 5. Data (once)

BIRD is downloaded from the official site (bird-bench.github.io). If the links
below fail, take the current links from that site.

```
New-Item -ItemType Directory -Force E:\bird, E:\verdict_runs\logs
cd E:\bird
curl.exe -L -o train.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/train.zip
curl.exe -L -o dev.zip https://bird-bench.oss-cn-beijing.aliyuncs.com/dev.zip
tar -xf train.zip
tar -xf dev.zip
```

The zips may contain another zip inside (`train_databases.zip`,
`dev_databases.zip`). Unzip those too with `tar -xf`. Then arrange:

- `E:\bird\dev\dev.json` and `E:\bird\dev\dev_databases\<db>\<db>.sqlite`
  (11 databases, 1,534 questions).
- `E:\bird\train_dir\train_all.json`: an **unchanged copy** of BIRD's
  `train.json`. Question ids are positions in this file, so it must be the
  official file, otherwise the validation split will differ from Kaggle's.
- `E:\bird\train_dir\train_databases\<db>\<db>.sqlite` (all 69 databases).
- `E:\bird\train_dir\schemas.json` containing just `{}`. All databases are on
  disk here, so no saved schemas are needed, but the scripts expect the file.
  Create it with: `Set-Content E:\bird\train_dir\schemas.json "{}" -Encoding ascii`

Check:

```
python -c "import json; print(len(json.load(open(r'E:\bird\train_dir\train_all.json', encoding='utf-8'))))"
(Get-ChildItem E:\bird\train_dir\train_databases -Directory).Count
python -c "import json; print(len(json.load(open(r'E:\bird\dev\dev.json', encoding='utf-8'))))"
```

Expected: 9428, 69, 1534. The zip files can be deleted afterwards to save space.

---

## 6. Code changes needed before the big runs

**Status 19 Nov: items 1 to 4 are done and pushed** (214 tests pass). After
`git pull` on the college PC:

- Precision is chosen automatically (`VERDICT_PRECISION=auto`): bf16 on the
  3060, fp16 on a T4. Force it with `$env:VERDICT_PRECISION = "fp16"` or `"bf16"`.
- `--max-schema-chars` exists in `train_sft.py`, `pass_rate.py`, `train_grpo.py`.
- `evaluate.py` has `--timeout`, `--workers`, `--gen-batch`, and `--rescore`
  (re-score a saved `eval_<label>.jsonl` with other settings, no GPU). Every
  summary now has a 95% range and the settings used. Each row saves the raw
  model text (first 1000 characters) for item 5.
- `pass_rate.py` has `--gen-batch` (questions sampled together).

Items 5 and 6 are still open. The original list:

1. **bf16 option.** Today CUDA always uses float16 weights and float16
   autocast (needed on the T4). On the 3060 use bfloat16 when
   `torch.cuda.is_bf16_supported()` is true: base weights in bf16, autocast
   bf16, no GradScaler. LoRA weights stay fp32. Places: `modeling.py` (line
   with `base_dtype`), `sft.py` (autocast), `grpo.py` (autocast), `rollout.py`
   (autocast). A single `--precision {auto,fp16,bf16}` flag is enough.
2. **`--max-schema-chars` flag** in `train_sft.py`, `pass_rate.py` and
   `train_grpo.py` (`evaluate.py` already has it). The configs have
   `max_schema_chars = 6000`. New runs use **12000**. The value must be the same
   for SFT, pass rate, GRPO and every evaluation, because it changes the
   prompt. Check that `max_total_tokens = 4096` still fits (12,000 characters
   is roughly 3,500 tokens).
3. **`--timeout` and `--workers` flags** in `evaluate.py` (default today 5 s
   and 8 workers). Final numbers use **30 s and 4 workers**.
4. **Batched generation** in `verdict/train/evaluation.py` (left padding, pad
   token set). Check on 50 dev questions that batched and one-at-a-time
   greedy answers agree on at least 98% of questions (tiny numeric
   differences can flip a few). This should make evaluation 3 to 5 times
   faster.
5. **Check that generation stops** at the end of the answer. Print 5 raw
   generations from the old SFT model or the base model. If it keeps writing
   after the SQL, stop on `<|im_end|>` / EOS.
6. **The 2 "blocked" queries** from SFT validation: find which keyword the
   filter caught. If it is a harmless word in a column name or string, report
   it to the user. The filter lives in `verdict/verifier/safety.py`, which is
   not a training file, so the fix belongs to the backend chat.

---

## 7. The runs, in order

### How to run anything long

Long runs must keep going if the Claude session closes. So the user starts
them in a **separate PowerShell window** (not the one Claude uses), does the
"every new terminal" lines from section 4, then puts
`python scripts/train_run.py <log file>` in front of the command. The output
then shows live on screen **and** is saved to the log:

```
python scripts/train_run.py E:\verdict_runs\logs\<name>.log python scripts/<script>.py <args>
```

Example:

```
python scripts/train_run.py E:\verdict_runs\logs\base_v2.log python scripts/evaluate.py --model Qwen/Qwen2.5-Coder-1.5B-Instruct --label base_v2 --max-schema-chars 12000 --timeout 30 --workers 4 --gen-batch 8
```

That window must stay open until the `=== end` line appears. Progress:
evaluation prints a line every 32 questions, SFT every 10 steps, pass rate
every 16 questions.

Watch the same log from another terminal (optional):

```
Get-Content E:\verdict_runs\logs\<name>.log -Wait -Tail 20
```

Before every long run, do a short version first (`--max-steps 20`,
`--max-tasks 20` or `--num-tasks 20`) to catch errors in minutes, not hours.

Keep the PC awake: `powercfg /change standby-timeout-ac 0` and
`powercfg /change hibernate-timeout-ac 0` (needs admin, was planned on 19 Nov).

### Step A. Base model, new settings (baseline)

```
python scripts/evaluate.py --model Qwen/Qwen2.5-Coder-1.5B-Instruct --label base_v2 --max-schema-chars 12000 --timeout 30 --workers 4 --gen-batch 8
```

This is the base number that every later model is compared with.

### Step B. SFT v2 (the biggest gain)

Quick check:

```
python scripts/train_sft.py --train-dir E:\bird\train_dir --checkpoint-dir E:\verdict_runs\sft_v2_test --max-steps 20 --val-size 20 --max-schema-chars 12000
```

Full run (2 epochs over all 9,428 questions, about 1,180 steps of 16):

```
python scripts/train_sft.py --train-dir E:\bird\train_dir --checkpoint-dir E:\verdict_runs\sft_v2 --epochs 2 --max-schema-chars 12000 --eval-every 300 --time-limit-hours 11
```

- Same as Kaggle except: 2 epochs, all 69 databases on disk, schema limit
  12000, bf16.
- Validation split: 200 questions, seed 0 (default). Do not change it.
- If it stops at the time limit, continue with
  `--resume E:\verdict_runs\sft_v2\latest`.
- If it runs out of GPU memory: `--micro-batch-size 1`.
- Expected time: roughly 5 to 8 hours.
- Kaggle SFT v1 validation: 38.0%. SFT v2 should beat it.

Then evaluate on BIRD dev:

```
python scripts/evaluate.py --model E:\verdict_runs\sft_v2\best --label sft_v2 --max-schema-chars 12000 --timeout 30 --workers 4 --gen-batch 8 --baseline E:\verdict_runs\eval\eval_base_v2.jsonl
```

Target: above 40%.

### Step C. Pass rate (pick useful GRPO questions)

```
python scripts/pass_rate.py --train-dir E:\bird\train_dir --model E:\verdict_runs\sft_v2\best --out E:\verdict_runs\pass_rate --max-schema-chars 12000 --gen-batch 2 --time-limit-hours 11
```

- 8 samples per question at temperature 0.9 (same as GRPO).
- Writes `kept_ids.json`: questions solved sometimes but not always.
- Resumable with `--resume`.

### Step D. GRPO from SFT v2

Quick check with `--num-tasks 20 --epochs 1` first, then:

```
python scripts/train_grpo.py --train-dir E:\bird\train_dir --init-adapter E:\verdict_runs\sft_v2\best --task-ids E:\verdict_runs\pass_rate\kept_ids.json --lr 1e-5 --checkpoint-dir E:\verdict_runs\grpo_v1 --max-schema-chars 12000
```

- Same validation split (seed 0).
- Watch the reward and validation accuracy. If validation drops for two
  checks in a row, stop and keep the best checkpoint.

Then evaluate:

```
python scripts/evaluate.py --model <grpo best folder> --label grpo_v1 --max-schema-chars 12000 --timeout 30 --workers 4 --gen-batch 8 --baseline E:\verdict_runs\eval\eval_sft_v2.jsonl
```

Expected gain over SFT v2: about 2 to 5 points. If it is smaller, report it
honestly.

### Version 1 is ready (target 25 Nov)

The best of SFT v2 and GRPO v1 is **Version 1**. Copy its adapter off the
machine (Google Drive, pen drive or a private Hugging Face repo) and tell the
user, so the eval chat can start the trust-engine runs and calibration.

---

## 8. Week 2: make it better (26 Nov to 1 Dec)

Choose with the user after Version 1's numbers. Run one or both:

- **Path A: more data, same 1.5B.** BIRD train plus Spider train (about
  7,000 questions, different databases) and, if time allows, a filtered subset
  of a public synthetic text-to-SQL set. SFT again, then GRPO. Expected gain
  about 3 to 6 points. Needs a loader for Spider in `verdict/data/` (data chat
  or training chat, agree with the user).
- **Path B: Qwen2.5-Coder-3B-Instruct.** Fits on 12 GB with LoRA and gradient
  checkpointing (use `--micro-batch-size 1` if needed). Expected about 5 to 8
  points over 1.5B. Laptop GGUF about 2 GB, so private mode still works, just
  slower. This is a product decision for the user.

Rule: the new model replaces Version 1 only if it is clearly better (more than
3 points on BIRD dev and the paired test agrees). Otherwise Version 1 stays.

---

## 9. Final comparison (2 to 3 Dec) and packaging (4 to 5 Dec)

### Comparison

Models: Qwen base, Qwen SFT (best), Qwen SFT+GRPO (final), Gemini, GPT.

Same for all: 1,534 BIRD dev questions, same prompt, greedy (temperature 0),
schema limit 12000, 30 s limit, 4 workers, same scoring.

Report for each model:

- Execution accuracy with 95% range (Wilson, `verdict/eval/metrics.py`).
- Share of SQL that ran.
- Accuracy per difficulty (simple, moderate, challenging).
- Paired test (McNemar): base vs SFT, SFT vs SFT+GRPO, final Qwen vs Gemini.
- One extra row: final Qwen with 8 samples and majority vote.

Gemini and GPT need an API evaluation script (does not exist yet; add
`--provider` to `scripts/evaluate.py` or a small new script). API keys go in
environment variables, never in files. Check current prices before running;
1,534 calls per model should be cheap.

Save the small summary files in `results/training/` in the repo (big `.jsonl`
files stay on E: and in backup). The eval chat builds `results.json` for the
dashboard from these.

### Packaging for the laptop

1. Merge the LoRA adapter into the base weights (`load_for_inference` already
   merges; save with `save_pretrained`).
2. Convert to GGUF with llama.cpp (`convert_hf_to_gguf.py`), quantise to
   Q4_K_M and Q5_K_M.
3. Ollama `Modelfile` with the same chat template and system prompt.
4. On the laptop: check that answers match the Hugging Face model on 50 dev
   questions, and measure seconds per answer.

---

## 10. Status (update after every step)

| Step | Status | Date | Result |
|---|---|---|---|
| Setup on E: | done | 19 Nov | venv on E:, torch cu128, tests pass (openpyxl installed) |
| BIRD data on E: | done | 19 Nov | 9428 train, 69 dbs, 1534 dev, 11 dbs; zips and __MACOSX removed |
| Code changes (section 6) | items 1-4 done | 19 to 24 Nov | train_run: venv Python fix (5453f11), single Ctrl+C no longer stops a run (db673e9) |
| A. Base v2 eval | done | 23 Nov | 24.6% (range 22.6-26.9), ran 54.9%, 47.6 min |
| B. SFT v2 | done | 19 to 23 Nov | 1146/1146 steps, resumed at 500; validation 23.0% to 49.5% (79.0% ran) |
| B. SFT v2 eval | running | 24 Nov | |
| C. Pass rate | not started | | |
| D. GRPO v1 | not started | | |
| D. GRPO v1 eval | not started | | |
| Version 1 handed over | not started | | |
| Week 2 choice | not started | | |
| Final comparison | not started | | |
| Packaging | not started | | |

---

## 11. Calendar

| Dates | Work |
|---|---|
| 19 Nov | Setup, data, code changes; start SFT v2 overnight |
| 20 Nov | Base v2 and SFT v2 evals; pass rate overnight |
| 21 to 23 Nov | GRPO v1 |
| 24 to 25 Nov | GRPO eval; Version 1 to the eval chat |
| 26 Nov to 1 Dec | Week 2: Path A and/or B |
| 2 to 3 Dec | Final comparison incl. Gemini and GPT |
| 4 to 5 Dec | Packaging, buffer |
