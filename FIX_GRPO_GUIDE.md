# How to Fix GRPO Training Loop

**Current Status:** ✅ Advantage calculation added, ⏳ Policy gradient still needs completion

---

## What I Just Fixed (Step 1/3)

### ✅ Added Group-Relative Advantage Calculation

**File:** `verdict/train/grpo.py` line 130-150

**What it does:**
```python
# For each group of 8 completions:
# advantage = reward - mean(group_rewards)
advantages = []
for i in range(0, len(batch_rewards), n):
    group_rewards = batch_rewards[i : i + n]
    group_mean = statistics.mean(group_rewards)
    group_advantages = [r - group_mean for r in group_rewards]
    advantages.extend(group_advantages)
```

**Why this matters:** GRPO compares rewards within each group, not globally. A completion gets positive advantage if it's better than its groupmates, even if the absolute reward is low.

**Example:**
```
Group 1 rewards: [1.0, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0]  mean = 0.15
Advantages:      [0.85, -0.05, -0.05, -0.15, -0.15, -0.15, -0.15, -0.15]
                  ^^^^                 ^^^^^^ Model learns: do more like #1, less like others
```

---

## What Still Needs to Be Done (Steps 2-3)

### ⏳ Step 2: Modify `rollout.py` to Return Log Probabilities

**Problem:** We need log probabilities from generation to compute policy loss, but `generate()` only returns text.

**Current code:**
```python
# verdict/train/rollout.py, line ~40
def generate(model, tokenizer, prompts, n_completions, config):
    # ... generates text ...
    return [[text1, text2, ...], ...]  # Only returns text
```

**What we need:**
```python
def generate(model, tokenizer, prompts, n_completions, config):
    # ... generates text ...
    # ALSO track log probabilities
    return groups, log_probs  # Return both text AND log probs
```

**How to do it:**

<function_calls>
<invoke name="read_file">
<parameter name="path">verdict/train/rollout.py