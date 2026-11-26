# Verdict: Training and Evaluation Protocol

This document describes how the Verdict text-to-SQL model is trained and
evaluated: the data splits, the method, the settings, the order of the runs,
and how the results are measured. It is written so that another person can
repeat every run and get comparable numbers.

Status of each part is marked as **[implemented]** (in the code today) or
**[planned]** (designed, not yet written).

---

## 1. Goal

Verdict answers questions about a database by writing SQL. The project makes
two claims, and the protocol is built to test both:

1. **Accuracy.** Reinforcement learning with an execution reward makes a small
   open model write correct SQL more often.
2. **Calibrated trust.** When the trust engine labels an answer green, the
   answer is correct at a high, measured rate. Red answers are correct at a
   low rate. The labels are assigned without access to the correct answer.

---

## 2. Data

### 2.1 Benchmark

BIRD (Li et al., 2023), a text-to-SQL benchmark built on real SQLite databases.

| Split | Questions | Databases | Role in this project |
|---|---|---|---|
| BIRD train | about 9,400 | 69 | training only |
| BIRD dev | 1,534 | 11 | evaluation only (final results) |

Each question has: the question text, an evidence hint, a gold SQL query, a
difficulty label (simple, moderate, challenging) and a database.

BIRD dev difficulty mix: 925 simple (60%), 464 moderate (30%), 145
challenging (10%).

### 2.2 The rule that keeps results honest

**A model that is evaluated on BIRD dev must never have been trained on any
BIRD dev question.** BIRD dev is the set that published papers report on. If
dev questions are seen in training, the dev score no longer measures
generalisation and cannot be compared with other work.

### 2.3 Splits used in each phase

| Phase | Train on | Check progress on | Final test on |
|---|---|---|---|
| Phase 1 (practice) | 240 BIRD dev questions | 60 other BIRD dev questions | none (practice only) |
| Phase 2 (main) | BIRD train | a held-out slice of BIRD train | all 1,534 BIRD dev questions |

The Phase 1 model is discarded. Phase 2 starts again from the original
pretrained model.

The Phase 1 split is stratified by difficulty so that both parts keep the
60/30/10 mix **[implemented]**.

---

## 3. Model input

### 3.1 Prompt **[implemented]**

Each question becomes one prompt in the model's chat format:

1. **System message.** Fixed instructions: write one SQLite SELECT query, use
   only the tables and columns in the schema, return only the query inside a
   ```sql block.
2. **User message.**
   - the database schema (`CREATE TABLE` statements),
   - two sample rows per table,
   - the question,
   - the evidence hint.
3. **Generation marker** (`<|im_start|>assistant`), after which the model
   writes its answer.

The gold SQL is never shown to the model.

### 3.2 Schema length limit **[implemented]**

Schemas can be long (2,000+ tokens). If a schema is longer than 6,000
characters, the sample rows are removed first. If it is still too long, it is
cut at a line break and marked as truncated. The prompt itself is never cut,
because the question sits at its end.

---

## 4. Reward **[implemented]**

Every model answer is scored by running it, not by reading it.

1. Extract the SQL from the answer (the last ```sql block, or the whole text).
2. Run it on the question's database, read-only, with a 5 second limit.
3. Run the gold SQL on the same database.
4. Compare the two results.

| Outcome | Reward |
|---|---|
| Query ran and the result matches the gold result | 1.0 |
| Query ran but the result is different | 0.1 |
| Query failed (syntax error, unknown column, timeout, blocked) | 0.0 |

The 0.1 tier follows Arctic-Text2SQL-R1 (Yao et al., 2025). Without it, a
group where every answer is wrong gets identical rewards and gives no
learning signal (Section 5.2). The tier rewards the model for producing
queries that at least run.

---

## 5. Training method

Training has two stages. Stage A is planned. Stage B is implemented.

### 5.1 Stage A: supervised fine-tuning (SFT) **[planned]**

**Purpose.** The base model's queries mostly fail to run (Section 9.1). A
model that is almost always wrong cannot learn from its own attempts, so it
is first taught from correct examples.

