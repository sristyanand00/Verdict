#!/usr/bin/env python
"""Merge a LoRA adapter into its base model and prepare it for Ollama.

Step 1 (this script, CPU only, so it can run while the GPU is busy):
    python scripts/export_model.py --adapter E:\\verdict_runs\\sft_v2\\best --out E:\\verdict_runs\\export\\sft_v2

Writes to --out:
    merged/     the full model in float16 with its tokenizer (Hugging Face format)
    Modelfile   for ``ollama create``, with the Qwen chat format and stop tokens

Step 2 (llama.cpp's converter, also CPU only):
    python E:\\llama.cpp\\convert_hf_to_gguf.py E:\\verdict_runs\\export\\sft_v2\\merged
        --outfile E:\\verdict_runs\\export\\sft_v2\\verdict-qwen.gguf --outtype q8_0

Step 3 (on the laptop, with the .gguf and Modelfile in one folder):
    ollama create verdict-qwen -f Modelfile

The prompt the app sends must match the training prompt (the system
instruction and the "### Database Schema / ### Question / ### Hint" layout in
verdict/train/data_prep.py), or accuracy drops.
"""

import argparse
import sys
from pathlib import Path

import torch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from verdict.train.modeling import load_for_inference  # noqa: E402

GGUF_NAME = "verdict-qwen.gguf"

# Qwen2.5 chat format (ChatML). Ollama fills .System and .Messages from the
# OpenAI-compatible request the backend sends.
MODELFILE = '''FROM ./{gguf}

TEMPLATE """{{{{- if .System }}}}<|im_start|>system
{{{{ .System }}}}<|im_end|>
{{{{ end }}}}{{{{- range .Messages }}}}{{{{- if ne .Role "system" }}}}<|im_start|>{{{{ .Role }}}}
{{{{ .Content }}}}<|im_end|>
{{{{ end }}}}{{{{- end }}}}<|im_start|>assistant
"""

PARAMETER stop "<|im_end|>"
PARAMETER stop "<|endoftext|>"
PARAMETER num_ctx 8192
PARAMETER num_predict 256
'''


def modelfile_text(gguf_name: str = GGUF_NAME) -> str:
    return MODELFILE.format(gguf=gguf_name)


def main() -> int:
    p = argparse.ArgumentParser(description="Merge a LoRA adapter and write an Ollama Modelfile",
                                formatter_class=argparse.RawDescriptionHelpFormatter, epilog=__doc__)
    p.add_argument("--adapter", type=Path, required=True, help="LoRA adapter folder (e.g. sft_v2\\best)")
    p.add_argument("--out", type=Path, required=True, help="output folder")
    args = p.parse_args()

    merged = args.out / "merged"
    merged.mkdir(parents=True, exist_ok=True)
    print(f"Merging {args.adapter} into its base model on the CPU", flush=True)
    model, tokenizer = load_for_inference(args.adapter, device="cpu")
    model.to(dtype=torch.float16)
    model.save_pretrained(merged, safe_serialization=True)
    tokenizer.save_pretrained(merged)
    (args.out / "Modelfile").write_text(modelfile_text(), encoding="utf-8")
    print(f"Saved the merged model to {merged}", flush=True)
    print(f"Saved {args.out / 'Modelfile'}", flush=True)
    print("Next: convert to GGUF with llama.cpp (see the top of this script).", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
