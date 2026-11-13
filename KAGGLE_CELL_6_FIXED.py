# Cell 6: Quick Test Training (FIXED VERSION)
# Copy-paste this entire cell into your Kaggle notebook

import sys
sys.path.insert(0, '/kaggle/working/Verdict')

from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig
from verdict.data.loaders import load_bird_dev
from pathlib import Path
import torch

# Load BIRD path
with open("/kaggle/working/bird_path.txt", "r") as f:
    bird_path = f.read().strip()

# Setup paths correctly
dev_json_path = Path(bird_path) / "dev.json"
data_root = Path(bird_path)  # For load_bird_dev: expects data_root/dev_databases/...
db_root = Path(bird_path) / "dev_databases"  # For GRPOTrainer: expects db_root/db_id/...

print(f"📁 Data root: {data_root}")
print(f"📁 DB root: {db_root}")
print(f"📄 dev.json: {dev_json_path}")

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
