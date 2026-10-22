from run_server import configure_database_url, configure_public_url, listen_port


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


def test_configure_database_url_waits_for_complete_mysql_settings() -> None:
    env = {"MYSQL_HOST": "fleetops-mysql"}

    assert configure_database_url(env) is None
    assert "DATABASE_URL" not in env


def test_configure_public_url_uses_render_hostname() -> None:
    env = {"RENDER_EXTERNAL_HOSTNAME": "fleetops-api-abc.onrender.com"}

    assert configure_public_url(env) == "https://fleetops-api-abc.onrender.com"
    assert env["BACKEND_PUBLIC_URL"] == "https://fleetops-api-abc.onrender.com"


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
