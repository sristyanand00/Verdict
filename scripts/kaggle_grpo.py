#!/usr/bin/env python
"""Run the whole GRPO job on Kaggle in one go: setup, check, training, test, export.

Meant for a Kaggle notebook started with "Save & Run All", so nothing has to be
watched. Notebook settings: accelerator GPU T4, internet on, and a dataset
holding verdict-qwen.gguf (the exported SFT model) added as input.

    !git clone -q https://github.com/sristyanand00/verdict.git /kaggle/working/verdict
    !python /kaggle/working/verdict/scripts/kaggle_grpo.py

Steps: rebuild the SFT model from the GGUF, download BIRD, run a short GRPO
check, pick how many questions fit in the training time from the check's batch
times, train one epoch, evaluate on BIRD dev, export to GGUF.

Left in the notebook output (/kaggle/working): grpo_v1/ (the adapter), eval/,
logs/ and export/verdict-qwen-grpo.gguf with its Modelfile. A failure after
training does not fail the notebook, so the trained adapter is still saved.
"""

import argparse
import glob
import os
import re
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUT = Path("/kaggle/working")
TMP = Path("/tmp")
SFT = TMP / "sft_v2_from_gguf"
TRAIN = TMP / "bird_train"
DEV = TMP / "bird_dev"
BIRD_URL = "https://bird-bench.oss-cn-beijing.aliyuncs.com/{}.zip"
SCHEMA_CHARS = "12000"
BATCH = 4  # questions per GRPO batch (train_grpo.py default)


def batch_seconds(log_text: str) -> list[int]:
    """Seconds taken by each GRPO batch, read from the training log."""
    pattern = r"\| gen (\d+)s, sql (\d+)s, update (\d+)s"
    return [sum(int(x) for x in m) for m in re.findall(pattern, log_text)]


def questions_that_fit(seconds: list[int], hours: float, most: int) -> int:
    """How many questions fit in ``hours`` of training, from the check's batch times."""
    average = sum(seconds) / len(seconds)
    fit = int(hours * 3600 / average) * BATCH
    return max(BATCH, min(most, fit))


def run(*command: str, log: str | None = None) -> None:
    """Run a command in the repo; raise if it fails."""
    if log:
        command = (sys.executable, "scripts/train_run.py", str(OUT / "logs" / log), *command)
    print(">>>", " ".join(command), flush=True)
    subprocess.run(command, cwd=REPO, check=True)


def find(root: Path, name: str) -> Path:
    hits = [p for p in glob.glob(f"{root}/**/{name}", recursive=True) if "__MACOSX" not in p]
    if not hits:
        raise FileNotFoundError(f"{name} not found under {root}")
    return Path(hits[0])


def fetch_bird(split: str) -> Path:
    """Download and unpack BIRD ``dev`` or ``train``; return the unpacked folder."""
    archive, raw = TMP / f"{split}.zip", TMP / f"bird_{split}_raw"
    run("curl", "-sS", "-L", "--fail", "--retry", "3", "-o", str(archive), BIRD_URL.format(split))
    zipfile.ZipFile(archive).extractall(raw)
    archive.unlink()
    inner = find(raw, f"{split}_databases.zip")
    zipfile.ZipFile(inner).extractall(inner.parent)
    inner.unlink()
    return raw


def prepare_train() -> None:
    if (TRAIN / "train_databases").is_dir():
        return
    raw = fetch_bird("train")
    TRAIN.mkdir(parents=True, exist_ok=True)
    shutil.copy(find(raw, "train.json"), TRAIN / "train_all.json")
    shutil.move(str(find(raw, "train_databases")), TRAIN / "train_databases")
    (TRAIN / "schemas.json").write_text("{}")


def prepare_dev() -> None:
    if (DEV / "dev_databases").is_dir():
        return
    raw = fetch_bird("dev")
    DEV.mkdir(parents=True, exist_ok=True)
    shutil.copy(find(raw, "dev.json"), DEV / "dev.json")
    shutil.move(str(find(raw, "dev_databases")), DEV / "dev_databases")


def grpo(num_tasks: int, eval_tasks: int, folder: Path, log: str, save_every: int) -> None:
    run("python", "scripts/train_grpo.py", "--train-dir", str(TRAIN), "--model", str(SFT),
        "--lora-r", "16", "--lr", "1e-5", "--epochs", "1", "--num-tasks", str(num_tasks),
        "--eval-max-tasks", str(eval_tasks), "--checkpoint-dir", str(folder),
        "--max-schema-chars", SCHEMA_CHARS,
        # A T4 runs out of memory on long prompts with the default of 4.
        "--micro-batch-size", "2", "--save-every", str(save_every), log=log)


