"""Production entrypoint — platform-safe configuration and migrations."""
from __future__ import annotations

from collections.abc import MutableMapping
import ipaddress
import os
import subprocess
import sys
import time
from urllib.parse import quote_plus, urlsplit


class DatabaseConfigurationError(RuntimeError):
    """Raised when a hosted deployment has no safe MySQL target."""


_HOSTED_ENVIRONMENT_MARKERS = (
    "RAILWAY_PROJECT_ID",
    "RAILWAY_ENVIRONMENT_ID",
    "RAILWAY_SERVICE_ID",
    "RENDER_EXTERNAL_HOSTNAME",
    "RENDER_SERVICE_ID",
)


def is_hosted_environment(env: MutableMapping[str, str] | None = None) -> bool:
    """Return whether this process is running as a hosted deployment."""
    values = os.environ if env is None else env
    app_env = (values.get("APP_ENV") or "").strip().lower()
    if app_env in {"production", "staging"}:
        return True
    return any((values.get(name) or "").strip() for name in _HOSTED_ENVIRONMENT_MARKERS)


def _normalize_mysql_url(url: str) -> str:
    cleaned = url.strip()
    if cleaned.startswith("mysql://"):
        return f"mysql+pymysql://{cleaned[len('mysql://'):]}"
    return cleaned


def _is_loopback_host(host: str) -> bool:
    cleaned = host.strip().rstrip(".").lower()
    if cleaned == "localhost" or cleaned.endswith(".localhost"):
        return True
    try:
        return ipaddress.ip_address(cleaned).is_loopback
    except ValueError:
        return False


def _validate_hosted_database_url(url: str) -> None:
    """Reject unresolved, malformed, or local URLs in hosted environments."""
    if "${{" in url or "}}" in url:
        raise DatabaseConfigurationError(
            "DATABASE_URL contains an unresolved Railway reference. Use Railway's "
            "variable picker and the exact MySQL service name."
        )

    try:
        parsed = urlsplit(url)
        hostname = parsed.hostname
    except ValueError as exc:
        raise DatabaseConfigurationError(
            "DATABASE_URL is malformed. In Railway, set it with the MySQL service's "
            "MYSQL_URL reference."
        ) from exc
    database = parsed.path.lstrip("/").split("/", 1)[0]
    if (
        parsed.scheme not in {"mysql", "mysql+pymysql"}
        or not hostname
        or not parsed.username
        or not database
    ):
        raise DatabaseConfigurationError(
            "DATABASE_URL must be a complete MySQL URL. In Railway, set it to "
            "${{<MYSQL_SERVICE_NAME>.MYSQL_URL}}."
        )
    if _is_loopback_host(hostname):
        raise DatabaseConfigurationError(
            "A hosted deployment cannot use a localhost/loopback MySQL host. "
            "Remove the local DATABASE_URL and reference the Railway MySQL service: "
            "${{<MYSQL_SERVICE_NAME>.MYSQL_URL}}. The application will not fall back "
            "to localhost."
        )


def database_target(url: str) -> str:
    """Return a credential-free database target for startup logs."""
    parsed = urlsplit(url)
    host = parsed.hostname or "unknown-host"
    try:
        port = parsed.port
    except ValueError:
        port = None
    database = parsed.path.lstrip("/").split("/", 1)[0] or "unknown-database"
    return f"{host}:{port or 3306}/{database}"


