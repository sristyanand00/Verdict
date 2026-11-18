# Verdict: handoff for a new chat

Written 18 Nov 2026. Read this first, then `docs/VERDICT-FINAL-PLAN.md` (the whole product plan) and `docs/TRAINING_PROTOCOL.md` (the training method and all numbers so far).

---

## 1. How to work with the user

- Explain in **Hinglish**, in plain, simple words. One step at a time. Short points, not dense tables.
- The user runs everything on **Kaggle** (and soon a **college GPU**). Claude writes and tests code on the laptop, pushes to GitHub, and gives the user cells or commands. The user pastes the output back, and Claude explains it.
- Claude cannot reach Kaggle or the college machine. Only the laptop repo.
- **No emoji or "sticker" characters anywhere** in code, logs, notebook cells or commit messages. No AI attribution lines in commits.
- Commit or push only when the user asks.
- Tests run locally with: `PYTHONPATH=<scratchpad>/pkgs python -m pytest` (peft was installed into that folder). 210 tests pass.

---

## 2. What Verdict is (one paragraph)

A manager asks a data question. Verdict writes the SQL 8 times, runs each safely (read-only), groups equal results, and decides: green (show), did you mean, can't answer, or yellow/red (send to the analyst inbox). The main engine is our own trained **Qwen2.5-Coder-1.5B**, so it can run privately offline. The full product plan, screens, API and the 20-day schedule (19 Nov to 8 Dec, demo about 18 Dec) are in `docs/VERDICT-FINAL-PLAN.md`.

The training work feeds two things in that plan:
- **Model Arena**: base vs SFT vs SFT+GRPO (vs Gemini) on all 1,534 BIRD dev questions.
- **Trust Dashboard**: green precision (target 90%) and coverage, measured with the best model.

The plan expects the final model's numbers by **days 4 to 6 (22 to 24 Nov)**.

---

## 3. What is done

### Phase 1: practice GRPO on Qwen2.5-0.5B (done, Kaggle T4)
Pipeline checked end to end: prompt, 8 samples, execution reward, one manual update, rehearsal, a 2-epoch run on 300 BIRD dev questions, saving and reloading through a Kaggle commit. These numbers are practice only (trained and checked on BIRD dev). Details in protocol sections 9.1 to 9.5.

Bug found and fixed on the way: an empty SQL answer used to count as "ran" and earned 0.1. Now a query with no result set is an error.

### Phase 2 so far (Qwen2.5-Coder-1.5B-Instruct, Kaggle T4)
- **BIRD train prepared** on Kaggle: 9,428 questions, 69 databases. The 4 largest databases were deleted to fit Kaggle's 20 GB output (bike_share_1, donor, codebase_comments, movie_platform; 564 questions). Their schemas are in `schemas.json`, so SFT still used all questions. Queries can only run on the 65 kept databases (8,864 questions).
- **Validation split**: 200 BIRD train questions, `holdout_split` seed 0. Same split for SFT, pass rate and GRPO. BIRD dev is never trained on.
- **SFT done**: LoRA r 16, alpha 32, 1 epoch, 577 steps of 16, lr 1e-4. About 3.6 hours. On the 200 validation questions: 20.5% to 38.0%.
- **Full BIRD dev evaluation done (step C)**, greedy, 5 s query limit:

| | Base | SFT |
|---|---|---|
| Correct | 20.7% (318) | 34.9% (535) |
| Ran | 42.6% | 67.9% |
| unknown column failures | 644 | 265 |
| timeout failures | 159 | 210 |

Net +217 questions (285 newly right, 68 newly wrong).

Saved on Kaggle: the SFT adapter (in the SFT notebook's commit output, `best/` folder) and `eval_base.jsonl`, `eval_sft.jsonl` plus their `_summary.json` files (in the evaluation notebook's output). Check the exact paths in those notebooks.

### Code added in Phase 2 (all committed except the last protocol edits)
- `verdict/data/loaders.py`: `load_bird_train`, `has_database`.
- `verdict/train/batch.py`: `holdout_split`.
- `verdict/train/data_prep.py`: `SchemaStore` (database or saved `schemas.json`, 6,000 character limit: drop sample rows first, then cut), `render_prompt`, `sql_answer`.
- `verdict/train/modeling.py`: LoRA setup, `load_for_training`, `load_for_inference` (merges the adapter), `completion_token_logprobs`.
- `verdict/train/sft.py`: `SFTConfig`, `SFTTrainer` (resume, keeps best on validation).
- `verdict/train/evaluation.py`: `evaluate_tasks`, `EvalResult` with failure reasons.
- `verdict/train/reward.py`: `ScoreDetail`, `failure_reason`, `details()`.
- `verdict/train/grpo.py`: LoRA, `--init-adapter`, BIRD train mode.
- Scripts: `train_sft.py`, `train_grpo.py`, `evaluate.py`, `pass_rate.py`.

