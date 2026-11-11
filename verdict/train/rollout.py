"""Sample several completions per prompt from a Hugging Face causal LM.

    generate(model, tokenizer, prompts, n_completions) -> list[list[str]]
"""

from dataclasses import dataclass

import torch


@dataclass
class GenerationConfig:
    temperature: float = 0.7
    max_tokens: int = 256
    top_p: float = 0.95
    top_k: int = 50
    repetition_penalty: float = 1.0

    def to_dict(self) -> dict:
        """Keyword arguments for ``model.generate``."""
        return {
            "temperature": self.temperature,
            "max_new_tokens": self.max_tokens,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "repetition_penalty": self.repetition_penalty,
            "do_sample": self.temperature > 0,
        }


def generate(
    model,
    tokenizer,
    prompts: list[str],
    n_completions: int = 4,
    config: GenerationConfig | None = None,
    max_prompt_tokens: int = 512,
) -> list[list[str]]:
    """Return ``n_completions`` sampled completions for each prompt.

    Runs on whatever device the model is already on. All completions for one
    prompt come from a single ``generate`` call (``num_return_sequences``).
    """
    config = config or GenerationConfig()
    gen_kwargs = {
        **config.to_dict(),
        "num_return_sequences": n_completions,
        "pad_token_id": tokenizer.pad_token_id or tokenizer.eos_token_id,
    }

    model.eval()
    results = []
    with torch.no_grad():
        for prompt in prompts:
            inputs = tokenizer(
                prompt, return_tensors="pt", truncation=True, max_length=max_prompt_tokens
            ).to(model.device)
            output_ids = model.generate(**inputs, **gen_kwargs)
            prompt_len = inputs["input_ids"].shape[1]
            results.append(
                [
                    tokenizer.decode(ids[prompt_len:], skip_special_tokens=True).strip()
                    for ids in output_ids
                ]
            )
    return results
