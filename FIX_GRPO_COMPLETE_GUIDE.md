# Complete Guide: Fix GRPO Training Loop

**Status:** ✅ Step 1 done, ⏳ Steps 2-3 remain

---

## ✅ Step 1: Advantage Calculation (DONE)

**File:** `verdict/train/grpo.py` (just updated)

Added group-relative advantage calculation:
```python
advantages = []
for i in range(0, len(batch_rewards), n):
    group_rewards = batch_rewards[i : i + n]
    group_mean = statistics.mean(group_rewards)
    group_advantages = [r - group_mean for r in group_rewards]
    advantages.extend(group_advantages)
```

**How it works:**
```
8 completions per prompt → compare within group
Reward [1.0, 0.1, 0.1, 0.0, ...] → Advantage [+0.85, -0.05, -0.05, -0.15, ...]
Model learns: "Do more like #1, less like others"
```

---

## ⏳ Step 2: Add Log Probability Tracking

**File to modify:** `verdict/train/rollout.py`

### Current Problem:
```python
def generate(...):
    output_ids = model.generate(**inputs, **gen_kwargs)
    # Only returns decoded text
    return [[text1, text2, ...], ...]
```

### What We Need:
Store log probabilities during generation so we can compute:
```python
policy_loss = -(log_probs * advantages).mean()
```

### Solution: Return Scores from model.generate()

**Option A: Use `return_dict_in_generate=True` (RECOMMENDED)**

Add this to `verdict/train/rollout.py`:

```python
def generate(
    model,
    tokenizer,
    prompts: list[str],
    n_completions: int = 4,
    config: GenerationConfig | None = None,
    max_prompt_tokens: int = 512,
    return_log_probs: bool = False,  # NEW parameter
) -> list[list[str]] | tuple[list[list[str]], torch.Tensor]:
    """Return n_completions for each prompt, optionally with log probs."""
    config = config or GenerationConfig()
    gen_kwargs = {
        **config.to_dict(),
        "num_return_sequences": n_completions,
        "pad_token_id": tokenizer.pad_token_id or tokenizer.eos_token_id,
    }
    
    if return_log_probs:
        gen_kwargs["return_dict_in_generate"] = True
        gen_kwargs["output_scores"] = True

    model.eval()
    results = []
    all_log_probs = []
    
    with torch.no_grad():
        for prompt in prompts:
            inputs = tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=max_prompt_tokens
            ).to(model.device)
            
            if return_log_probs:
                outputs = model.generate(**inputs, **gen_kwargs)
                sequences = outputs.sequences
                prompt_len = inputs["input_ids"].shape[1]
                
                # Decode text
                texts = [
                    tokenizer.decode(ids[prompt_len:], skip_special_tokens=True).strip()
                    for ids in sequences
                ]
                results.append(texts)
                
                # Compute log probabilities from scores
                # scores is a tuple of (batch_size, vocab_size) for each generated token
                scores = outputs.scores  # tuple of tensors
                log_probs = []
                for step_idx, step_scores in enumerate(scores):
                    # step_scores: (n_completions, vocab_size)
                    step_log_probs = torch.log_softmax(step_scores, dim=-1)
                    # Get log prob of the token that was actually chosen
                    chosen_tokens = sequences[:, prompt_len + step_idx]
                    chosen_log_probs = step_log_probs.gather(1, chosen_tokens.unsqueeze(1)).squeeze(1)
                    log_probs.append(chosen_log_probs)
                
                # Sum log probs across sequence length for each completion
                # Shape: (n_completions,)
                sequence_log_probs = torch.stack(log_probs, dim=1).sum(dim=1)
                all_log_probs.append(sequence_log_probs)
            else:
                # Original code path (no log probs)
                output_ids = model.generate(**inputs, **gen_kwargs)
                prompt_len = inputs["input_ids"].shape[1]
                results.append(
                    [
                        tokenizer.decode(ids[prompt_len:], skip_special_tokens=True).strip()
                        for ids in output_ids
                    ]
                )
    
    if return_log_probs:
        # Concatenate all log probs: shape (total_completions,)
        return results, torch.cat(all_log_probs)
    return results
```

**Why this approach:**
- Uses HuggingFace's built-in `output_scores`
- No manual forward passes needed
- Clean and efficient

---

## ⏳ Step 3: Add Optimizer & Policy Gradient

**File to modify:** `verdict/train/grpo.py`

### 3.1 Add Optimizer to `__init__`

Add after line 33 (after `self.model = ...`):

