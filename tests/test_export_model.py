"""The Ollama Modelfile written next to the exported model."""

import sys
from pathlib import Path

import pytest

pytest.importorskip("torch")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

from export_model import modelfile_text  # noqa: E402


def test_modelfile_uses_qwen_chat_format():
    text = modelfile_text("m.gguf")
    assert text.startswith("FROM ./m.gguf")
    assert "<|im_start|>system\n{{ .System }}<|im_end|>" in text
    assert "{{- range .Messages }}" in text and "{{{{" not in text
    assert text.rstrip().endswith('PARAMETER num_predict 256')
    assert 'PARAMETER stop "<|im_end|>"' in text