### Kaggle lessons
- Every LoRA notebook's first cell must remove torchao (it breaks peft):
  `rm -rf /usr/local/lib/python3.13/dist-packages/torchao /usr/local/lib/python3.13/dist-packages/torchao-* /usr/local/lib/python3.13/dist-packages/~orchao*`
  Do not use `pip uninstall` for it.
- Long runs go as a commit ("Save & Run All"). Output in `/kaggle/working` is kept (20 GB max) and can be added as input to the next notebook.
- About 30 GPU hours a week, 12 hours per session. TPU does not work with this code.
- After rerunning the clone cell, run `%cd /kaggle/working` first.

### Uncommitted right now
- `docs/TRAINING_PROTOCOL.md` (sections 8.4, 9.6, 9.7 with the SFT and dev results).
- `docs/VERDICT-FINAL-PLAN.md` and `.html` (the new product plan).
- This file.

---

## 4. Open problems found in the dev results

1. **Timeouts (210 for SFT).** Probably partly our measurement: 5 s limit with 8 queries at once on few CPU cores. BIRD's official limit is believed to be about 30 s (not confirmed yet). Fix: re-score the saved SQL with a longer limit. This needs no GPU.
2. **Unknown columns (265 for SFT).** Partly caused by schema shortening: `european_football_2` is cut at 6,000 characters (129 dev questions), and 4 databases lose their sample rows (640 questions). Fix: check per database, then try a larger limit.
3. **SFT generation is slower** (6,044 s vs 3,712 s). Maybe it does not stop at the end of the answer. Check a few raw texts.
4. **2 "blocked" queries** in SFT validation. Maybe the keyword filter catches a harmless word.
5. **Generation is one question at a time in chunks**; batched generation would make evaluation and pass rate much faster.

---

## 5. Next steps for training

Letters follow the plan used in the chat.

**Before or at the college GPU (no GPU needed for the first two):**
1. User downloads `eval_base.jsonl` and `eval_sft.jsonl` from Kaggle into `results/` on the laptop.
2. Re-score both with a 30 s limit and fewer parallel workers; break down unknown columns per database. Update protocol 9.7 with the honest numbers.
3. Add a `--timeout` flag to `scripts/evaluate.py` and fix problems 3 to 5 above if they are real.

**D. Pass rate.** `scripts/pass_rate.py` with the SFT adapter: 8 samples per BIRD train question, keep questions solved sometimes but not always (`kept_ids.json`). Long; resumable with `--resume` and `--time-limit-hours`.

**E. GRPO from the SFT adapter.** `scripts/train_grpo.py --train-dir ... --init-adapter <sft best/> --task-ids kept_ids.json`, lr 1e-5 with LoRA. Same validation split.

**F. Final dev evaluation** of SFT+GRPO on all 1,534 questions, with the same settings as base and SFT. Paired comparison (McNemar) base vs SFT and SFT vs GRPO. If GRPO adds little, report that honestly.

**G. Qwen writer for the trust engine.** The final plan wants an `OpenAICompatWriter` (vLLM on the college GPU, Ollama on the laptop) behind the existing `SQLWriter` interface.

**H. Trust engine on BIRD dev** with the best model, 8 attempts per question.

**I. Calibration.** Fit thresholds on one half, report on the other half. Target green precision 90% (lower end of range at least 85%), coverage at least 30 to 40%. Replace the placeholders in `verdict/engine/thresholds.json`.

**J. Unanswerable test.** Using `verdict/data/unanswerable.py`, including partly missing cases. Target recall 90%, wrongly refused under 5%.

**K. Report.** Fill protocol 8.4 and produce `results.json` for the dashboard.

After that: package the model for the laptop (merge LoRA, GGUF Q4/Q5, Ollama), as in plan days 15 and 16.

---

## 6. College GPU: what was decided and what is still open

The user gets a college GPU today and wants the strongest model with the biggest gain over base.

**Roles:** the user runs commands there and pastes output; Claude writes code, pushes it, explains output. Model files must be saved off the machine afterwards (Google Drive, pen drive or Kaggle dataset).

**First thing on the college machine:** run and paste
```
nvidia-smi
df -h
python --version
```
Also find out: how many hours, internet access, pip install allowed, Linux or Windows (vLLM needs Linux or WSL2).

**Options, to choose once the GPU is known:**
- Same 1.5B, but faster and bigger: SFT for 2 epochs with all 69 databases on disk (no deleted databases), larger schema limit, then pass rate and GRPO much faster than on a T4.
- A bigger model (Qwen2.5-Coder-7B with LoRA) would likely give much higher accuracy, but the plan's private mode runs on the laptop. A 7B GGUF is about 4.5 GB and slower there. This is a product decision for the user.
- Code changes likely needed: bf16 instead of fp16 on newer GPUs (Ampere or later), batched generation, `--timeout` flag, larger `max_schema_chars`.

**Note:** the final plan says "Qwen2.5-Coder-1.5B is being trained now on the college GPUs" and "about 134 tests". In fact SFT was done on Kaggle, GRPO has not started, and 210 tests pass.