**Procedure.**
1. For each BIRD train question, build the prompt (Section 3) and append the
   gold SQL as the answer.
2. Train the model to predict the gold SQL token by token (cross-entropy loss
   on the answer tokens only).
3. One to two passes over BIRD train.

**What it teaches.** Output format, quoting column names that contain spaces,
choosing tables from the schema, and using the hint.

### 5.2 Stage B: Group Relative Policy Optimisation (GRPO) **[implemented]**

GRPO (Shao et al., 2024) trains the model on its own answers, using the
reward to decide which answers to make more likely.

**One training step:**

1. **Sample.** Take a batch of `B` questions. For each, the model writes `G`
   answers with sampling (temperature 0.9, top-p 0.95).
2. **Score.** Each answer receives a reward `r` (Section 4).
3. **Advantage.** Within each group of `G` answers to the same question:

   ```
   advantage_i = r_i - mean(r_1, ..., r_G)
   ```

   Answers better than their group's average get a positive advantage, worse
   ones a negative advantage. If all `G` rewards are equal, every advantage is
   zero and the question contributes nothing to this step.

   The advantage is not divided by the group's standard deviation, following
   Dr. GRPO (Liu et al., 2025), which shows that division over-weights groups
   whose rewards are nearly identical.

4. **Loss.** For each answer, `log p(answer)` is the sum of the log
   probabilities the model gives to the answer's tokens, given the prompt.

   ```
   loss = - sum_i( advantage_i * log p(answer_i) ) / (B * G * max_tokens)
   ```

   Lowering this loss raises the probability of above-average answers and
   lowers it for below-average ones. Dividing by a constant (`max_tokens`)
   instead of each answer's length also follows Dr. GRPO.

5. **Update.** Backpropagate, clip the gradient norm to 1.0, take one AdamW
   step.

There is one update per batch of samples (on-policy), so the importance ratio
and clipping used by PPO are always 1 and are omitted. No KL penalty to a
reference model is used.

**Implementation details that affect correctness:**

- The exact token ids that were sampled are used to compute `log p`. Decoding
  to text and re-tokenising can produce different tokens.
- Each answer is cut at its first end-of-sequence token, so padding is never
  trained on.
- Completions are paired with their own prompt (`[p0 x G, p1 x G, ...]`).

### 5.3 LoRA **[planned]**

For models of 1.5B parameters and larger, full fine-tuning does not fit in a
16 GB GPU (weights, gradients and two AdamW states need about 16 bytes per
parameter: roughly 24 GB for 1.5B). Low-Rank Adaptation (Hu et al., 2021)
freezes the original weights and trains small added matrices in each layer,
which reduces trainable parameters and optimiser memory by more than 95%.

---

## 6. Settings

### 6.1 Models

| Phase | Model | Training |
|---|---|---|
| Phase 1 | Qwen2.5-0.5B-Instruct (494M parameters) | full fine-tuning, GRPO only |
| Phase 2 | Qwen2.5-Coder-1.5B-Instruct | LoRA, SFT then GRPO |

### 6.2 GRPO hyperparameters (Phase 1 defaults) **[implemented]**

| Setting | Value | Why |
|---|---|---|
| Questions per batch `B` | 4 | |
| Answers per question `G` | 8 | enough spread within a group |
| Max new tokens | 256 | a BIRD query rarely needs more |
| Temperature / top-p | 0.9 / 0.95 | answers must differ for advantages to be non-zero |
| Learning rate | 1e-6 | small steps keep the model from forgetting |
| Optimiser | AdamW, weight decay 0 | |
| Gradient clipping | 1.0 | limits the effect of one unusual batch |
| Epochs | 2 | |
| Precision | fp32 weights, fp16 autocast, gradient scaling | the T4 has no bf16; fp16 weights lose updates this small |
| Gradient checkpointing | on | saves memory on long prompts |
| Random seed | 42 | |

### 6.3 Hardware

