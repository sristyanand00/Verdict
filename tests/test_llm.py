import pytest

from verdict.engine import llm
from verdict.engine.llm import FixedWriter, GeminiWriter, LLMError


class FakeGemini(GeminiWriter):
    """GeminiWriter with the network call replaced, so no key or SDK is needed."""

    def __init__(self, outcomes, cache_dir=None):
        self.model, self.temperature, self.max_parallel = "fake", 0.8, 8
        self.cache_dir = cache_dir
        self.outcomes = outcomes  # list of (reply, error)

    def _one(self, prompt, i):
        return self.outcomes[i]


def test_some_failures_are_tolerated():
    w = FakeGemini([("ok", None)] * 5 + [("", "429")] * 3)
    assert w.write("p", 8) == ["ok"] * 5 + [""] * 3


def test_mostly_failed_calls_raise_instead_of_a_fake_trust_level():
    w = FakeGemini([("ok", None)] * 3 + [("", "429 quota")] * 5)
    with pytest.raises(LLMError, match="5 of 8"):
        w.write("p", 8)


def test_cache_files_differ_per_attempt_and_prompt(tmp_path):
    w = FakeGemini([], cache_dir=tmp_path)
    files = {w._cache_file("a", 0), w._cache_file("a", 1), w._cache_file("b", 0)}
    assert len(files) == 3


def test_retry_waits_are_short_enough_for_a_request():
    assert sum(llm.RETRY_WAITS_S) <= 90


def test_fixed_writer_cycles():
    assert FixedWriter(["a", "b"]).write("p", 3) == ["a", "b", "a"]
