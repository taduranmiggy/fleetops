import pytest
from pydantic import ValidationError

from app.core.config import Settings


def production_settings(**overrides) -> Settings:
    values = {
        "app_env": "production",
        "secret_key": "s" * 32,
        "database_url": "mysql+pymysql://fleetops:secret@mysql.railway.internal:3306/fleetopt",
        "frontend_url": "https://fleetops.netlify.app",
        "cors_origins": "https://fleetops.netlify.app",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


@pytest.mark.parametrize(
    "url",
    [
        "mysql+pymysql://root:@localhost:3306/fleetopt",
        "mysql+pymysql://root:@127.0.0.1:3306/fleetopt",
        "mysql+pymysql://root:@[::1]:3306/fleetopt",
    ],
)
def test_production_settings_reject_loopback_database(url: str) -> None:
    with pytest.raises(ValidationError, match="must not target localhost"):
        production_settings(database_url=url)


def test_production_settings_accept_railway_database() -> None:
    settings = production_settings()

    assert settings.database_url == (
        "mysql+pymysql://fleetops:secret@mysql.railway.internal:3306/fleetopt"
    )


def test_railway_marker_cannot_be_weakened_by_development_app_env(monkeypatch) -> None:
    monkeypatch.setenv("RAILWAY_PROJECT_ID", "project-id")

    with pytest.raises(ValidationError, match="must not target localhost"):
        Settings(
            _env_file=None,
            app_env="development",
            secret_key="s" * 32,
            frontend_url="https://fleetops.netlify.app",
            cors_origins="https://fleetops.netlify.app",
        )