Kaggle notebook, one NVIDIA Tesla T4 (16 GB). Kaggle allows about 30 GPU
hours a week and 12 hours per session. Runs longer than one session must be
resumed from a saved checkpoint.

---

## 7. Procedure

### Phase 1: practice run on 0.5B **[done]**

| Step | What is done | Output that is checked |
|---|---|---|
| 0 | Set up the notebook: GPU T4, internet on, BIRD dev added as input; clone the code | `CUDA: True`, 11 databases found |
| 1 | Load BIRD dev | 1,534 questions, difficulty and database counts |
| 2 | Build one prompt | prompt text and length in tokens |
| 3 | Base model writes 8 answers to one question | each SQL and its reward |
| 4 | Repeat on 6 questions from different databases | rewards and advantages per group |
| 5 | One manual GRPO update | log-probability of the best answer rises, of the worst falls |
| 6 | Rehearsal: full script on 20 questions, 1 epoch | no errors; seconds per batch; checkpoint written |
| 7 | Training: 300 questions (239 train, 61 check), 2 epochs, run as a Kaggle commit | check-set accuracy before and after each epoch |
| 8 | Keep the checkpoint: the commit's output is attached as input to later notebooks | checkpoint loads in a new session |
| 9 | Compare base and trained model on the 61 check questions | accuracy, share of queries that run, per-question changes |

Results are in Section 9.

Phase 1 exists to confirm that the pipeline works end to end, to measure time
per batch, and to practise saving and resuming. Its numbers are not reported
as results.

### Phase 2: main run **[code implemented, not yet run]**

| Step | What is done | Code |
|---|---|---|
| 10 | Prepare BIRD train on Kaggle; load it | `load_bird_train`, `SchemaStore` |
| 11 | LoRA and an SFT stage | `verdict/train/modeling.py`, `verdict/train/sft.py` |
| 12 | SFT on all of BIRD train | `scripts/train_sft.py` |
| 13 | Measure each BIRD train question's success rate with the SFT model (8 samples); keep questions solved sometimes but not always | `scripts/pass_rate.py` |
| 14 | GRPO on the kept questions, starting from the SFT adapter | `scripts/train_grpo.py --train-dir --init-adapter --task-ids` |
| 15 | Evaluate base, SFT and SFT+GRPO models on all of BIRD dev | `scripts/evaluate.py` |

**BIRD train as prepared.** 9,428 questions over 69 databases (31 GB
unpacked). Kaggle keeps at most 20 GB of a notebook's output, so the four
largest databases were dropped from disk: `bike_share_1`, `donor`,
`codebase_comments` and `movie_platform` (18.5 GB, 564 questions). Their
schemas were saved to `schemas.json`, so SFT still trains on all 9,428
questions. GRPO and validation, which run queries, use the 8,864 questions
whose 65 databases were kept.

**Validation split.** 200 questions with a database on disk, chosen with a
fixed seed (`holdout_split`, seed 0). SFT, the pass-rate step and GRPO use
the same seed, so none of them trains on these questions. BIRD dev is not
used until step 15.

Questions that are always solved or never solved give zero advantage in every
group (Section 5.2), so step 13 removes them to save GPU time.

### Phase 3: trust engine evaluation **[planned]**

| Step | What is done |
|---|---|
| 16 | Run the trust engine with the final model on all of BIRD dev |
| 17 | Measure accuracy per trust level and set the thresholds from these numbers |
| 18 | Test unanswerable questions (databases with the needed table removed) |

---

## 8. Evaluation

### 8.1 Execution accuracy

For each question the model writes one answer with greedy decoding
(temperature 0). The answer is correct if its result matches the gold
result. Execution accuracy is the share of correct answers. The gold SQL is
used only to grade; the model is not updated during evaluation.

Reported overall and per difficulty level.

### 8.2 Trust engine

The engine has no access to the gold SQL. For each question:

1. The model writes `n = 8` answers with sampling.
2. All 8 are run. Answers that return the same result are grouped.
3. **Agreement** is the share of the 8 answers in the largest group.
4. The level is set from agreement:

