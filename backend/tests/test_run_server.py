import pytest

from run_server import (
    DatabaseConfigurationError,
    configure_database_url,
    configure_public_url,
    database_target,
    listen_port,
)


def test_configure_database_url_preserves_explicit_url() -> None:
    env = {
        "DATABASE_URL": "mysql+pymysql://existing:secret@db:3306/fleetopt",
        "MYSQL_HOST": "ignored",
    }

    result = configure_database_url(env)

    assert result == "mysql+pymysql://existing:secret@db:3306/fleetopt"
    assert env["DATABASE_URL"] == result


def test_configure_database_url_builds_render_private_mysql_url() -> None:
    env = {
        "MYSQL_HOST": "fleetops-mysql",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "fleetopt",
        "MYSQL_USER": "fleetopt",
        "MYSQL_PASSWORD": "p@ss/word",
    }

    result = configure_database_url(env)

    assert result == (
        "mysql+pymysql://fleetopt:p%40ss%2Fword@fleetops-mysql:3306/fleetopt"
        "?charset=utf8mb4"
    )
    assert env["DATABASE_URL"] == result


def test_configure_database_url_builds_railway_mysql_url() -> None:
    env = {
        "MYSQLHOST": "mysql.railway.internal",
        "MYSQLPORT": "3306",
        "MYSQLDATABASE": "fleetopt",
        "MYSQLUSER": "fleetops",
        "MYSQLPASSWORD": "p@ss/word",
    }

    result = configure_database_url(env)

    assert result == (
        "mysql+pymysql://fleetops:p%40ss%2Fword@mysql.railway.internal:3306/fleetopt"
        "?charset=utf8mb4"
    )
    assert env["DATABASE_URL"] == result


def test_configure_database_url_uses_railway_mysql_url() -> None:
    env = {
        "RAILWAY_PROJECT_ID": "project-id",
        "MYSQL_URL": "mysql://fleetops:secret@mysql.railway.internal:3306/fleetopt",
    }

    result = configure_database_url(env)

    assert result == "mysql+pymysql://fleetops:secret@mysql.railway.internal:3306/fleetopt"
    assert env["DATABASE_URL"] == result
    assert database_target(result) == "mysql.railway.internal:3306/fleetopt"


def test_configure_database_url_waits_for_complete_mysql_settings() -> None:
    env = {"MYSQL_HOST": "fleetops-mysql"}

    assert configure_database_url(env) is None
    assert "DATABASE_URL" not in env


def test_configure_database_url_rejects_missing_railway_connection() -> None:
    env = {"RAILWAY_PROJECT_ID": "project-id"}

    with pytest.raises(DatabaseConfigurationError, match="will not fall back to localhost"):
        configure_database_url(env)


@pytest.mark.parametrize(
    "url",
    [
        "mysql+pymysql://root:@localhost:3306/fleetopt",
        "mysql+pymysql://root:@127.0.0.1:3306/fleetopt",
        "mysql+pymysql://root:@[::1]:3306/fleetopt",
    ],
)
def test_configure_database_url_rejects_loopback_in_production(url: str) -> None:
    env = {"APP_ENV": "production", "DATABASE_URL": url}

    with pytest.raises(DatabaseConfigurationError, match="cannot use a localhost/loopback"):
        configure_database_url(env)


def test_configure_public_url_uses_render_hostname() -> None:
    env = {"RENDER_EXTERNAL_HOSTNAME": "fleetops-api-abc.onrender.com"}

    assert configure_public_url(env) == "https://fleetops-api-abc.onrender.com"
    assert env["BACKEND_PUBLIC_URL"] == "https://fleetops-api-abc.onrender.com"


def test_configure_public_url_uses_railway_hostname() -> None:
    env = {"RAILWAY_PUBLIC_DOMAIN": "fleetops-production.up.railway.app"}

    assert configure_public_url(env) == "https://fleetops-production.up.railway.app"
    assert env["BACKEND_PUBLIC_URL"] == "https://fleetops-production.up.railway.app"


def test_configure_public_url_preserves_explicit_origin() -> None:
    env = {
        "BACKEND_PUBLIC_URL": "https://api.example.com/",
        "RENDER_EXTERNAL_HOSTNAME": "ignored.onrender.com",
    }

    assert configure_public_url(env) == "https://api.example.com"
    assert env["BACKEND_PUBLIC_URL"] == "https://api.example.com"


def test_listen_port_uses_render_port() -> None:
    assert listen_port({"PORT": "10000"}) == 10000


def test_listen_port_ignores_unexpanded_placeholder() -> None:
    assert listen_port({"PORT": "$PORT"}) == 8000
    assert listen_port({"PORT": ""}) == 8000
    assert listen_port({"PORT": "not-a-port"}) == 8000
