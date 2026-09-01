"""Release resources must exist independently of an editable checkout."""

from importlib.resources import files

from fza.factors.registry import load_all
from fza.store import Store


def test_runtime_resources_are_packaged_and_readable():
    assert files("fza").joinpath("sql", "001_schema.sql").is_file()
    cards = files("fza.factors").joinpath("cards")
    assert len(list(cards.iterdir())) == 10
    assert len(load_all()) == 10
    with Store(":memory:") as store:
        assert store.fundamentals_asof("2020-01-01").empty