```python
def __init__(self, config: GRPOTrainingConfig, db_root: Path | str):
    # ... existing code ...
    self.model = self._load_model(config.model_name)
    
    # ADD THIS: Initialize optimizer
    self.optimizer = torch.optim.AdamW(
        self.model.parameters(),
        lr=config.learning_rate,
        weight_decay=0.01,
    )
    
    # ADD THIS: Enable gradient computation
    self.model.train()  # Switch to training mode
    
    # ... rest of __init__ ...
```

### 3.2 Modify `_train_epoch` to Compute Policy Loss

Replace the current TODO section (around line 140) with:

```python
def _train_epoch(self, loader: DataLoader) -> list[float]:
    """Sample, score, and update policy."""
    gen_config = GenerationConfig(...)
    n = self.config.num_generations
    epoch_rewards: list[float] = []

    for tasks in loader:
        prompts = [_prompt(t) for t in tasks]
        
        # Generate with log probs
        groups, log_probs = generate(
            self.model, self.tokenizer, prompts,
            n_completions=n, config=gen_config,
            return_log_probs=True  # NEW
        )
        
        # Flatten for rewards
        all_completions = [c for group in groups for c in group]
        all_gold = [t.gold_sql for t in tasks for _ in range(n)]
        all_db_id = [t.db_id for t in tasks for _ in range(n)]
        
        # Calculate rewards
        batch_rewards = self.reward_fn(
            prompts=[], completions=all_completions,
            gold_sql=all_gold, db_id=all_db_id,
        )
        epoch_rewards.extend(batch_rewards)
        
        # GRPO: Group-relative advantages
        advantages = []
        for i in range(0, len(batch_rewards), n):
            group_rewards = batch_rewards[i : i + n]
            group_mean = statistics.mean(group_rewards)
            group_advantages = [r - group_mean for r in group_rewards]
            advantages.extend(group_advantages)
        
        # Convert to tensors
        advantages_tensor = torch.tensor(advantages, device=self.model.device)
        
        # Policy loss: negative advantage-weighted log probs
        policy_loss = -(log_probs * advantages_tensor).mean()
        
        # Backpropagation
        policy_loss.backward()
        
        # Gradient clipping (prevent exploding gradients)
        torch.nn.utils.clip_grad_norm_(
            self.model.parameters(), self.config.max_grad_norm
        )
        
        # Update weights
        self.optimizer.step()
        self.optimizer.zero_grad()
        
        self.global_step += 1
    
    return epoch_rewards
```

### 3.3 Important: Switch Model Modes

Make sure:
- `model.train()` in `__init__` (enables gradients)
- `model.eval()` in `generate()` during rollout (no gradients during generation)
- This is already handled correctly in the code above

---

## ✅ Testing Checklist

### Before Training:

1. **Test advantage calculation:**
```python
rewards = [1.0, 0.1, 0.1, 0.0, 0.0, 0.0, 0.0, 0.0]
mean = 0.15
advantages = [r - mean for r in rewards]
print(advantages)  # Should be [0.85, -0.05, ...]
```

2. **Test log prob return:**
```python
from verdict.train.rollout import generate, GenerationConfig
groups, log_probs = generate(model, tokenizer, ["Test"], n_completions=2, return_log_probs=True)
print(log_probs.shape)  # Should be torch.Size([2])
```

3. **Test policy loss calculation:**
```python
advantages = torch.tensor([0.85, -0.15])
log_probs = torch.tensor([-2.5, -3.0])
loss = -(log_probs * advantages).mean()
print(loss)  # Should be a scalar tensor
```

### GSM8K Gate (Math Problems First):

Before training on SQL, test on simpler problems:

```python
# verdict/train/control/gsm8k.py (create this file)
from datasets import load_dataset

def load_gsm8k_train():
    """Load GSM8K math problems for control test."""
    ds = load_dataset("gsm8k", "main", split="train[:100]")
    tasks = []
    for item in ds:
        # Convert to BirdTask-like format
        tasks.append(BirdTask(
            question_id=f"gsm8k_{item['idx']}",
            db_id="gsm8k",  # dummy
            question=item['question'],
            evidence="",
            gold_sql=item['answer'],  # Store answer in gold_sql field
            difficulty="simple",
            db_path=Path("dummy")
        ))
    return tasks

# Test script: scripts/test_gsm8k.py
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig
from verdict.train.control.gsm8k import load_gsm8k_train

config = GRPOTrainingConfig(
    model_name="Qwen/Qwen2.5-0.5B-Instruct",
    num_epochs=1,
    batch_size=4,
)
trainer = GRPOTrainer(config, "dummy_db")
tasks = load_gsm8k_train()
result = trainer.fit(tasks, num_epochs=1, batch_size=4)

# Reward should increase (even slightly) if training works
print("Initial reward:", result['metrics']['reward_mean'][0])
print("Final reward:", result['metrics']['reward_mean'][-1])
```