| Level | Rule (current placeholder thresholds) | Shown to the user |
|---|---|---|
| unanswerable | more than half the answers say the question cannot be answered | "cannot answer" |
| green | agreement >= 0.75 | the answer |
| yellow | agreement >= 0.50 | the answer, with a warning |
| red | otherwise | no answer |

An empty result (no rows, or only NULL) is never green.

The reasoning: there are many ways to be wrong and usually one way to be
right. A model that knows the answer tends to reach the same result
repeatedly. A model that is guessing spreads across different results.
Agreement is not proof of correctness: answers from one model can share the
same mistake. That is why the levels must be measured (8.3).

### 8.3 Calibration

After the engine labels every BIRD dev question, the gold SQL is used to
check each label:

| Metric | Meaning | Target |
|---|---|---|
| Green precision | share of green answers that are correct | 90% or higher |
| Yellow precision | share of yellow answers that are correct | in between |
| Red precision | share of red answers that would have been correct | low |
| Coverage | share of questions labelled green | as high as possible at the target precision |
| Unanswerable recall | share of truly unanswerable questions labelled unanswerable | high |

The thresholds in `verdict/engine/thresholds.json` are then set from these
measurements instead of the placeholders.

### 8.4 Results table to report

| | Base model | SFT | SFT + GRPO |
|---|---|---|---|
| BIRD dev execution accuracy | 20.7% | 34.9% | |
| Share of queries that run | 42.6% | 67.9% | |
| Green precision / coverage | | | |
| Unanswerable recall | | | |

Base model: Qwen2.5-Coder-1.5B-Instruct. Accuracies use a 5-second query
limit; see Section 9.7.

---

## 9. Observations so far

### 9.1 Base model behaviour (Phase 1, steps 3 and 4)

Qwen2.5-0.5B-Instruct, 8 sampled answers per question, 7 questions:

- 56 answers in total: 1 correct, 6 ran but wrong, 49 failed to run.
- 3 of 7 questions had all 8 answers fail, giving zero learning signal.
- Common failures: column names containing spaces written without backticks;
  columns taken from the wrong table; invented columns and functions; the
  evidence hint ignored; one answer hit the 256-token limit.

These observations motivate the SFT stage and the larger code model in
Phase 2.

### 9.2 One manual GRPO update (Phase 1, step 5)

Question 202 (toxicology): rewards `[0.1, 0, 1, 1, 1, 0, 1, 0]`, group mean
0.51, advantages +0.49 for correct answers, -0.41 for the one that ran but
was wrong, -0.51 for failures.

After one AdamW step (learning rate 1e-6) on this group:

| Answer | log p before | log p after | Probability change |
|---|---|---|---|
| Best (correct, uses table `bond`) | -2.80 | -0.63 | x8.7 |
| Worst (failed, uses table `connected`) | -5.89 | -16.93 | about x0 |

The change is large for one step because Adam's first update moves every
weight by about the full learning rate regardless of gradient size. This
was measured on the training example itself, so it shows the update has the
intended direction, not that the model generalises.

On the same question, a step where all 8 rewards were equal produced no
change at all (probability x1.000), as the advantage formula predicts.

### 9.3 Rehearsal (Phase 1, step 6)

20 questions (15 train, 5 check, 4 evaluated), 1 epoch, 4 batches, 3.2
minutes. About 40 seconds per batch at the start (generation 20 to 40 s,
SQL under 10 s, update 4 to 12 s).

The first attempt ran out of GPU memory because the notebook still held a
model from step 5 (6.2 GB). Training alone peaked at about 8.3 GB of the
T4's 15 GB. Training runs must start from a fresh session.

### 9.4 Training run (Phase 1, step 7)

300 BIRD dev questions (every 5th question), split by difficulty into 239
train and 61 check questions. 2 epochs, 60 batches each, 70.5 minutes.

