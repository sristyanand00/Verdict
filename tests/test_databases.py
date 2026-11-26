"""The databases offered to analysts come from VERDICT_DATABASES."""

from verdict.api.state import DEFAULT_DATABASES, KNOWN_DATABASES, preloaded_databases


def test_default_is_olist_plus_four_hard_databases(monkeypatch):
    monkeypatch.delenv("VERDICT_DATABASES", raising=False)
    ids = [d.id for d in preloaded_databases()]
    assert ids == DEFAULT_DATABASES.split(",")
    assert ids == ["olist", "financial", "formula_1", "european_football_2", "card_games"]
    assert all(d.description for d in preloaded_databases())


def test_setting_picks_databases_and_skips_unknown_ids(monkeypatch):
    monkeypatch.setenv("VERDICT_DATABASES", " superhero, nope ,financial,superhero")
    dbs = preloaded_databases()
    assert [d.id for d in dbs] == ["superhero", "financial"]
    assert dbs[0].name == KNOWN_DATABASES["superhero"][0] and dbs[0].source == "preloaded"


def test_olist_path_setting(monkeypatch, tmp_path):
    monkeypatch.setenv("VERDICT_DATABASES", "olist")
    monkeypatch.setenv("VERDICT_OLIST_PATH", str(tmp_path / "o.sqlite"))
    assert preloaded_databases()[0].path == tmp_path / "o.sqlite"
