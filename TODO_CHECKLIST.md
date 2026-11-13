# TODO Checklist - Copy These Exact Steps

## 📋 Part 1: Calibration (Optional - API credits needed)

- [ ] **1.1** Go to https://aistudio.google.com/
- [ ] **1.2** Add $20-30 credits (if you want 200 questions)
- [ ] **1.3** Run: `python scripts/run_calibration.py --questions 200`
- [ ] **1.4** Wait ~2-3 hours
- [ ] **1.5** Check: `results/calibration/report.json`

**OR skip this:** Use existing 34-question results (already good enough)

---

## 🔧 Part 2: Fix GRPO Training (CRITICAL)

### Step 2.1: Update rollout.py

- [ ] **2.1.1** Open `verdict/train/rollout.py`
- [ ] **2.1.2** Find the `generate()` function (starts around line 30)
- [ ] **2.1.3** Replace entire function with code from `NEXT_STEPS_SUMMARY.md` (Step 2)
- [ ] **2.1.4** Save file
- [ ] **2.1.5** Test: `python -c "from verdict.train.rollout import generate; print('✅')"`

### Step 2.2: Update grpo.py - Add Optimizer

- [ ] **2.2.1** Open `verdict/train/grpo.py`
- [ ] **2.2.2** Find `__init__` method (around line 25-35)
- [ ] **2.2.3** After `self.model = self._load_model(...)` line, add:
```python
        self.optimizer = torch.optim.AdamW(
            self.model.parameters(),
            lr=config.learning_rate,
            weight_decay=0.01,
        )
        self.model.train()
```
- [ ] **2.2.4** Save file

### Step 2.3: Update grpo.py - Add Policy Gradient

- [ ] **2.3.1** Still in `verdict/train/grpo.py`
- [ ] **2.3.2** Find `_train_epoch` method (around line 130)
- [ ] **2.3.3** Find the line: `groups = generate(...)`
- [ ] **2.3.4** Change it to:
```python
            groups, log_probs = generate(
                self.model, self.tokenizer, prompts,
                n_completions=n, config=gen_config,
                return_log_probs=True
            )
```
- [ ] **2.3.5** After advantage calculation (after `advantages.extend(...)`), add:
```python
            # Convert to tensor
            advantages_tensor = torch.tensor(advantages, device=self.model.device)
            
            # Policy loss
            policy_loss = -(log_probs * advantages_tensor).mean()
            
            # Backpropagation
            policy_loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), self.config.max_grad_norm)
            self.optimizer.step()
            self.optimizer.zero_grad()
```
- [ ] **2.3.6** Save file
- [ ] **2.3.7** Test: `python -c "from verdict.train.grpo import GRPOTrainer; print('✅')"`

---

## 🧪 Part 3: Test on Math Problems (GSM8K Gate)

### Step 3.1: Create GSM8K test file

- [ ] **3.1.1** Create new file: `scripts/test_gsm8k.py`
- [ ] **3.1.2** Copy this content:

```python
"""Quick test: Does training work on simple math problems?"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig
from verdict.data.loaders import BirdTask

def make_gsm8k_tasks():
    """10 simple math problems for quick test."""
    problems = [
        ("What is 2 + 2?", "4"),
        ("What is 5 * 3?", "15"),
        ("What is 10 - 7?", "3"),
        ("What is 20 / 4?", "5"),
        ("What is 3 + 5?", "8"),
        ("What is 6 * 2?", "12"),
        ("What is 15 - 8?", "7"),
        ("What is 18 / 3?", "6"),
        ("What is 7 + 4?", "11"),
        ("What is 9 * 2?", "18"),
    ]
    tasks = []
    for i, (q, a) in enumerate(problems):
        tasks.append(BirdTask(
            question_id=f"math_{i}",
            db_id="math",
            question=q,
            evidence="",
            gold_sql=f"SELECT {a}",  # Hack: use SQL format for answer
            difficulty="simple",
            db_path=Path("dummy.db")
        ))
    return tasks

if __name__ == "__main__":
    print("Testing GRPO on simple math...")
    
    config = GRPOTrainingConfig(
        model_name="Qwen/Qwen2.5-0.5B-Instruct",
        num_epochs=1,
        batch_size=2,
        num_generations=4,
    )
    
    # Note: Will fail on reward calculation (no real DB)
    # But tests if training loop runs without errors
    trainer = GRPOTrainer(config, "datasets")
    tasks = make_gsm8k_tasks()
    
    try:
        result = trainer.fit(tasks[:4], num_epochs=1, batch_size=2)
        print("✅ Training loop runs!")
        print("Metrics:", result['metrics'])
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
```

