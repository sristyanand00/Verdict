# 🚀 Kaggle Training Quick Start - FIXED

## ✅ What Was Fixed

The Kaggle training was failing with:
```
FileNotFoundError: databases not found under /kaggle/working/datasets/dev_databases/dev_databases
```

**Root Cause**: Path configuration inconsistency in the codebase:
- `config.db_path()` expects: `data_root/dev_databases/db_id/db_id.sqlite`
- `SQLRewardFunction.db_path()` expects: `db_root/db_id/db_id.sqlite`

## 📋 Working Kaggle Notebook

### Cell 1: Check GPU
```python
import torch
print(f"CUDA available: {torch.cuda.is_available()}")
print(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'None'}")
```

### Cell 2: Clone Repository
```python
import os

if os.path.exists("/kaggle/working/Verdict"):
    print("⚠️ Removing old Verdict folder...")
    !rm -rf /kaggle/working/Verdict

print("📥 Cloning repo from GitHub...")
!git clone https://github.com/sristyanand00/Verdict.git /kaggle/working/Verdict

print("\n✅ Repository cloned!")
print("\n=== Checking grpo.py ===")
!wc -l /kaggle/working/Verdict/verdict/train/grpo.py
```

### Cell 3: Link BIRD Dataset
```python
import os
import shutil

print("🔍 Finding BIRD dataset...")

# Your Kaggle dataset path
input_path = "/kaggle/input/datasets/sristyanand00/bird-sql-benchmark"
output_path = "/kaggle/working/datasets"

if os.path.exists(input_path):
    print(f"✅ Found BIRD dataset at: {input_path}")
    
    # Create local datasets folder
    os.makedirs(output_path, exist_ok=True)

    # Copy files
    shutil.copy(
        os.path.join(input_path, "dev.json"),
        os.path.join(output_path, "dev.json")
    )
    print(f"✅ Copied dev.json")

    # Copy dev_databases folder
    if os.path.exists(os.path.join(input_path, "dev_databases")):
        shutil.copytree(
            os.path.join(input_path, "dev_databases"),
            os.path.join(output_path, "dev_databases"),
            dirs_exist_ok=True
        )
        print(f"✅ Copied dev_databases/")

    # Save path for later cells
    with open("/kaggle/working/bird_path.txt", "w") as f:
        f.write(output_path)

    print(f"\n🎯 BIRD dataset ready at: {output_path}")
else:
    print(f"❌ Dataset not found at: {input_path}")
    raise FileNotFoundError("BIRD dataset not found")
```

### Cell 4: Install Dependencies
```python
print("📦 Installing dependencies...")

!pip install -q transformers accelerate datasets sqlglot

# Verify installations
import transformers
import accelerate
import sqlglot

print(f"\n✅ transformers: {transformers.__version__}")
print(f"✅ accelerate: {accelerate.__version__}")
print(f"✅ sqlglot installed")
print("\n🎯 All packages ready!")
```

### Cell 5: Verify Dataset
```python
import sys
import json

# Add verdict repo to Python path
sys.path.insert(0, '/kaggle/working/Verdict')

# Load BIRD path
with open("/kaggle/working/bird_path.txt", "r") as f:
    bird_path = f.read().strip()

# Load dev.json
dev_json_path = f"{bird_path}/dev.json"
with open(dev_json_path, 'r') as f:
    data = json.load(f)

print(f"✅ Loaded {len(data)} questions from BIRD dev set")
print(f"\n📋 First question example:")
print(f"Question: {data[0]['question']}")
print(f"Database: {data[0]['db_id']}")
print(f"\n🎯 Dataset verified and ready for training!")
```

### Cell 6: Quick Test Training (FIXED!)
```python
import sys
sys.path.insert(0, '/kaggle/working/Verdict')

from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig
from verdict.data.loaders import load_bird_dev
from pathlib import Path
import torch

# Load BIRD path
with open("/kaggle/working/bird_path.txt", "r") as f:
    bird_path = f.read().strip()

# Setup paths correctly - THIS IS THE FIX!
dev_json_path = Path(bird_path) / "dev.json"
data_root = Path(bird_path)  # For load_bird_dev: expects data_root/dev_databases/...
db_root = Path(bird_path) / "dev_databases"  # For GRPOTrainer: expects db_root/db_id/...

print(f"📁 Data root: {data_root}")
print(f"📁 DB root: {db_root}")
print(f"📄 dev.json: {dev_json_path}")

# Create training config
config = GRPOTrainingConfig(
    model_name="Qwen/Qwen2.5-0.5B-Instruct",
    num_epochs=1,
    batch_size=4,
    num_generations=8,
    temperature=0.7,
    checkpoint_dir=Path("/kaggle/working/test_output"),
    device="cuda" if torch.cuda.is_available() else "cpu"
)

# Load BIRD tasks
print("\n📚 Loading BIRD dataset...")
all_tasks = load_bird_dev(dev_json_path, data_root=data_root)
print(f"✅ Loaded {len(all_tasks)} tasks")

# Use only 5 questions for quick test
test_tasks = all_tasks[:5]
print(f"\n🧪 Testing with {len(test_tasks)} questions:")
for i, task in enumerate(test_tasks, 1):
    print(f"  {i}. {task.db_id}: {task.question[:60]}...")

# Initialize trainer
print("\n⚙️ Initializing GRPOTrainer...")
trainer = GRPOTrainer(config=config, db_root=db_root)

print("\n🚀 Running quick test: 5 questions, 1 epoch")
print("Expected time: 5-10 minutes\n")
print("=" * 70)

# Train
result = trainer.fit(test_tasks, num_epochs=1, batch_size=4)

print("=" * 70)
print("\n✅ Test complete!")
print(f"\n📊 Metrics:")
for key, value in result['metrics'].items():
    print(f"  {key}: {value}")

print("\n✅ If no errors above, proceed to Cell 7 for full training!")
```

### Cell 7: Full Training (Run after Cell 6 succeeds)
```python
# Use more questions and epochs for real training
full_tasks = all_tasks[:100]  # Start with 100 questions

config_full = GRPOTrainingConfig(
    model_name="Qwen/Qwen2.5-0.5B-Instruct",
    num_epochs=3,
    batch_size=4,
    num_generations=8,
    temperature=0.7,
    checkpoint_dir=Path("/kaggle/working/full_output"),
    device="cuda"
)

trainer_full = GRPOTrainer(config=config_full, db_root=db_root)

print(f"🚀 Starting full training: {len(full_tasks)} questions, 3 epochs")
result_full = trainer_full.fit(full_tasks, num_epochs=3, batch_size=4)

print("\n✅ Full training complete!")
print(f"📊 Final Metrics: {result_full['metrics']}")
```

## 🎯 Key Points

1. **Two different path expectations**:
   - `load_bird_dev()` needs `data_root` (parent of `dev_databases`)
   - `GRPOTrainer()` needs `db_root` (the `dev_databases` folder itself)

2. **Why this happens**:
   - `config.db_path()` adds `/dev_databases/` to the path
   - `SQLRewardFunction.db_path()` does NOT add it

3. **The fix**:
   ```python
   data_root = Path(bird_path)                    # /kaggle/working/datasets
   db_root = Path(bird_path) / "dev_databases"    # /kaggle/working/datasets/dev_databases
   ```

## 📦 Files Created

- `kaggle_training_fix.md` - Detailed explanation of the fix
- `KAGGLE_CELL_6_FIXED.py` - Ready-to-use Cell 6 code
- `KAGGLE_QUICK_START.md` - This file

All changes committed and pushed to GitHub! ✅