def configure_database_url(env: MutableMapping[str, str] | None = None) -> str | None:
    """Build ``DATABASE_URL`` from discrete MySQL variables when needed.

    Railway and external providers can continue supplying ``DATABASE_URL``
    directly. ``MYSQL_URL`` and both the underscored and Railway-style
    discrete MySQL variables are also supported. Hosted deployments fail
    closed instead of silently using the application's localhost dev default.
    """
    values = os.environ if env is None else env
    existing = (values.get("DATABASE_URL") or "").strip()
    railway_mysql_url = (values.get("MYSQL_URL") or "").strip()
    supplied_url = existing or railway_mysql_url
    if supplied_url:
        resolved = _normalize_mysql_url(supplied_url)
        if is_hosted_environment(values):
            _validate_hosted_database_url(resolved)
        values["DATABASE_URL"] = resolved
        return resolved

    def first_value(*names: str) -> str:
        for name in names:
            value = (values.get(name) or "").strip()
            if value:
                return value
        return ""

    host = first_value("MYSQL_HOST", "MYSQLHOST")
    user = first_value("MYSQL_USER", "MYSQLUSER")
    database = first_value("MYSQL_DATABASE", "MYSQLDATABASE")
    if not host or not user or not database:
        if is_hosted_environment(values):
            missing: list[str] = []
            if not host:
                missing.append("MYSQLHOST/MYSQL_HOST")
            if not user:
                missing.append("MYSQLUSER/MYSQL_USER")
            if not database:
                missing.append("MYSQLDATABASE/MYSQL_DATABASE")
            raise DatabaseConfigurationError(
                "No Railway MySQL connection is configured for this service. Set "
                "DATABASE_URL=${{<MYSQL_SERVICE_NAME>.MYSQL_URL}} (recommended), or "
                "reference all discrete MySQL variables. Missing: "
                + ", ".join(missing)
                + ". The application will not fall back to localhost."
            )
        return None

    port = first_value("MYSQL_PORT", "MYSQLPORT") or "3306"
    password = first_value("MYSQL_PASSWORD", "MYSQLPASSWORD")
    url = (
        "mysql+pymysql://"
        f"{quote_plus(user, safe='')}:{quote_plus(password, safe='')}@"
        f"{host}:{port}/{quote_plus(database, safe='')}"
        "?charset=utf8mb4"
    )
    values["DATABASE_URL"] = url
    if is_hosted_environment(values):
        _validate_hosted_database_url(url)
    return url


def configure_public_url(env: MutableMapping[str, str] | None = None) -> str | None:
    """Use the hosting platform's public hostname when no URL is set."""
    values = os.environ if env is None else env
    existing = (values.get("BACKEND_PUBLIC_URL") or "").strip().rstrip("/")
    if existing:
        values["BACKEND_PUBLIC_URL"] = existing
        return existing

    hostname = (
        values.get("RAILWAY_PUBLIC_DOMAIN")
        or values.get("RENDER_EXTERNAL_HOSTNAME")
        or ""
    ).strip().strip("/")
    if not hostname:
        return None
    if hostname.startswith(("http://", "https://")):
        public_url = hostname.rstrip("/")
    else:
        public_url = f"https://{hostname}"
    values["BACKEND_PUBLIC_URL"] = public_url
    return public_url


def run_migrations() -> bool:
    """Run Alembic, optionally retrying while a new database starts."""
    try:
        max_attempts = max(1, int(os.environ.get("MIGRATION_MAX_ATTEMPTS", "1")))
    except ValueError:
        max_attempts = 1
    try:
        retry_seconds = max(0.0, float(os.environ.get("MIGRATION_RETRY_SECONDS", "5")))
    except ValueError:
        retry_seconds = 5.0

    for attempt in range(1, max_attempts + 1):
        rc = subprocess.call([sys.executable, "-m", "alembic", "upgrade", "head"])
        if rc == 0:
            print("Migrations complete.")
            return True
        if attempt < max_attempts:
            print(
                f"Migration attempt {attempt}/{max_attempts} failed; "
                f"retrying in {retry_seconds:g}s..."
            )
            time.sleep(retry_seconds)

    print("WARNING: alembic upgrade failed — check DATABASE_URL.")
    return False


def listen_port(env: MutableMapping[str, str] | None = None) -> int:
    values = os.environ if env is None else env
    raw = (values.get("PORT") or "8000").strip()
    if raw in ("", "$PORT"):
        return 8000
    try:
        return int(raw)
    except ValueError:
        return 8000


def main() -> None:
    try:
        configured_database_url = configure_database_url()
    except DatabaseConfigurationError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        raise SystemExit(78) from exc

    if configured_database_url:
        print(f"Database target: {database_target(configured_database_url)}")
    configure_public_url()
    print("Running database migrations...")
    migrated = run_migrations()
    require_migrations_value = os.environ.get("REQUIRE_MIGRATIONS")
    if require_migrations_value is None:
        require_migrations = is_hosted_environment()
    else:
        require_migrations = require_migrations_value.strip().lower() in {"1", "true", "yes"}
    if not migrated and require_migrations:
        raise SystemExit("Database migrations are required but did not complete.")

    port = listen_port()
    print(f"Starting uvicorn on port {port}...")
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
