# Training on Kaggle

Five cells. Run them in order in a Kaggle notebook.

**Notebook settings (right panel):**
- Accelerator: **GPU T4 x2**. Only one GPU is used; T4 is the right choice over P100.
- Internet: **On** (needed to clone the repo and download the model).
- Add your BIRD dataset with **Add Input**. It must contain `dev.json` and `dev_databases/`.

## Cell 1: check the GPU

```python
import torch
print("CUDA:", torch.cuda.is_available())
print("GPU:", torch.cuda.get_device_name(0) if torch.cuda.is_available() else "none")
print("torch", torch.__version__)
```

If CUDA is `False`, turn on the GPU in settings and restart the session.

## Cell 2: get the code

```python
!rm -rf /kaggle/working/Verdict
!git clone --depth 1 https://github.com/sristyanand00/verdict.git /kaggle/working/Verdict
!pip install -q sqlglot
%cd /kaggle/working/Verdict
!git log -1 --oneline
```

Only `sqlglot` is installed. Kaggle already has torch and transformers;
reinstalling them can break the CUDA setup.

## Cell 3: find the dataset

```python
import glob, os

hits = glob.glob("/kaggle/input/**/dev.json", recursive=True)
hits = [h for h in hits if os.path.isdir(os.path.join(os.path.dirname(h), "dev_databases"))]
assert hits, "No dev.json next to a dev_databases/ folder under /kaggle/input. Check Add Input."
BIRD = os.path.dirname(hits[0])

os.environ["VERDICT_DATA_ROOT"] = BIRD
os.environ["VERDICT_RESULTS_ROOT"] = "/kaggle/working/results"
print("BIRD data:", BIRD)
print("databases:", len(os.listdir(os.path.join(BIRD, "dev_databases"))))
```

The databases are opened read-only, so they are used straight from
`/kaggle/input`. There's no need to copy them.

## Cell 4: quick test (about 10 to 20 minutes)

```python
!python scripts/train_grpo.py --num-tasks 20 --epochs 1 --eval-max-tasks 4 \
    --checkpoint-dir /kaggle/working/test_ckpt
```

You should see lines like:

```
[epoch 1/1 batch 1/4] correct 3/32, ran 20/32, loss -0.0012 | gen 40s, sql 1s, update 6s
```

- `ran` is how many queries executed without an error. `correct` is how many
  returned the right answer. Both should be above zero for most batches.
- Note the seconds per batch. Multiply by the number of batches to estimate
  the full run.
- If you get `CUDA out of memory`, add `--micro-batch-size 2`, or 1.

## Cell 5: real training

```python
!python scripts/train_grpo.py --num-tasks 300 --epochs 2 \
    --checkpoint-dir /kaggle/working/checkpoints
```

- 300 questions are spread across all the databases: 240 to train on and 60 to
  check progress on.
- Validation accuracy is printed before training and after every epoch. That
  number shows whether the model is improving.
- Checkpoints are saved in `/kaggle/working/checkpoints/`: `latest/` after
  every epoch, and `best/` when validation accuracy improves.
- Results are saved to `/kaggle/working/results/training_results.json`.

**For long runs**, use **Save Version → Save & Run All (Commit)** instead of
running cells interactively. The run then continues after you close the
browser, and everything in `/kaggle/working` is kept as the notebook's output.
Kaggle stops any session after 12 hours.

## Loading the trained model later

```python
from transformers import AutoModelForCausalLM, AutoTokenizer
model = AutoModelForCausalLM.from_pretrained("/kaggle/working/checkpoints/best")
tok = AutoTokenizer.from_pretrained("/kaggle/working/checkpoints/best")
```

## A note on the data

BIRD dev is also BIRD's official test set. Training on it is fine for
development, but a model trained on dev cannot report a BIRD dev score. For
results you publish, train on BIRD **train** and evaluate on dev.
