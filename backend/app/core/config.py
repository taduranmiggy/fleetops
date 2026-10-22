from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def normalize_mysql_url(url: str) -> str:
    """Ensure SQLAlchemy can use PyMySQL."""
    cleaned = url.strip()
    if cleaned.startswith("mysql+pymysql://"):
        return cleaned
    if cleaned.startswith("mysql://"):
        return f"mysql+pymysql://{cleaned[len('mysql://'):]}"
    return cleaned


class Settings(BaseSettings):
    # Application
    app_name: str = "FleetOpt API"
    app_env: str = Field(default="development", description="Environment: development, staging, production")

    # JWT secret — must be 32+ chars in production
    secret_key: str = Field(
        default="dev-key-change-in-production",
        description="JWT secret key — must be 32+ chars in production",
    )
    access_token_expire_minutes: int = 60 * 24  # 24 h

    # ----------------------------------------------------------------
    # MySQL / XAMPP database  (NO SQLite support)
    # XAMPP default: root user, empty password, port 3306
    # ----------------------------------------------------------------
    database_url: str = Field(
        default="mysql+pymysql://root:@localhost:3306/fleetopt",
        description=(
            "MySQL connection string.\n"
            "XAMPP default: mysql+pymysql://root:@localhost:3306/fleetopt\n"
            "With password:  mysql+pymysql://root:yourpassword@localhost:3306/fleetopt"
        ),
    )

    # Frontend URL for CORS
    frontend_url: str = Field(
        default="http://localhost:3000",
        description="Frontend URL for CORS",
    )
    cors_origins: str | None = Field(
        default=None,
        description="Comma-separated allowlist of CORS origins for production.",
    )

    # Upload storage root (relative paths resolve from backend/ directory)
    uploads_root: str = Field(
        default="uploads",
        description="Base directory for uploaded files.",
    )

    # Clerk authentication (optional)
    use_clerk_auth: bool = False
    clerk_api_key: str | None = None
    clerk_frontend_api: str | None = None
    clerk_webhook_secret: str | None = None

    # Email notifications (optional)
    resend_api_key: str | None = None
    email_from: str = "FleetOpt <notifications@fleetopt.com>"
    # Inbox for customer feedback (e.g. FleetOps Gmail). Uses Resend when RESEND_API_KEY is set.
    feedback_inbox_email: str | None = Field(default=None, description="Recipient for customer feedback emails")
    password_reset_token_expire_minutes: int = 30

    # SMS notifications (optional)
    twilio_account_sid: str | None = None
    twilio_auth_token: str | None = None
    twilio_from_number: str | None = None

    # Geocoding — Google (paid API key) optional; if unset, OSM Nominatim is used (no API key; rate-limited).
    google_maps_geocoding_api_key: str | None = Field(
        default=None,
        description=(
            "Google Geocoding API key for backend pin resolution. Enable Geocoding API; for uvicorn calls avoid HTTP-referrer-only "
            "restriction (use IP / none in dev) or backend requests will fail and Nominatim is used."
        ),
    )
    geocoding_user_agent: str = Field(
        default="FleetOpt/1.0 (+http://localhost:3000)",
        description="HTTP User-Agent sent to Nominatim (must identify your app; include contact URL or email).",
    )

    # Road km — Google Directions (closest to Google Maps driving distance) when key available.
    google_maps_directions_api_key: str | None = Field(
        default=None,
        description=(
            "Optional dedicated Google Directions API key. If empty and GOOGLE_DIRECTIONS_FALLBACK_TO_GEOCODING_KEY=true, "
            "reuses GOOGLE_MAPS_GEOCODING_API_KEY (enable Directions API on that key)."
        ),
    )
    google_directions_fallback_to_geocoding_key: bool = Field(
        default=True,
        description="If no dedicated directions key, use GOOGLE_MAPS_GEOCODING_API_KEY for Directions API calls.",
    )
    use_google_directions_for_routing: bool = Field(
        default=True,
        description="When a directions-capable key is available, call Google Directions before ORS/OSRM for road km.",
    )

    # Driving distance (road km) after geocoding — OSRM / OpenRouteService (OpenStreetMap-based).
    openrouteservice_api_key: str | None = Field(
        default=None,
        description="Optional OpenRouteService API key (free tier). Tried before OSRM when set.",
    )
    use_truck_route_profile: bool = Field(
        default=True,
        description=(
            "If true, OpenRouteService uses driving-hgv (heavy goods / truck-friendly restrictions). "
            "If false, uses driving-car. Public OSRM demo has no HGV profile — see OSRM_ROUTE_PROFILE."
        ),
    )
    osrm_route_base_url: str = Field(
        default="https://router.project-osrm.org",
        description="OSRM route endpoint base (no trailing path). Public demo or self-hosted.",
    )
    osrm_route_profile: str = Field(
        default="driving",
        description=(
            "OSRM profile segment in /route/v1/{profile}/… Default 'driving' matches public demo (car-oriented). "
            "Self-hosted OSRM with a truck/HGV profile: set to that profile name."
        ),
    )
    use_osrm_driving_distance: bool = Field(
        default=True,
        description="If true, request OSRM driving distance when ORS key is unset or fails.",
    )
    require_routed_distance: bool = Field(
        default=True,
        description="If true, refuse heuristics / straight-line km — only Google Directions / OSRM / ORS road km (or same-location zero).",
    )

    # Booking freight knobs persisted in DB — admin UI only edits these two (.env seeds first row).
    diesel_price_php_per_liter: float = Field(
        default=74.75,
        ge=1.0,
        le=500.0,
        description="Retail diesel ₱/L for the fuel deduction (road km / 4 × ₱/L in the business formula).",
    )
    toll_fees_php_per_trip: float = Field(
        default=0.0,
        ge=0.0,
        le=500_000.0,
        description="Toll deduction ₱ per booking leg (admin Calculations tab).",
    )
    fuel_price_source_url: str | None = Field(
        default=None,
        description="Optional trusted URL returning JSON diesel price (or HTML with Diesel common price).",
    )
    fuel_price_cache_ttl_hours: float = Field(
        default=24.0,
        ge=1.0,
        le=168.0,
        description="Hours before cached diesel price is refreshed from FUEL_PRICE_SOURCE_URL.",
    )
    fuel_price_fetch_timeout_sec: float = Field(
        default=8.0,
        ge=1.0,
        le=60.0,
        description="HTTP timeout for fuel price source fetch.",
    )

    # Xendit payments (GCash QR)
    xendit_secret_key: str | None = Field(default=None, description="Xendit secret API key")
    xendit_public_key: str | None = Field(default=None, description="Xendit public API key (optional, for client-side)")
    xendit_webhook_token: str | None = Field(
        default=None,
        description="Xendit callback verification token (x-callback-token header).",
    )
    xendit_webhook_base_url: str | None = Field(
        default=None,
        description="Public HTTPS base URL for Xendit webhooks, e.g. https://api.example.com",
    )
    backend_public_url: str | None = Field(
        default="http://127.0.0.1:8000",
        description="Public backend URL used to build webhook callbacks when XENDIT_WEBHOOK_BASE_URL is unset.",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    @field_validator("database_url")
    @classmethod
    def must_be_mysql(cls, v: str) -> str:
        if not v:
            raise ValueError("DATABASE_URL must be set")
        normalized = normalize_mysql_url(v)
        if normalized.startswith("sqlite"):
            raise ValueError(
                "SQLite is not supported. Use MySQL.\n"
                "Set DATABASE_URL=mysql+pymysql://user:pass@host:3306/fleetopt"
            )
        if normalized.startswith("postgres"):
            raise ValueError(
                "PostgreSQL is not supported by this schema. "
                "Use a MySQL DATABASE_URL."
            )
        return normalized

    @field_validator("secret_key")
    @classmethod
    def validate_secret_key(cls, v: str, info) -> str:
        env = info.data.get("app_env", "development")
        if env == "production":
            if len(v) < 32:
                raise ValueError(
                    "SECRET_KEY must be at least 32 characters in production. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )
            if v == "dev-key-change-in-production":
                raise ValueError("Set a strong SECRET_KEY in .env for production.")
        return v

    @model_validator(mode="after")
    def validate_production_requirements(self):
        env = (self.app_env or "").strip().lower()
        if env != "production":
            return self

        missing: list[str] = []
        if not self.secret_key:
            missing.append("SECRET_KEY")
        if not self.database_url:
            missing.append("DATABASE_URL")
        if not self.frontend_url:
            missing.append("FRONTEND_URL")
        if missing:
            raise ValueError("Missing required production environment values: " + ", ".join(missing))

        if self.secret_key == "dev-key-change-in-production":
            raise ValueError("SECRET_KEY must not use the development default in production.")
        lowered = [o.lower() for o in self.allowed_cors_origins]
        if any("localhost" in o or "127.0.0.1" in o for o in lowered):
            raise ValueError(
                "Production CORS origins must not include localhost/127.0.0.1. "
                "Set FRONTEND_URL and/or CORS_ORIGINS to your approved domains."
            )
        return self

    @property
    def xendit_enabled(self) -> bool:
        return bool((self.xendit_secret_key or "").strip())

    @property
    def resolved_uploads_root(self) -> Path:
        configured = Path(self.uploads_root).expanduser()
        if configured.is_absolute():
            return configured
        backend_root = Path(__file__).resolve().parents[2]
        return (backend_root / configured).resolve()

    @property
    def allowed_cors_origins(self) -> list[str]:
        env = (self.app_env or "").strip().lower()
        local_dev = {"http://localhost:3000", "http://127.0.0.1:3000"}
        # The production frontend is hosted on Netlify. Keep this narrow
        # fallback so browser access remains available if a manually created
        # Render service is missing FRONTEND_URL/CORS_ORIGINS.
        production_frontend_origins = {"https://fleetops.netlify.app"}
        origins: list[str] = []

        raw = (self.cors_origins or "").strip()
        if raw:
            for item in raw.split(","):
                cleaned = item.strip().rstrip("/")
                if cleaned and cleaned not in origins:
                    origins.append(cleaned)

        frontend = (self.frontend_url or "").strip().rstrip("/")
        if frontend and frontend not in origins:
            origins.append(frontend)

        if env != "production":
            for local in local_dev:
                if local not in origins:
                    origins.append(local)
        else:
            for production_origin in production_frontend_origins:
                if production_origin not in origins:
                    origins.append(production_origin)

        return origins


settings = Settings()
