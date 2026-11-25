# Training status for the study book

Written 25 Nov 2026 by the Training session, from the files in this repo and the run
outputs the user pasted into the Training chat. Nothing here is estimated unless it says so.

**Where the facts come from.** The training runs happen on the college PC (RTX 3060 12 GB).
Its logs and result files (`E:\verdict_runs\...`) are **not on the laptop**: `results/college/`
does not exist yet. So the sources are:

- repo files and git history (exact);
- `docs/TRAINING_RUNBOOK.md` section 10, filled in from the college PC results (exact as written there);
- console output from the college PC that the user pasted into the Training chat (marked
  "pasted output"). The original log files are on the PC; they should be copied to
  `results/college/` and checked against this page.

The last report from the college PC reached the Training chat on **24 Nov 2026, about 14:00**.
Anything that may have run after that is marked **unclear**.

---

## 0. Already finished before this page (for reference)

| Item | Value | Date | Source |
|---|---|---|---|
| Base v2 on BIRD dev (1,534) | 24.6% correct (Wilson 22.6-26.9), 54.9% ran, 47.6 min | 23 Nov | runbook section 10 |
| SFT v2 training | 1146/1146 steps, resumed at step 500; validation 23.0% -> 49.5% (79.0% ran) | 19-23 Nov | runbook section 10 |
| SFT v2 on BIRD dev (1,534) | 43.5% (Wilson 41.0-46.0), 87.9% ran; simple 52.0, moderate 33.0, challenging 22.8; 38.4 min | 24 Nov | runbook section 10 |
| SFT v2 vs base v2 | 353 became correct, 64 stopped being correct, net +289 | 24 Nov | runbook section 10 |
| McNemar, SFT v2 vs base v2 | exact binomial p = 1.7e-49; chi-square with continuity correction 198.9, p = 3.6e-45 | computed 25 Nov from 353 and 64 | this page (scipy) |
| Most common SFT v2 error | "unknown column", 167 questions | 24 Nov | pasted eval summary (24 Nov); not in a repo file |

Settings for both dev runs: greedy, schema limit 12,000 characters, 30 s query timeout, 4 workers,
generation batch 8 (runbook section 7, steps A and B).

---

## 1. Pass-rate run (`scripts/pass_rate.py` on SFT v2)

**20-question test run**

| Item | Value | Date | Source |
|---|---|---|---|
| Questions | 20 | 24 Nov | pasted output |
| Time | 4.2 min, i.e. 12.6 s per question | 24 Nov | pasted output (12.6 = 4.2 x 60 / 20) |
| Never solved / always solved / kept | 5 / 4 / 11 | 24 Nov | pasted output |
| Spread of the 11 kept (1 of 8 ... 7 of 8) | unclear (not in the pasted output) | | |

**First full run** (`--num-tasks 2000 --gen-batch 2 --time-limit-hours 9`, 8 samples, temperature 0.9)

| Item | Value | Date | Source |
|---|---|---|---|
| Result | **stopped: CUDA out of memory** | 24 Nov, ended 07:22:22 | pasted output of the PC log |
| Error | `torch.OutOfMemoryError: CUDA out of memory. Tried to allocate 12.08 GiB`; 9.78 GiB allocated by PyTorch, 4.24 GiB reserved but unallocated; raised in `scaled_dot_product_attention` during the prefill of `model.generate` | 24 Nov | pasted output |
| Exit code, duration | exit code 1, 33.8 minutes | 24 Nov | pasted output (`=== end` line) |
| Questions measured before the crash | 48 of 2000 (saved in `E:\verdict_runs\pass_rate\pass_rates.jsonl`) | 24 Nov | pasted output (last progress line "measured 48/2000") |
| Speed | progress lines: 16 in 8 min, 32 in 16 min, 48 in 26 min, so about 30-33 s per question (the script prints whole minutes) | 24 Nov | pasted output |
| Kept from these 48, and their spread | unclear (`pass_rates.jsonl` is on the PC) | | |

Cause: with `--gen-batch 2`, 2 questions x 8 samples = 16 sequences were generated together, and one
very long prompt made the attention step need 12 GB. Fix: commit `8267a07` (24 Nov):
`verdict/train/rollout.py` now frees memory and retries in smaller pieces (fewer questions, then fewer
samples at a time) instead of crashing. Test: `tests/test_rollout.py::test_out_of_memory_retries_in_smaller_pieces`.

**Restarted run** (same command plus `--resume`)

| Item | Value |
|---|---|
| Started? finished? | unclear: the restart command was given on 24 Nov; no output from it has reached the Training chat |
| Questions measured, kept, spread (1..7 of 8) | unclear |
| Seconds per question | unclear for this run (first run: about 30-33 s) |

---

## 2. GRPO on Qwen2.5-Coder-1.5B

| Item | Value |
|---|---|
| 20-question quick check | unclear (planned; not reported as run). Peak GPU memory and OOM: unclear |
| Full GRPO v1 | unclear; last known state on 24 Nov: not started (it needs `kept_ids.json` from the pass rate) |
| Per-epoch reward, ran share, correct share, validation accuracy | not available (no GRPO v1 run reported) |
| Reward hacking signs on 1.5B | not available (no 1.5B GRPO run reported) |
| Total time, GPU | not available. Planned GPU: RTX 3060 12 GB. Planning estimate (not a measurement): about 40-45 s per question per epoch, 6-8 h for one epoch on 500-600 questions |

