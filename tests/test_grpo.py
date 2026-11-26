"""End-to-end GRPO trainer test on a tiny random model (CPU, no download).

Skipped when torch/transformers are not installed (CI installs neither).
"""

import json

import pytest

torch = pytest.importorskip("torch")
transformers = pytest.importorskip("transformers")
tokenizers = pytest.importorskip("tokenizers")

from tests.fixtures import make_tiny_db  # noqa: E402
from verdict.data.loaders import BirdTask  # noqa: E402
from verdict.train import grpo as grpo_mod  # noqa: E402
from verdict.train.grpo import GRPOTrainer, GRPOTrainingConfig  # noqa: E402


def _tiny_tokenizer():
    from tokenizers import Tokenizer, decoders, models, pre_tokenizers, trainers

    tok = Tokenizer(models.BPE())
    tok.pre_tokenizer = pre_tokenizers.ByteLevel(add_prefix_space=False)
    tok.decoder = decoders.ByteLevel()
    trainer = trainers.BpeTrainer(
        vocab_size=400, special_tokens=["<pad>", "<eos>"],
        initial_alphabet=pre_tokenizers.ByteLevel.alphabet(),
    )
    tok.train_from_iterator(["SELECT name FROM students WHERE year = 2", "Question Schema Hint"], trainer)
    return transformers.PreTrainedTokenizerFast(tokenizer_object=tok, pad_token="<pad>", eos_token="<eos>")


def _tiny_model(vocab_size, eos_id, pad_id):
    cfg = transformers.Qwen2Config(
        vocab_size=vocab_size, hidden_size=32, intermediate_size=64, num_hidden_layers=2,
        num_attention_heads=4, num_key_value_heads=2, max_position_embeddings=4096,
        eos_token_id=eos_id, pad_token_id=pad_id, tie_word_embeddings=True,
    )
    torch.manual_seed(0)
    return transformers.Qwen2ForCausalLM(cfg)


@pytest.fixture
def make_trainer(tmp_path, monkeypatch):
    """Build a trainer on a tiny random model; keyword arguments override the config."""
    make_tiny_db(tmp_path / "dbs")
    tok = _tiny_tokenizer()
    monkeypatch.setattr(GRPOTrainer, "_load_tokenizer", staticmethod(lambda source: tok))
    # Every from_pretrained gets the same fresh-per-test tiny model, so the
    # real post-load steps (dtype, device, LoRA, checkpointing) run on it.
    model = _tiny_model(len(tok), tok.eos_token_id, tok.pad_token_id)
    monkeypatch.setattr(grpo_mod.AutoModelForCausalLM, "from_pretrained", lambda s: model)

    def build(**overrides):
        cfg = GRPOTrainingConfig(**{
            "model_name": "tiny", "num_epochs": 1, "batch_size": 2, "num_generations": 3,
            "max_tokens": 8, "micro_batch_size": 2, "learning_rate": 1e-2, "eval_max_tasks": 2,
            "checkpoint_dir": tmp_path / "ckpt", "device": "cpu", "reward_workers": 2,
            **overrides,
        })
        return GRPOTrainer(cfg, db_root=tmp_path / "dbs")

    return build


@pytest.fixture
def trainer(make_trainer):
    return make_trainer()


def _task(qid):
    return BirdTask(
        question_id=qid, db_id="tiny", question="Names of year 2 students?", evidence="year = 2",
        gold_sql="SELECT name FROM students WHERE year = 2", difficulty="simple", db_path=None,
    )


def test_prompt_contains_schema_question_and_hint(trainer):
    text = trainer.prompt_for(_task(1))
    assert "CREATE TABLE students" in text
    assert "Names of year 2 students?" in text
    assert "year = 2" in text


def test_db_root_must_be_the_databases_folder(tmp_path):
    with pytest.raises(FileNotFoundError, match="dev_databases"):
        GRPOTrainer(GRPOTrainingConfig(device="cpu"), db_root=tmp_path / "missing")


def test_logprobs_match_a_plain_forward_pass(trainer):
    """The hidden-state shortcut must give the same log-probs as full logits."""
    p, c = [5, 6, 7, 8], [9, 10, 11]
    got = trainer._sequence_logprobs([(p, c, 1.0), ([5, 6], [7], 1.0)])
    with torch.no_grad():
        logits = trainer.model(torch.tensor([p + c])).logits[0]
    expected = torch.log_softmax(logits.float(), -1)[torch.arange(3, 6), torch.tensor(c)].sum()
    assert got[0].item() == pytest.approx(expected.item(), rel=1e-4)


def test_update_makes_rewarded_completion_more_likely(trainer):
    """Sign check: positive advantage must raise log p, negative must lower it."""
    p, good, bad = [5, 6, 7], [8, 9, 10], [11, 12, 13]
    with torch.no_grad():
        before = trainer._sequence_logprobs([(p, good, 0), (p, bad, 0)])
    for _ in range(3):
        trainer._accumulate_gradients([(p, good, 1.0), (p, bad, -1.0)])
        trainer._optimizer_step()
    with torch.no_grad():
        after = trainer._sequence_logprobs([(p, good, 0), (p, bad, 0)])
    assert after[0] > before[0]
    assert after[1] < before[1]


class _SpreadReward:
    """A random tiny model never writes valid SQL, so every reward would be 0
    and there would be no gradient. This gives one 'correct' per group of 3."""

    rewards = {"correct": 1.0, "wrong": 0.1, "failed": 0.0}

    def __call__(self, prompts, completions, **kwargs):
        return [1.0 if i % 3 == 0 else 0.0 for i in range(len(completions))]


