"""Batched generation for text-to-SQL model rollouts.

    generate(model, prompts, n_completions, temperature, max_tokens) -> list[list[str]]

Uses vLLM for efficient batched inference. Generates n completions per prompt.
"""

from typing import Optional
from pathlib import Path
import torch
from dataclasses import dataclass


@dataclass
class GenerationConfig:
    """Configuration for model generation."""
    
    temperature: float = 0.7
    max_tokens: int = 256
    top_p: float = 0.95
    top_k: int = 50
    repetition_penalty: float = 1.0
    
    def to_dict(self) -> dict:
        """Convert to dict for HF API."""
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
    config: Optional[GenerationConfig] = None,
    device: str = "cuda",
) -> list[list[str]]:
    """Generate n completions per prompt using the model.
    
    Args:
        model: HF transformers model
        tokenizer: Tokenizer
        prompts: List of prompt strings
        n_completions: Number of completions per prompt
        config: GenerationConfig (uses defaults if None)
        device: Device to use ("cuda" or "cpu")
    
    Returns:
        List of lists: [[completion1, completion2, ...], ...]
        Each inner list has n_completions strings for that prompt.
    """
    if config is None:
        config = GenerationConfig()
    
    model = model.to(device)
    model.eval()
    
    all_completions = []
    
    with torch.no_grad():
        for prompt in prompts:
            completions = []
            
            for _ in range(n_completions):
                # Tokenize input
                inputs = tokenizer(
                    prompt,
                    return_tensors="pt",
                    truncation=True,
                    max_length=512,
                ).to(device)
                
                # Generate
                gen_kwargs = config.to_dict()
                gen_kwargs["output_scores"] = False
                
                output_ids = model.generate(
                    **inputs,
                    **gen_kwargs,
                )
                
                # Decode (skip the input tokens)
                completion = tokenizer.decode(
                    output_ids[0][inputs["input_ids"].shape[1]:],
                    skip_special_tokens=True,
                )
                completions.append(completion.strip())
            
            all_completions.append(completions)
    
    return all_completions


def batch_generate(
    model,
    tokenizer,
    prompts: list[str],
    n_completions: int = 4,
    batch_size: int = 8,
    config: Optional[GenerationConfig] = None,
) -> list[list[str]]:
    """Generate completions in batches to save memory.
    
    Args:
        model: HF transformers model
        tokenizer: Tokenizer
        prompts: List of prompts
        n_completions: Completions per prompt
        batch_size: How many prompts to process at once
        config: GenerationConfig
    
    Returns:
        All completions: [[...], [...], ...]
    """
    if config is None:
        config = GenerationConfig()
    
    all_results = []
    
    for i in range(0, len(prompts), batch_size):
        batch = prompts[i : i + batch_size]
        batch_results = generate(
            model=model,
            tokenizer=tokenizer,
            prompts=batch,
            n_completions=n_completions,
            config=config,
        )
        all_results.extend(batch_results)
    
    return all_results
