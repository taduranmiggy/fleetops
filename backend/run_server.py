"""Production entrypoint — platform-safe configuration and migrations."""
from __future__ import annotations

from collections.abc import MutableMapping
import os
import subprocess
import sys
import time
from urllib.parse import quote_plus


def configure_database_url(env: MutableMapping[str, str] | None = None) -> str | None:
    """Build ``DATABASE_URL`` from discrete MySQL variables when needed.

    Railway and external providers can continue supplying ``DATABASE_URL``
    directly. Render's Blueprint supplies the private MySQL hostname and a
    shared generated password as separate variables, so the process composes
    the SQLAlchemy URL before Alembic or the application imports settings.
    """
    values = os.environ if env is None else env
    existing = (values.get("DATABASE_URL") or "").strip()
    if existing:
        return existing

    host = (values.get("MYSQL_HOST") or "").strip()
    user = (values.get("MYSQL_USER") or "").strip()
    database = (values.get("MYSQL_DATABASE") or "").strip()
    if not host or not user or not database:
        return None

    port = (values.get("MYSQL_PORT") or "3306").strip() or "3306"
    password = values.get("MYSQL_PASSWORD") or ""
    url = (
        "mysql+pymysql://"
        f"{quote_plus(user, safe='')}:{quote_plus(password, safe='')}@"
        f"{host}:{port}/{quote_plus(database, safe='')}"
        "?charset=utf8mb4"
    )
    values["DATABASE_URL"] = url
    return url


def configure_public_url(env: MutableMapping[str, str] | None = None) -> str | None:
    """Use Render's assigned public hostname when no explicit URL is set."""
    values = os.environ if env is None else env
    existing = (values.get("BACKEND_PUBLIC_URL") or "").strip().rstrip("/")
    if existing:
        values["BACKEND_PUBLIC_URL"] = existing
        return existing

    hostname = (values.get("RENDER_EXTERNAL_HOSTNAME") or "").strip().strip("/")
    if not hostname:
        return None
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
    configure_database_url()
    configure_public_url()
    print("Running database migrations...")
    migrated = run_migrations()
    require_migrations = (os.environ.get("REQUIRE_MIGRATIONS") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    if not migrated and require_migrations:
        raise SystemExit("Database migrations are required but did not complete.")

    port = listen_port()
    print(f"Starting uvicorn on port {port}...")
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
