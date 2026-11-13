# What to Do Next - Quick Summary

## ✅ Calibration Status

**Gemini API Issue:** Credits exhausted (402 error)

**Current Data:** 34 questions already evaluated
- Plain AI: 47% accuracy
- Verdict GREEN: 62% accuracy, 76% coverage
- **44% reduction in confident wrong answers**

**Decision:** Use 34-question results for now (good enough for proof-of-concept)

**If you want 200 questions:** Add $20-30 credits at https://aistudio.google.com/

---

## 🚨 GRPO Training - What I Fixed & What's Left

### ✅ Step 1: DONE (I just fixed this)
- Added advantage calculation in `verdict/train/grpo.py`
- Code now computes group-relative advantages correctly

### ⏳ Step 2: TODO - Add Log Probabilities

**File:** `verdict/train/rollout.py`

**What to do:** Copy-paste this code to replace the `generate()` function:

```python
def generate(
    model,
    tokenizer,
    prompts: list[str],
    n_completions: int = 4,
    config: GenerationConfig | None = None,
    max_prompt_tokens: int = 512,
    return_log_probs: bool = False,
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
                
                texts = [
                    tokenizer.decode(ids[prompt_len:], skip_special_tokens=True).strip()
                    for ids in sequences
                ]
                results.append(texts)
                
                scores = outputs.scores
                log_probs = []
                for step_idx, step_scores in enumerate(scores):
                    step_log_probs = torch.log_softmax(step_scores, dim=-1)
                    chosen_tokens = sequences[:, prompt_len + step_idx]
                    chosen_log_probs = step_log_probs.gather(1, chosen_tokens.unsqueeze(1)).squeeze(1)
                    log_probs.append(chosen_log_probs)
                
                sequence_log_probs = torch.stack(log_probs, dim=1).sum(dim=1)
                all_log_probs.append(sequence_log_probs)
            else:
                output_ids = model.generate(**inputs, **gen_kwargs)
                prompt_len = inputs["input_ids"].shape[1]
                results.append(
                    [
                        tokenizer.decode(ids[prompt_len:], skip_special_tokens=True).strip()
                        for ids in output_ids
                    ]
                )
    
    if return_log_probs:
        return results, torch.cat(all_log_probs)
    return results
```

### ⏳ Step 3: TODO - Add Optimizer & Policy Gradient

**File:** `verdict/train/grpo.py`

**3A. In `__init__` method, add after line 33:**

```python
# Initialize optimizer
self.optimizer = torch.optim.AdamW(
    self.model.parameters(),
    lr=config.learning_rate,
    weight_decay=0.01,
)
self.model.train()  # Enable gradients
```

**3B. In `_train_epoch` method, replace the TODO section (around line 140-145):**

```python
# Generate with log probs
groups, log_probs = generate(
    self.model, self.tokenizer, prompts,
    n_completions=n, config=gen_config,
    return_log_probs=True
)

# (keep existing reward calculation code)

# Convert advantages to tensor
advantages_tensor = torch.tensor(advantages, device=self.model.device)

# Policy loss
policy_loss = -(log_probs * advantages_tensor).mean()

# Backpropagation
policy_loss.backward()
torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
self.optimizer.step()
self.optimizer.zero_grad()
```

---

## 🎯 Testing Plan

### Test 1: Quick Syntax Check
```bash
python -c "from verdict.train.grpo import GRPOTrainer; print('✅ Import works')"
```

### Test 2: GSM8K Gate (Math Problems)
Create `scripts/test_gsm8k.py`:
```python
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig

config = GRPOTrainingConfig(
    model_name="Qwen/Qwen2.5-0.5B-Instruct",
    num_epochs=1,
    batch_size=4,
)
# ... (see FIX_GRPO_COMPLETE_GUIDE.md for full code)
```

Run: `python scripts/test_gsm8k.py`

**Success:** Reward increases even slightly (e.g., 0.1 → 0.15)

### Test 3: SQL Training
```bash
python scripts/train_grpo.py --questions 100 --epochs 3
```

---

## 📋 Priority Order

1. **First:** Read `FIX_GRPO_COMPLETE_GUIDE.md` (full details)
2. **Then:** Update `rollout.py` (Step 2 code)
3. **Then:** Update `grpo.py` (Step 3A and 3B code)
4. **Then:** Test GSM8K (math gate)
5. **Then:** Train on SQL
6. **Finally:** Evaluate results

---

## 📁 Files to Read

- `FIX_GRPO_COMPLETE_GUIDE.md` ← **START HERE** (detailed guide)
- `PROJECT_DEEP_ANALYSIS_REPORT.md` ← Full project analysis
- `QUICK_STATUS_SUMMARY.md` ← Quick overview

---

## ❓ One Question for You

**Do you have access to a GPU?**

- ✅ Yes (local/Kaggle/Colab) → Proceed with training
- ❌ No → Focus on calibration report & frontend instead

Training needs ~2-4 hours on GPU. Everything else works on CPU.

---

## 🎬 Bottom Line

**Calibration:** ✅ Already have useful results (34 questions, 44% error reduction)

**Training:** ⚠️ Need to add 2 code blocks (Steps 2 & 3), then test

**Time:** ~1-2 hours to fix code, ~4 hours to train

**Blocker:** GPU access (can use Kaggle free tier: 30h/week)
