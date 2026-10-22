# FleetOpt Backend — Render Deployment

The repository root [`render.yaml`](../render.yaml) creates:

- `fleetops-api`: the public FastAPI web service
- `fleetops-mysql`: a private MySQL 8 service
- persistent disks for MySQL data and uploaded files

Both services use the Singapore region so they can talk on Render's private
network. The Blueprint generates the JWT secret and database password; no
credentials are committed to Git.

> Render only manages PostgreSQL directly. This project is MySQL-only. There is
> **no `.db` file** in the repo (and none should be committed). Schema is created
> at boot by Alembic. MySQL itself is the official `mysql:8.0` image from Docker
> Hub, with a persistent disk. Disks and private networking require paid compute.
>
> The API uses the `1c-2g` plan because analytics imports pandas/scikit-learn.
> MySQL stays on `0.5c-512mb`. Upgrade either service in the dashboard if you
> see out-of-memory restarts.

## Deploy MySQL without GitHub (recommended)

Do **not** pick a `backend/` folder. Cancel the Git root-directory picker.

1. **New → Private Service**.
2. Under **Source**, choose **Existing Image** (not the GitHub repo).
3. Image URL: `mysql:8.0` (or `docker.io/library/mysql:8.0`) → **Connect**.
4. Name: `fleetops-mysql`. Same **region** as `fleetops-f1jg`. Plan `$7 / 0.5 CPU` is fine.
5. Environment:

   | Key | Value |
   |---|---|
   | `MYSQL_DATABASE` | `fleetopt` |
   | `MYSQL_USER` | `fleetopt` |
   | `MYSQL_PASSWORD` | Generate |
   | `MYSQL_ROOT_PASSWORD` | Generate |

6. **Advanced → Disk**: mount path `/var/lib/mysql`, size `10 GB`.
7. Deploy and wait until **Live**. Copy the internal host (looks like `fleetops-mysql-xxxx`).

Then on **fleetops** (the API) → **Environment**, set `MYSQL_HOST` to that internal host, plus `MYSQL_PORT=3306`, `MYSQL_DATABASE=fleetopt`, `MYSQL_USER=fleetopt`, and the **same** `MYSQL_PASSWORD`. Leave `DATABASE_URL` unset. Redeploy the API.

## Deploy

1. Create MySQL from the Docker Hub image (steps above). You do not commit a database.
2. In Render, choose **New → Blueprint** if you still want `render.yaml` to wire both services later.
3. Wait for `fleetops-mysql` to become available. The API retries Alembic for
   up to five minutes (`MIGRATION_MAX_ATTEMPTS=60`) while MySQL initializes,
   then binds Render's `PORT`. Render checks `/health` before routing traffic.
4. Copy the public URL Render assigns to `fleetops-api`, for example
   `https://fleetops-api-xxxx.onrender.com`.

If you create the services by hand instead of the Blueprint, paste values from
[`render.env.example`](render.env.example). Leave `DATABASE_URL` unset and let
`run_server.py` build it from `MYSQL_HOST`, `MYSQL_USER`, `MYSQL_PASSWORD`,
and `MYSQL_DATABASE`. Keep MySQL private; do not expose port 3306 publicly.

Optional secrets (Resend, Google Maps, Xendit) are not in the Blueprint. Add
them later under **fleetops-api → Environment**.

## Verify

Replace `YOUR-RENDER-DOMAIN` below with the assigned hostname:

| URL | Expected |
|---|---|
| `https://YOUR-RENDER-DOMAIN/health` | `{"status":"ok"}` |
| `https://YOUR-RENDER-DOMAIN/ready` | `{"status":"ready"}` |
| `https://YOUR-RENDER-DOMAIN/` | backend path discovery JSON |
| `https://YOUR-RENDER-DOMAIN/docs` | FastAPI documentation |

`/health` is liveness only. `/ready` confirms MySQL connectivity.

## Connect Netlify

After both health checks pass, replace the backend hostname in all three
locations in the repository-root [`netlify.toml`](../netlify.toml):

- `BACKEND_ORIGIN`
- the `/api-proxy/*` destination
- the `/uploads/*` destination

Keep `NEXT_PUBLIC_API_URL=/api-proxy`, then redeploy Netlify. Browser login
requests will use `/api-proxy/auth/login`, which Netlify forwards to Render's
`/api/auth/login` endpoint.

Do not point Netlify at Render until `/health` returns `200` from the assigned
`onrender.com` hostname. A placeholder Render URL will break production login.

## Existing data

The new MySQL disk starts empty. Alembic creates the schema, but it does not
copy Railway records. When Railway is available again, export its database
with `mysqldump` and import that dump into `fleetops-mysql` using Render's
service shell.

Uploaded files also require a separate copy from the old Railway volume. The
database dump contains only their stored paths, not the files themselves.

## Troubleshooting

| Log / symptom | Fix |
|---|---|
| API deploy fails with migration errors | Open `fleetops-mysql` logs first. First boot can take a few minutes; the API retries for five minutes, then Render will retry the deploy. |
| `/health` OK, `/ready` fails | Confirm `MYSQL_HOST` comes from the private service and `MYSQL_PORT` is `3306`, not Render's HTTP `PORT`. |
| `ValidationError` on `SECRET_KEY` | Let the Blueprint generate it, or paste a 32+ character secret. |
| Uploads 404 after redeploy | Confirm the API disk is mounted at `/app/uploads` and `UPLOADS_ROOT=/app/uploads`. |
| Contact Support emails never arrive | Add `RESEND_API_KEY` and `FEEDBACK_INBOX_EMAIL` on `fleetops-api`. `EMAIL_FROM` must use a verified Resend domain. |
