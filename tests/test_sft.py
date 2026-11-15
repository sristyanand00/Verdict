"""SFT trainer tests on a tiny random model (CPU, no download).

Skipped when torch, transformers or peft are not installed.
"""

import json

import pytest

torch = pytest.importorskip("torch")
pytest.importorskip("transformers")
pytest.importorskip("peft")

from tests.fixtures import make_tiny_db  # noqa: E402
from tests.test_grpo import _tiny_model, _tiny_tokenizer  # noqa: E402
from verdict.data.loaders import BirdTask  # noqa: E402
from verdict.train import modeling  # noqa: E402
from verdict.train.sft import SFTConfig, SFTTrainer  # noqa: E402


def _task(qid, db_id="tiny"):
    return BirdTask(
        question_id=qid, db_id=db_id, question="Names of year 2 students?", evidence="year = 2",
        gold_sql="SELECT name FROM students WHERE year = 2", difficulty="unknown", db_path=None,
    )


@pytest.fixture
def make_trainer(tmp_path, monkeypatch):
    make_tiny_db(tmp_path / "dbs")
    tok = _tiny_tokenizer()
    monkeypatch.setattr(SFTTrainer, "_load_tokenizer", staticmethod(lambda source: tok))
    # A fresh copy of the same base weights for every load, like from_pretrained.
    monkeypatch.setattr(modeling.AutoModelForCausalLM, "from_pretrained",
                        lambda s: _tiny_model(len(tok), tok.eos_token_id, tok.pad_token_id))

    def build(init_from=None, schemas_file=None, **overrides):
        cfg = SFTConfig(**{
            "model_name": "tiny", "batch_size": 2, "micro_batch_size": 1, "learning_rate": 1e-2,
            "warmup_steps": 1, "lora_r": 4, "lora_alpha": 8, "lora_dropout": 0.0,
            "max_answer_tokens": 64, "eval_max_tasks": 2, "log_every_steps": 1,
            "save_every_steps": 1000, "checkpoint_dir": tmp_path / "ckpt", "device": "cpu",
            "reward_workers": 2, **overrides,
        })
        return SFTTrainer(cfg, db_root=tmp_path / "dbs", schemas_file=schemas_file, init_from=init_from)

    return build


def test_answer_is_the_fenced_gold_sql_and_ends_with_eos(make_trainer):
    trainer = make_trainer()
    prompt, answer = trainer.encode(_task(1))
    assert answer[-1] == trainer.tokenizer.eos_token_id
    text = trainer.tokenizer.decode(answer[:-1])
    assert text == "```sql\nSELECT name FROM students WHERE year = 2\n```"
    assert trainer.tokenizer.decode(prompt) == trainer.prompt_for(_task(1))


def test_training_makes_the_gold_answer_more_likely(make_trainer):
    trainer = make_trainer()
    ex = [(1, *trainer.encode(_task(1)))]

    def answer_logp():
        with torch.no_grad():
            logp, _ = modeling.completion_token_logprobs(
                trainer.model, [(ex[0][1], ex[0][2])], trainer.tokenizer.pad_token_id,
                trainer.device, trainer._autocast(),
            )
        return logp.sum().item()

    before = answer_logp()
    for _ in range(5):
        trainer.train_step(ex)
    assert answer_logp() > before


def test_fit_saves_adapter_checkpoints(make_trainer):
    trainer = make_trainer(num_epochs=1)
    result = trainer.fit([_task(i) for i in range(1, 5)], val_tasks=[_task(9)])
    assert result["finished"]
    assert result["global_step"] == result["total_steps"] == 2
    latest = trainer.checkpoint_dir / "latest"
    assert (latest / "adapter_config.json").exists()
    assert (latest / "trainer_state.pt").exists()
    assert json.loads((latest / "sft_state.json").read_text())["global_step"] == 2
    assert (trainer.checkpoint_dir / "best").is_dir()
    assert result["val_accuracy_before"] is not None


def test_time_limit_stops_and_resume_finishes_the_run(make_trainer):
    tasks = [_task(i) for i in range(1, 9)]  # 4 steps of 2
    first = make_trainer(time_limit_hours=1e-12, eval_before_training=False)
    r1 = first.fit(tasks)
    assert not r1["finished"]
    assert r1["global_step"] == 1

    latest = first.checkpoint_dir / "latest"
    second = make_trainer(init_from=latest, eval_before_training=False)
    r2 = second.fit(tasks, resume_from=latest)
    assert r2["finished"]
    assert r2["global_step"] == 4
    # The learning-rate schedule continued rather than restarting the warm-up.
    assert second.scheduler.last_epoch == 4


def test_schema_comes_from_the_saved_file_when_the_database_is_missing(make_trainer, tmp_path):
    schemas = tmp_path / "schemas.json"
    schemas.write_text(json.dumps({"big": {
        "with_rows": "CREATE TABLE big_table (x INTEGER);\n-- Sample rows:\n-- (1,)",
        "no_rows": "CREATE TABLE big_table (x INTEGER);",
    }}))
    trainer = make_trainer(schemas_file=schemas)
    assert "big_table" in trainer.prompt_for(_task(1, db_id="big"))
    examples = trainer._examples([_task(1, db_id="big"), _task(2, db_id="nowhere")])
    assert [qid for qid, _, _ in examples] == [1]