**Expected:** Reward increases by at least 0.1 over 100 steps.

**If reward doesn't increase:**
- Check gradients: `torch.nn.utils.clip_grad_norm_` returns the norm
- Check loss is decreasing
- Check log_probs have correct sign (should be negative)

---

## 📊 Full Training Timeline

Once GSM8K gate passes:

### Day 1: Setup & GSM8K
- ✅ Fix rollout.py (log probs)
- ✅ Add optimizer to grpo.py
- ✅ Test on GSM8K (100 problems, 1 epoch)
- **Gate:** Reward increases

### Day 2-3: SQL Training
- Load 300-500 simple+moderate BIRD questions
- Train 3 epochs (~300 steps)
- Monitor: reward mean, accuracy, loss
- Save checkpoints

### Day 4: Evaluation
- Test on BIRD dev set
- Compare: base Qwen vs trained Qwen
- Metrics: pass@1, pass@k, execution accuracy

---

## 🚨 Common Issues & Fixes

### Issue 1: "RuntimeError: element 0 of tensors does not require grad"

**Cause:** Model in eval mode or parameters frozen

**Fix:**
```python
# In __init__:
self.model.train()
for param in self.model.parameters():
    param.requires_grad = True
```

### Issue 2: "CUDA out of memory"

**Cause:** Too large batch size or model

**Fix:**
```python
config = GRPOTrainingConfig(
    batch_size=4,  # Reduce from 8
    gradient_accumulation_steps=4,  # Simulate larger batch
)
```

### Issue 3: "Loss is NaN"

**Cause:** Exploding gradients

**Fix:**
```python
# Already added:
torch.nn.utils.clip_grad_norm_(self.model.parameters(), 1.0)
```

### Issue 4: "Rewards don't increase"

**Check:**
1. Log probs are negative? `print(log_probs.mean())`
2. Advantages have variance? `print(advantages.std())`
3. Loss is decreasing? `print(policy_loss.item())`

**Debug:**
```python
# Add to training loop:
logger.info(
    "Step %d | loss %.4f | reward %.4f | adv_std %.4f | log_prob %.4f",
    self.global_step,
    policy_loss.item(),
    statistics.mean(batch_rewards),
    statistics.pstdev(advantages),
    log_probs.mean().item(),
)
```

---

## 🎯 Summary: What to Do Next

### Immediate (Today):
1. ✅ Read this guide
2. ⏳ Update `rollout.py` with log prob code (copy-paste from Step 2)
3. ⏳ Update `grpo.py` __init__ with optimizer (copy-paste from Step 3.1)
4. ⏳ Update `grpo.py` _train_epoch (copy-paste from Step 3.2)

### Tomorrow:
5. Create `gsm8k.py` control dataset
6. Run GSM8K test: `python scripts/test_gsm8k.py`
7. Verify reward increases (gate passed ✅)

### Next 2-3 Days:
8. Train on BIRD SQL (300 questions, 3 epochs)
9. Evaluate trained vs base model
10. Write results in technical report

---

## 📁 Files Modified Summary

| File | What Changed | Status |
|------|--------------|--------|
| `verdict/train/grpo.py` | ✅ Added advantage calculation | Done |
| `verdict/train/grpo.py` | ⏳ Add optimizer in __init__ | Copy code from Step 3.1 |
| `verdict/train/grpo.py` | ⏳ Add policy gradient in _train_epoch | Copy code from Step 3.2 |
| `verdict/train/rollout.py` | ⏳ Add return_log_probs parameter | Copy code from Step 2 |
| `verdict/train/control/gsm8k.py` | ⏳ Create GSM8K loader | New file needed |
| `scripts/test_gsm8k.py` | ⏳ Create test script | New file needed |

---

## ❓ Questions?

**Q: Why GSM8K first?**
A: Simpler domain. If training fails on math, bug is in training code. If training works on math but fails on SQL, problem is domain-specific (SQL harder).

**Q: Do I need GPU?**
A: Yes for training. Qwen 0.5B needs ~2GB VRAM. Use Kaggle free GPU (30h/week) or Colab.

**Q: How long will training take?**
A: GSM8K test: ~10 minutes. Full SQL training: 2-4 hours on single GPU.

**Q: What if I don't have Gemini credits?**
A: Can still do training! Gemini is for calibration (separate). Training uses your own model (Qwen) locally.

---

**Next Step:** Copy code from Step 2 into `rollout.py` and test it.
