#!/usr/bin/env python
"""Turn an exported GGUF back into a Hugging Face model folder for training.

For continuing training on a machine that does not have the LoRA adapter but
does have the exported GGUF of the merged model:

    pip install gguf
    python scripts/gguf_to_hf.py --gguf /data/verdict-qwen.gguf --out /data/sft_v2_from_gguf

The weights in a q8_0 GGUF are 8-bit, so the result is close to the merged
model but not identical to it. Evaluate it on BIRD dev (scripts/evaluate.py)
before training from it, and compare with the original model's score.

The result is a full model, not an adapter. Train from it with
``train_grpo.py --model <out folder>`` (without ``--init-adapter``).
"""

import argparse
import sys
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

BASE_MODEL = "Qwen/Qwen2.5-Coder-1.5B-Instruct"


def copy_weights(target: torch.nn.Module, state: dict) -> None:
    """Copy ``state`` into ``target``; every name and shape must match."""
    wanted = target.state_dict()
    missing = sorted(set(wanted) - set(state))
    extra = sorted(set(state) - set(wanted))
    if missing or extra:
        raise ValueError(f"weight names differ: missing {missing[:5]}, unexpected {extra[:5]}")
    wrong = [k for k in wanted if wanted[k].shape != state[k].shape]
    if wrong:
        raise ValueError(f"weight shapes differ for {wrong[:5]}")
    target.load_state_dict(state)


def main() -> int:
    p = argparse.ArgumentParser(description="Convert a GGUF export back to a Hugging Face model folder",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--gguf", type=Path, required=True, help="the .gguf file")
    p.add_argument("--out", type=Path, required=True, help="output folder")
    p.add_argument("--base-model", default=BASE_MODEL, help="model the GGUF was fine-tuned from")
    args = p.parse_args()

    if not args.gguf.is_file():
        print(f"GGUF file not found: {args.gguf}")
        return 1

    print(f"Reading {args.gguf} (needs about 14 GB of RAM)", flush=True)
    loaded = AutoModelForCausalLM.from_pretrained(str(args.gguf.parent), gguf_file=args.gguf.name)
    state = loaded.float().state_dict()

    # Config and tokenizer come from the official base model, so the prompt
    # format and stop tokens are exactly the ones used in training.
    model = AutoModelForCausalLM.from_pretrained(args.base_model).float()
    copy_weights(model, state)
    model.half()

    args.out.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(args.out, safe_serialization=True)
    AutoTokenizer.from_pretrained(args.base_model).save_pretrained(args.out)
    print(f"Saved the model to {args.out}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