def test_fit_updates_weights_and_saves_checkpoints(trainer):
    trainer.reward_fn = _SpreadReward()
    before = [p.detach().clone() for p in trainer.model.parameters()]
    result = trainer.fit([_task(1), _task(2), _task(3)], val_tasks=[_task(4)])
    after = list(trainer.model.parameters())

    assert any(not torch.equal(a, b) for a, b in zip(before, after)), "no weights changed"
    assert all(torch.isfinite(p).all() for p in after)
    assert trainer.global_step >= 1
    assert len(result["metrics"]["val_accuracy"]) == 1
    latest = trainer.checkpoint_dir / "latest"
    assert (latest / "config.json").exists()
    assert json.loads((latest / "training_state.json").read_text())["epoch"] == 1
    assert (trainer.checkpoint_dir / "best").is_dir()


def test_out_of_memory_chunk_is_retried_one_at_a_time_then_skipped(trainer, monkeypatch):
    real = trainer._sequence_logprobs
    sizes = []

    def flaky(chunk):
        sizes.append(len(chunk))
        if len(chunk) > 1 or chunk[0][1] == [11]:
            raise torch.OutOfMemoryError("no memory")
        return real(chunk)

    monkeypatch.setattr(trainer, "_sequence_logprobs", flaky)
    trainer._accumulate_gradients([([5, 6], [7], 1.0), ([5, 6], [11], -1.0)])
    assert sizes == [2, 1, 1]
    assert trainer.skipped_answers == 1
    assert trainer._has_grads


def test_save_every_writes_latest_during_the_epoch(make_trainer, monkeypatch):
    trainer = make_trainer(batch_size=1, save_every=2, eval_before_training=False)
    trainer.reward_fn = _SpreadReward()
    saved = []
    monkeypatch.setattr(trainer, "_save_checkpoint", lambda name, epoch: saved.append(name))
    trainer.fit([_task(1), _task(2), _task(3)])
    assert saved == ["latest", "latest"]  # after batch 2, and at the end of the epoch


def test_tasks_without_a_database_are_skipped(trainer):
    other = BirdTask(
        question_id=9, db_id="not_here", question="q", evidence="", gold_sql="SELECT 1",
        difficulty="unknown", db_path=None,
    )
    assert [t.question_id for t in trainer._usable([_task(1), other])] == [1]


# ----------------------------------------------------------------------- LoRA


def test_lora_trains_only_the_adapter(make_trainer):
    pytest.importorskip("peft")
    trainer = make_trainer(lora_r=4, lora_alpha=8, lora_dropout=0.0)
    trainer.reward_fn = _SpreadReward()
    named = dict(trainer.model.named_parameters())
    frozen = {n: p.detach().clone() for n, p in named.items() if not p.requires_grad}
    trained = {n: p.detach().clone() for n, p in named.items() if p.requires_grad}
    assert trained and all("lora_" in n for n in trained)
    assert all(p.dtype == torch.float32 for n, p in named.items() if p.requires_grad)

    trainer.fit([_task(1), _task(2), _task(3)], val_tasks=[_task(4)])

    after = dict(trainer.model.named_parameters())
    assert all(torch.equal(after[n], p) for n, p in frozen.items()), "a frozen weight changed"
    assert any(not torch.equal(after[n], p) for n, p in trained.items()), "no adapter weight changed"
    latest = trainer.checkpoint_dir / "latest"
    assert (latest / "adapter_config.json").exists()
    assert not (latest / "model.safetensors").exists(), "LoRA checkpoint should hold only the adapter"


def test_lora_logprobs_match_a_plain_forward_pass(make_trainer):
    pytest.importorskip("peft")
    trainer = make_trainer(lora_r=4, lora_dropout=0.0)
    p, c = [5, 6, 7, 8], [9, 10, 11]
    got = trainer._sequence_logprobs([(p, c, 1.0)])
    with torch.no_grad():
        logits = trainer.model(input_ids=torch.tensor([p + c])).logits[0]
    expected = torch.log_softmax(logits.float(), -1)[torch.arange(3, 6), torch.tensor(c)].sum()
    assert got[0].item() == pytest.approx(expected.item(), rel=1e-4)


def test_adapter_checkpoint_loads_for_inference(make_trainer, monkeypatch):
    pytest.importorskip("peft")
    from verdict.train import modeling

    trainer = make_trainer(lora_r=4, lora_dropout=0.0)
    trainer.reward_fn = _SpreadReward()
    trainer.fit([_task(1), _task(2)], val_tasks=[])
    tok = trainer.tokenizer
    # A fresh copy of the same base weights, as from_pretrained would give.
    monkeypatch.setattr(modeling.AutoModelForCausalLM, "from_pretrained",
                        lambda s: _tiny_model(len(tok), tok.eos_token_id, tok.pad_token_id))
    monkeypatch.setattr(modeling, "load_tokenizer", lambda s: tok)

    merged, _ = modeling.load_for_inference(trainer.checkpoint_dir / "latest", device="cpu")

    ids = torch.tensor([[5, 6, 7, 8, 9]])
    trainer.model.eval()
    with torch.no_grad():
        expected = trainer.model(input_ids=ids).logits
        got = merged(input_ids=ids).logits
    assert torch.allclose(got, expected, atol=1e-4)
