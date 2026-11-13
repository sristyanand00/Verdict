# Fixed Kaggle Training Notebook - Cell 6

Replace Cell 6 with this corrected version:

```python
# Cell 6: Quick Test Training (FIXED)
import sys
sys.path.insert(0, '/kaggle/working/Verdict')

from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig
from verdict.data.loaders import load_bird_dev
from pathlib import Path
import torch

# Load BIRD path
with open("/kaggle/working/bird_path.txt", "r") as f:
    bird_path = f.read().strip()

# IMPORTANT FIX: Pass the parent directory (not dev_databases)
# The loader expects: data_root/dev_databases/db_id/db_id.sqlite
dev_json_path = Path(bird_path) / "dev.json"
data_root = Path(bird_path)  # <- FIXED: Use parent, not dev_databases

# Create training config
config = GRPOTrainingConfig(
    model_name="Qwen/Qwen2.5-0.5B-Instruct",
    num_epochs=1,  # Quick test: 1 epoch
    batch_size=4,
    num_generations=8,
    temperature=0.7,
    checkpoint_dir=Path("/kaggle/working/test_output"),
    device="cuda" if torch.cuda.is_available() else "cpu"
)

# Load BIRD tasks (pass data_root, not db_root)
print("📚 Loading BIRD dataset...")
all_tasks = load_bird_dev(dev_json_path, data_root=data_root)
print(f"✅ Loaded {len(all_tasks)} tasks")

# Use only 5 questions for quick test
test_tasks = all_tasks[:5]
print(f"🧪 Testing with {len(test_tasks)} questions")

# Initialize trainer - pass data_root/dev_databases for db_root
# GRPOTrainer's db_root should point to dev_databases folder directly
# because SQLRewardFunction expects: db_root/db_id/db_id.sqlite
trainer = GRPOTrainer(config=config, db_root=data_root / "dev_databases")

print("\n🧪 Running quick test: 5 questions, 1 epoch")
print("Expected time: 5-10 minutes\n")

# Train
result = trainer.fit(test_tasks, num_epochs=1, batch_size=4)

print("\n✅ Test complete!")
print(f"Metrics: {result['metrics']}")
print("If no errors, proceed to Cell 7 for full training.")
```

## The Issue

The problem was in how we passed the database root paths. There are TWO different path expectations:

### 1. For `load_bird_dev()` - Pass parent directory
**WRONG:**
```python
db_root = Path(bird_path) / "dev_databases"  # ❌
all_tasks = load_bird_dev(dev_json_path, data_root=db_root)
```

**CORRECT:**
```python
data_root = Path(bird_path)  # ✅ Parent of dev_databases
all_tasks = load_bird_dev(dev_json_path, data_root=data_root)
```

### 2. For `GRPOTrainer()` - Pass dev_databases directory
**WRONG:**
```python
trainer = GRPOTrainer(config=config, db_root=data_root)  # ❌
```

**CORRECT:**
```python
trainer = GRPOTrainer(config=config, db_root=data_root / "dev_databases")  # ✅
```

## Why?

There are TWO different expectations in the codebase:

### `config.db_path()` adds `/dev_databases/`:
```python
def db_path(db_id: str, root: Path | None = None) -> Path:
    return (root or data_root()) / "dev_databases" / db_id / f"{db_id}.sqlite"
```
So it expects: `data_root/dev_databases/db_id/db_id.sqlite`

### `SQLRewardFunction.db_path()` does NOT add `/dev_databases/`:
```python
def db_path(self, db_id: str) -> Path:
    return self.db_root / db_id / f"{db_id}.sqlite"
```
So it expects: `db_root` to already BE the `dev_databases` folder.

This is why we pass different paths to each component!
