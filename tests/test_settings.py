import pytest

from diffpl import __version__
from diffpl.settings import get_settings


def test_version() -> None:
    assert __version__ == "0.1.0"


def test_settings_read_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIFFPL_SEED", "7")
    monkeypatch.setenv("DIFFPL_DATABASE_URL", "postgresql+psycopg://u:p@db:5432/x")
    settings = get_settings()
    assert settings.seed == 7
    assert settings.database_url.endswith("@db:5432/x")