**The only GRPO run so far: Phase 1 practice on Qwen2.5-0.5B-Instruct** (Kaggle T4, date not stated in the protocol;
source `docs/TRAINING_PROTOCOL.md` sections 9.4-9.5; `docs/19-reward-hacking-case-study.md` is still an empty stub):

- 239 train / 61 check questions taken from BIRD dev, 2 epochs, 60 batches each, 70.5 min; peak memory
  about 8.3 GB of the T4's 15 GB.
- Check-set accuracy 4.9% (3) -> 4.9% (3) -> 8.2% (5); mean training reward 0.071 (epoch 1) -> 0.135 (epoch 2);
  sampled answers correct 4.3% -> 8.8%.
- Share of answers that ran per batch: 2-9 of 32 at the start, 20-32 of 32 at the end.
- On the 61 check questions, base -> trained: correct 3 -> 5, ran but wrong 12 -> 29, failed 46 -> 27.
  This is the reward-hacking sign: the "ran" share rose much more than the "correct" share; the model
  learned to collect the 0.1 reward. Examples: question 1070 (trained model returned the league id instead
  of the country name); question 1300 (wrong column `T-CHO`, no range filter, result matched by coincidence
  and counted as correct).
- Reward bug found later: empty answers counted as "ran" and earned 0.1; fixed so a query with no result
  set is an error. How many Phase 1 answers were empty was not measured.
- The protocol calls this a practice run, not a reported result (+2 of 61 is within chance).

**Planned settings for GRPO v1 on 1.5B** (from the code and the runbook command; none of this has been confirmed by a run):

| Setting | Value | Source |
|---|---|---|
| Start point | SFT v2 adapter `E:\verdict_runs\sft_v2\best` (`--init-adapter`) | runbook step D |
| Questions | ids in `kept_ids.json` (`--task-ids`) | runbook step D |
| Learning rate | 1e-5 | runbook step D (`--lr 1e-5`); also `LORA_LR` in `scripts/train_grpo.py` |
| Questions per batch | 4 | `GRPOTrainingConfig.batch_size`, `verdict/train/grpo.py` |
| Group size (samples per question) | 8 | `num_generations` |
| Epochs | code default 3; the Training chat recommended `--epochs 1` because of time (not yet in the runbook command) | `grpo.py`; `docs/TRAINING_SESSION_HANDOFF.md` |
| LoRA rank | 16 (alpha 32), taken from the SFT v2 adapter | runbook / handoff |
| Reward | "sparse": 1.0 correct, 0.1 ran but wrong, 0.0 did not run | `REWARD_SCHEMES` in `verdict/train/reward.py` |
| Reward query timeout | 5 s (code default `reward_timeout_s`; `train_grpo.py` has no flag for it). Note: the dev evaluation uses 30 s | `grpo.py`, `reward.py` |
| Micro-batch | 4 completions per forward/backward | `micro_batch_size` |
| Advantage | reward minus group mean, not divided by group std (`scale_rewards=False`) | `grpo.py` |
| KL penalty | none | `grpo.py` docstring |
| Temperature / top-p / max new tokens | 0.9 / 0.95 / 256 | `grpo.py` |
| Schema limit | 12,000 characters | runbook step D |
| Validation | greedy accuracy on up to 100 of the 200 held-out questions, before training and after each epoch | `eval_max_tasks`, `eval_before_training` |
| Checkpoints | `latest/` every epoch, `best/` when validation improves; no mid-epoch resume | `grpo.py` |

Note: the pass rate also scores answers with the 5 s default timeout (`SQLRewardFunction` default),
not 30 s.

---

## 3. GRPO on BIRD dev (1,534 questions)

**Not run.** Correct %, Wilson range, ran %, by difficulty, change against SFT v2, McNemar and
error types: not available. Planned command: runbook step D (eval with `--baseline eval_sft_v2.jsonl`).

---

## 4. Export (`scripts/export_model.py`)

| Item | Value | Source |
|---|---|---|
| Merge (LoRA into base, fp16) | unclear: commands were given on 24 Nov, no result reported | runbook section 9 |
| GGUF conversion | unclear (planned `q8_0`, expected about 1.6 GB; not measured) | runbook section 9 |
| Ollama build | not run on the laptop: Ollama is not installed there (`where ollama` finds nothing, 25 Nov) | this check |
| 50-question parity check | not run | |
| Laptop speed (1 answer, 8 answers) | not run | |

Code exists and is tested only for the Modelfile text (`tests/test_export_model.py`); the merge
itself has not been run on the laptop.

---

## 5. Other work since 24 Nov 2026