| | Before training | After epoch 1 | After epoch 2 |
|---|---|---|---|
| Check-set accuracy (greedy, 61 questions) | 4.9% (3) | 4.9% (3) | 8.2% (5) |
| Mean training reward | | 0.071 | 0.135 |
| Training answers correct (sampled) | | 4.3% | 8.8% |

During training the share of answers that ran rose from 2 to 9 of 32 per
batch at the start to 20 to 32 of 32 by the end, and generation time per
batch fell from about 30 s to about 12 s, meaning the answers got shorter.

### 9.5 Base and trained model compared (Phase 1, step 9)

Same 61 check questions, one greedy answer each.

| Outcome | Base model | Trained model |
|---|---|---|
| Correct | 3 | 5 |
| Ran, wrong result | 12 | 29 |
| Failed to run | 46 | 27 |

How each question moved from base to trained:

| Base | Trained | Questions |
|---|---|---|
| failed | failed | 23 |
| failed | ran, wrong | 20 |
| ran, wrong | ran, wrong | 7 |
| ran, wrong | failed | 4 |
| failed | correct | 3 |
| correct | ran, wrong | 2 |
| correct | correct | 1 |
| ran, wrong | correct | 1 |

Four questions became correct and two stopped being correct, a net gain of
two.

**What the trained model learned.** Mostly to write queries that run. The
trained model writes shorter queries with fewer joins, often a single table
or a subquery. This helped where the base model wandered (question 1425: the
base model joined six unrelated tables; the trained model wrote one correct
`COUNT(*)` on `major`) and hurt where a join was needed (question 1070: the
question asks for a country name; the trained model returned the league's
id instead).

**A correct result for the wrong reason.** Question 1300 asks for the
patient with the highest triglyceride level within the normal range. The
trained model used the cholesterol column (`T-CHO`) and no range filter, yet
its result matched the gold result. Execution matching counted it as
correct. Of the four new correct answers, at least one is a coincidence.

**Reading.** The 0.1 reward for a query that runs is what the model learned
to collect: failures fell from 46 to 27, but most of those became wrong
answers rather than correct ones. The gain in correct answers (+2 of 61) is
within what chance can produce on 61 questions. This is a practice run on
BIRD dev and is not reported as a result.

**A reward bug found afterwards.** While building Phase 2, an empty answer
(no SQL, only a comment, or only `;`) was found to count as a query that ran:
SQLite executes it without error. Such answers earned the 0.1 "ran but
wrong" reward. The verifier now treats any query without a result set as an
error, so these earn 0. Phase 1 ran with the bug, so some of its "ran,
wrong" answers may have been empty; how many was not measured.

**Consequences for Phase 2.**

- SFT before GRPO, so that the model learns joins and correct columns from
  gold queries, not only queries that run.
- A larger code model, so that more groups contain fully correct answers and
  the 1.0 reward, not the 0.1 reward, drives learning.
- Evaluation on all 1,534 BIRD dev questions; 61 questions cannot separate a
  gain of a few points from noise.
- Watch the share of queries that run against the share that are correct.
  If the first rises and the second does not, lower or remove the 0.1
  reward.

### 9.6 Supervised fine-tuning (Phase 2, step 12)

Qwen2.5-Coder-1.5B-Instruct with LoRA (r 16, alpha 32, dropout 0.05;
18.5M trainable parameters, 1.18% of 1.56B). 9,226 BIRD train examples
(two skipped for answers over 256 tokens), 1 epoch, 577 steps of 16
examples, learning rate 1e-4 with 20 warm-up steps and linear decay. About
20 s per step on a T4; 217.8 minutes including two validation passes.

Training loss per answer token fell from 0.25 (first 10 steps) to 0.13 to
0.16 (last 100 steps).

On the 200 held-out BIRD train questions (greedy, 5-second query limit):

| | Before SFT | After SFT |
|---|---|---|
| Correct | 20.5% (41) | 38.0% (76) |
| Ran | 37.0% | 61.5% |
| Failed: unknown column | 80 | 38 |
| Failed: timeout | 28 | 33 |
| Failed: syntax error | 10 | 0 |