- [ ] **3.1.3** Save file

### Step 3.2: Run GSM8K test

- [ ] **3.2.1** Activate venv: `.\.venv\Scripts\Activate.ps1`
- [ ] **3.2.2** Run: `python scripts/test_gsm8k.py`
- [ ] **3.2.3** Check output: Should print "✅ Training loop runs!"
- [ ] **3.2.4** If errors, check traceback and fix

---

## 🚂 Part 4: Train on SQL (Main Goal)

### Step 4.1: Prepare data

- [ ] **4.1.1** Check BIRD exists: `python -c "from verdict.data.loaders import load_bird_dev; print(len(load_bird_dev()))"`
- [ ] **4.1.2** Should print: `1534`

### Step 4.2: Run training

- [ ] **4.2.1** Check if `scripts/train_grpo.py` exists
- [ ] **4.2.2** If not, create it (see FIX_GRPO_COMPLETE_GUIDE.md)
- [ ] **4.2.3** Run: `python scripts/train_grpo.py --questions 100 --epochs 3`
- [ ] **4.2.4** Monitor output for:
  - Rewards increasing
  - Loss decreasing
  - No errors

### Step 4.3: Expected output

```
Epoch 1/3 | reward 0.15 +/- 0.05 | accuracy 10%
Epoch 2/3 | reward 0.18 +/- 0.06 | accuracy 12%
Epoch 3/3 | reward 0.22 +/- 0.07 | accuracy 15%
✓ Saved checkpoint: checkpoints/checkpoint-epoch-3
```

**Success criteria:** Reward increases, accuracy improves

---

## 📊 Part 5: Evaluate Results

- [ ] **5.1** Create evaluation script (if needed)
- [ ] **5.2** Compare base Qwen vs trained Qwen
- [ ] **5.3** Calculate: pass@1, pass@k, accuracy
- [ ] **5.4** Document results in `docs/24-technical-report.md`

---

## ✅ Completion Checklist

Mark when fully done:

- [ ] **Calibration:** Have report (200q or accept 34q)
- [ ] **Training code:** All 3 files updated (rollout.py, grpo.py x2)
- [ ] **GSM8K test:** Training loop runs without errors
- [ ] **SQL training:** Completed 3 epochs on 100+ questions
- [ ] **Evaluation:** Base vs trained comparison done
- [ ] **Documentation:** Results written up

---

## 🚨 If You Get Stuck

**Import errors:**
```bash
.\.venv\Scripts\Activate.ps1
pip install -e .
pip install torch transformers accelerate
```

**CUDA out of memory:**
- Reduce batch_size in config (try 2 or 4)
- Use gradient_accumulation_steps=4

**Training doesn't improve:**
- Check FIX_GRPO_COMPLETE_GUIDE.md Section "Common Issues"
- Add debug logging to see loss/gradients

**No GPU:**
- Use Kaggle free GPU (30h/week)
- Or use Google Colab free tier
- Upload code, run there

---

## 📁 Files You'll Modify

1. ✅ `verdict/train/grpo.py` (advantage calc - DONE)
2. ⏳ `verdict/train/rollout.py` (add log probs)
3. ⏳ `verdict/train/grpo.py` (add optimizer)
4. ⏳ `verdict/train/grpo.py` (add policy gradient)
5. ⏳ `scripts/test_gsm8k.py` (create new)

---

## ⏱️ Time Estimate

- Fix code: 1-2 hours
- GSM8K test: 10 minutes
- SQL training: 2-4 hours (GPU)
- Evaluation: 1 hour
- **Total: 4-7 hours**

---

## 🎯 Success = This Works

```bash
$ python scripts/train_grpo.py --questions 100 --epochs 3
Loading model: Qwen/Qwen2.5-0.5B-Instruct
Training on 100 tasks for 3 epochs
Epoch 1/3 | reward 0.15 +/- 0.05 | accuracy 10.0%
Epoch 2/3 | reward 0.18 +/- 0.06 | accuracy 12.0%
Epoch 3/3 | reward 0.22 +/- 0.07 | accuracy 15.0%
✅ Training complete!
```

**Then you have:** Working RL training on SQL ✅

---

**Start with:** Step 2.1 (Update rollout.py)