| Item | Value |
|---|---|
| 8 samples per dev question for the trust run | not run (script not written yet; output format to come from the Evaluation session) |
| Gemini / GPT comparison on BIRD dev | not run (script not written yet) |
| Untrained 7B evaluation | not run (needs a 4-bit loading option; waiting for the user's decision) |

Training commits on 24 Nov (from `git log`):

- `db673e9` 11:02: `scripts/train_run.py`: one Ctrl+C only warns, two within 5 s stop the run; the child
  runs in its own process group. Bug it fixes: runs on the PC ended with exit code 1 and no traceback
  (most likely an accidental Ctrl+C while copying text).
- `57f3bca` 11:03: runbook status table.
- `0f1df04` 11:46: `scripts/export_model.py` and runbook section 9.
- `8267a07` 14:01: out-of-memory retry in generation (section 1 above).
- `3bd2bdd` 14:16: `docs/TRAINING_SESSION_HANDOFF.md`.

Earlier, `5453f11` (before 24 Nov): `train_run.py` uses the venv Python (bug: "No module named sqlglot").

Laptop test suite on 24 Nov after `8267a07`: 272 passed, 4 skipped.

---

## 6. Reasons for the main choices

**Hand-written PyTorch loops instead of TRL or Unsloth.**
Not documented. The original plan chose Unsloth (ADR-011 in `VERDICT-MASTER-CONTEXT.md`: it shares
weight memory between training and generation, which matters on one GPU), and `README.md` still lists
"Unsloth + vLLM" and "Unsloth/TRL" in the stack. The code in `verdict/train/` uses neither; no document
says why it changed. What the code does document: the reward function keeps the TRL/verl signature so
it can be reused there (`verdict/train/reward.py`), and the loop does one update per batch, so the PPO
ratio and clipping are left out (`verdict/train/grpo.py`). The README and the code disagree; the book
should not claim Unsloth was used.

**Qwen2.5-Coder and not Llama, DeepSeek-Coder or Phi.**
Partly documented, as planning notes (not measurements): `VERDICT-MASTER-CONTEXT.md` says Qwen2.5-Coder
has the "best SQL ability of the small ones" and lists Llama-3.1-8B as "weaker at SQL than Qwen-Coder".
DeepSeek-Coder and Phi: not documented. The size (1.5B and not 7B) is explained in `docs/HANDOFF.md`:
the private mode runs on the laptop, where a 7B GGUF is about 4.5 GB and slower. The same master context
also warns that RL gains on Qwen models may partly come from the model and not the reward (marked
unverified there), and suggests a random-reward control run; that run has not been done.

**q8_0 for the GGUF and not Q4 or Q5.**
Not documented. `docs/TRAINING_RUNBOOK.md` section 9 uses `q8_0` ("8-bit, about 1.6 GB") with no reason
given, and `docs/DEPLOYMENT.md` (Backend's file) still says "Q4 or Q5, about 1 GB". The two documents
disagree and should be made to match once the export is done.

**No KL penalty.**
Documented in `verdict/train/grpo.py`: a KL penalty needs a second copy of the model (the reference) in
GPU memory, and Dr. GRPO and DAPO report it is not needed for verifiable-reward tasks at this scale.
`docs/TRAINING_PROTOCOL.md` section 5 states that no KL penalty is used. Counterpoint on record:
`VERDICT-MASTER-CONTEXT.md` notes that Arctic-Text2SQL-R1 kept a small KL (beta 0.001).

**Dr. GRPO-style normalisation.**
Documented in `docs/TRAINING_PROTOCOL.md` section 5: the advantage is not divided by the group's standard
deviation, because Dr. GRPO (Liu et al., 2025, arXiv:2503.20783) shows this over-weights groups whose
rewards are nearly identical; the loss is divided by a constant (`max_tokens`) instead of each answer's
length, also following Dr. GRPO. In code: `scale_rewards=False` in `verdict/train/grpo.py`.

---

## 7. What is left, in order

Times are planning estimates, not measurements.

1. Get the restarted pass-rate result (summary, `kept_ids.json`, spread of correct counts) and copy the PC
   logs to `results/college/`. Run: up to 9 h (time limit); copying: 15 min.
2. GRPO quick check on 20 questions (checks memory in the training step): about 15 min.
3. GRPO v1, one epoch: about 6-8 h (one night). No mid-epoch resume.
4. GRPO v1 on BIRD dev with McNemar against SFT v2: about 40 min.
5. Export SFT v2: merge about 5 min, GGUF conversion about 10-20 min, copy to the laptop, install Ollama,
   `ollama create`: about 1 h in total. Then the 50-question parity check and speed numbers: about 1 h.
   Repeat for GRPO v1 if it is better.
6. Script for 8 samples per dev question (for the Evaluation session): about 2 h to write and test, then
   about 3-4 h of GPU time (based on 12.6-30 s per question for 8 samples on the training set; dev not measured).
7. Gemini / GPT comparison script and run: about 2 h to write, run time depends on API limits.
8. Optional untrained 7B eval (4-bit): about 2 h of code, 15 GB download, 3-5 h of GPU. Competes with GRPO
   for the one GPU; waiting for the user's decision.
9. Final model table, runbook and LOG updates, and making `docs/DEPLOYMENT.md` and the README match what
   was really used (q8_0, no Unsloth): about 2 h.