The base model's failures were mostly invented or misplaced column names,
not output formatting, as had been assumed before the failure reasons were
recorded.

### 9.7 BIRD dev, base and SFT models (Phase 2, step 15, first part)

All 1,534 BIRD dev questions, one greedy answer each, 5-second query limit,
8 queries scored in parallel. Neither model was trained on any BIRD dev
question.

| | Base | SFT |
|---|---|---|
| Overall correct | 318 (20.7%) | 535 (34.9%) |
| simple (925) | 26.3% | 40.8% |
| moderate (464) | 12.3% | 26.1% |
| challenging (145) | 12.4% | 25.5% |
| Ran | 42.6% | 67.9% |

Per question, base to SFT: 285 became correct, 68 stopped being correct,
net +217.

| Failure reason | Base | SFT |
|---|---|---|
| unknown column | 644 | 265 |
| timeout | 159 | 210 |
| unknown function | 30 | 3 |
| syntax error | 26 | 8 |
| other error | 13 | 0 |
| unknown table | 5 | 6 |

Answers marked wrong because the gold query itself failed: 18 (base), 10
(SFT).

**Open questions.**

- **Timeouts.** 210 SFT answers (14%) hit the 5-second limit, more than the
  base model's 159, because more SFT answers reach execution. Some of these
  may be correct queries on large databases, slowed further by running 8 at
  once on a few CPU cores. The saved SQL will be re-scored with a longer
  limit before these numbers are reported.
- **Unknown columns.** Still the largest failure. Schemas over 6,000
  characters are shortened, first by dropping sample rows, then by cutting.
  Whether cut schemas account for part of these failures is to be checked.
- **Generation time.** Answering took 3,712 s for the base model and 6,044 s
  for the SFT model. The cause has not been checked.

---

## 10. Known limitations

- **Agreement is not correctness.** All 8 answers can make the same mistake.
  Calibration (8.3) measures how often this happens; it cannot prevent it.
- **Result matching can be lenient or strict.** Two queries can return the
  same rows for different reasons, and some correct answers differ from the
  gold result in column order or rounding.
- **BIRD gold SQL contains errors.** Some gold queries are known to be wrong,
  which caps the measurable accuracy.
- **Phase 1 numbers are not results.** The Phase 1 model was trained and
  checked on BIRD dev.
- **One seed.** Runs on a free GPU allow one seed per setting; differences of
  one or two points may be noise.

---

## 11. Reproducing a run

Phase 1, step 7, on Kaggle:

```python
!python scripts/train_grpo.py --num-tasks 300 --epochs 2 \
    --checkpoint-dir /kaggle/working/checkpoints
```

Outputs:
- `checkpoints/latest/` after every epoch, `checkpoints/best/` when check-set
  accuracy improves. Each holds the model, tokenizer, `training_config.json`
  and `training_state.json`.
- `results/training_results.json` with the settings, split sizes, per-epoch
  rewards and accuracies.

The commands for the college PC are in `docs/TRAINING_RUNBOOK.md`.

---

## References

- Li, J. et al. (2023). *Can LLM Already Serve as a Database Interface? A Big
  Bench for Large-Scale Database Grounded Text-to-SQLs* (BIRD). NeurIPS.
- Shao, Z. et al. (2024). *DeepSeekMath: Pushing the Limits of Mathematical
  Reasoning in Open Language Models*. arXiv:2402.03300. (GRPO)
- Liu, Z. et al. (2025). *Understanding R1-Zero-Like Training: A Critical
  Perspective*. arXiv:2503.20783. (Dr. GRPO)
- Yao, Z. et al. (2025). *Arctic-Text2SQL-R1: Simple Rewards, Strong
  Reasoning in Text-to-SQL*. arXiv:2505.20315.
- Hu, E. et al. (2021). *LoRA: Low-Rank Adaptation of Large Language Models*.
  arXiv:2106.09685.
- Qwen Team (2024). *Qwen2.5 Technical Report*. arXiv:2412.15115.