def evaluate_dev(model: Path) -> None:
    prepare_dev()
    os.environ["VERDICT_DATA_ROOT"] = str(DEV)
    os.environ["VERDICT_RESULTS_ROOT"] = str(OUT / "eval")
    run("python", "scripts/evaluate.py", "--model", str(model), "--label", "grpo_v1",
        "--max-schema-chars", SCHEMA_CHARS, "--timeout", "30", "--workers", "4", "--gen-batch", "8",
        log="eval_grpo_v1.log")


def export(adapter: Path) -> None:
    work = TMP / "export"
    run("python", "scripts/export_model.py", "--adapter", str(adapter), "--out", str(work),
        log="export.log")
    llama = TMP / "llama.cpp"
    if not llama.is_dir():
        run("git", "clone", "-q", "--depth", "1", "https://github.com/ggml-org/llama.cpp", str(llama))
    run(sys.executable, "-m", "pip", "install", "-q", str(llama / "gguf-py"), "sentencepiece", "protobuf")
    final = OUT / "export"
    final.mkdir(parents=True, exist_ok=True)
    name = "verdict-qwen-grpo.gguf"
    run("python", str(llama / "convert_hf_to_gguf.py"), str(work / "merged"),
        "--outfile", str(final / name), "--outtype", "q8_0", log="gguf.log")
    modelfile = (work / "Modelfile").read_text(encoding="utf-8")
    (final / "Modelfile").write_text(modelfile.replace("verdict-qwen.gguf", name), encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description="GRPO on Kaggle from start to finish",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--hours", type=float, default=5.5, help="training time to fill with questions")
    p.add_argument("--max-questions", type=int, default=500)
    args = p.parse_args()

    os.environ["CUDA_VISIBLE_DEVICES"] = "0"
    # Less memory lost to fragmentation, which matters on a 15 GB T4.
    os.environ["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    (OUT / "logs").mkdir(parents=True, exist_ok=True)
    # train_grpo.py writes training_results.json here; the repo folder is removed at the end.
    os.environ["VERDICT_RESULTS_ROOT"] = str(OUT / "eval")

    print("STEP 1/6 packages", flush=True)
    run(sys.executable, "-m", "pip", "install", "-q", "sqlglot", "gguf>=0.10.0", "peft")
    # Kaggle ships an old torchao that makes peft refuse to add LoRA. Nothing here uses it.
    run(sys.executable, "-m", "pip", "uninstall", "-y", "-q", "torchao")

    print("STEP 2/6 SFT model from the GGUF", flush=True)
    if not (SFT / "model.safetensors").exists():
        found = glob.glob("/kaggle/input/**/verdict-qwen.gguf", recursive=True)
        if not found:
            print("verdict-qwen.gguf is not in /kaggle/input: add the dataset to the notebook")
            return 1
        run("python", "scripts/gguf_to_hf.py", "--gguf", found[0], "--out", str(SFT))

    print("STEP 3/6 BIRD train data", flush=True)
    prepare_train()

    print("STEP 4/6 short GRPO check, then training", flush=True)
    check = TMP / "grpo_check"
    grpo(20, 20, check, "grpo_check.log", save_every=2)
    seconds = batch_seconds((OUT / "logs" / "grpo_check.log").read_text(errors="replace"))
    if not seconds:
        print("The check printed no batch lines; not starting the long run")
        return 1
    questions = questions_that_fit(seconds, args.hours, args.max_questions)
    print(f"Check: {sum(seconds) / len(seconds):.0f} s per batch; training on {questions} questions", flush=True)
    shutil.rmtree(check, ignore_errors=True)
    trained = OUT / "grpo_v1"
    try:
        grpo(questions, 100, trained, "grpo_v1.log", save_every=10)
    except subprocess.CalledProcessError as e:
        if not (trained / "latest").is_dir():
            raise
        print(f"TRAINING STOPPED EARLY (exit code {e.returncode}); going on with the last saved "
              "checkpoint. See logs/grpo_v1.log for how far it got.", flush=True)
    # best/ is written only when an epoch finishes; latest/ also during the epoch.
    adapter = trained / "best" if (trained / "best").is_dir() else trained / "latest"
    print(f"Using the adapter in {adapter}", flush=True)

    # From here on, a failure must not fail the notebook: the adapter is trained.
    for number, name, step in ((5, "test on BIRD dev", evaluate_dev), (6, "export to GGUF", export)):
        print(f"STEP {number}/6 {name}", flush=True)
        try:
            step(adapter)
        except Exception as e:  # noqa: BLE001
            print(f"STEP {number} FAILED: {e}", flush=True)

    shutil.rmtree(REPO, ignore_errors=True)
    print("ALL DONE", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
