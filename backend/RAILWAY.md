# FleetOpt Backend — Railway Deployment

## Service layout

```
Railway project
├── fleetops   (GitHub repo, Root Directory: backend)
└── MySQL      (Railway database)
```

## fleetops service settings

| Setting | Value |
|---------|--------|
| Root Directory | `backend` |
| Builder | **Dockerfile** (`backend/Dockerfile`) |
| **Start Command** | **EMPTY** in UI — the Docker image runs `python run_server.py` |
| Healthcheck Path | `/ready` |
| Public domain port | Match Railway **Variables → PORT** (often `8080`) |

For an existing service that already uses legacy Config as Code, set **Config
File Path** to `/backend/railway.toml`; Railway does not resolve that path from
the Root Directory. New services should mirror the healthcheck/restart settings
in the dashboard because Railway no longer allows opting into legacy Config as
Code.

### Still seeing `'$PORT' is not a valid integer`?

Railway is running `uvicorn ... --port $PORT` instead of our Dockerfile. Fix **all**:

1. **Settings → Deploy → Custom Start Command** → delete all text → Save
2. **Variables** → delete `PORT` if its value is literally `$PORT`; Railway injects `PORT` automatically
3. **Settings → Build** → Builder = **Dockerfile**
4. **Redeploy** from latest GitHub commit (not just Restart)

Good logs look like:
```
Running database migrations...
Starting uvicorn on port 8080...
```

## Environment variables

1. Open **fleetops** → **Variables** → **Raw Editor**
2. Paste from [`railway.env.example`](railway.env.example)
3. Set `SECRET_KEY` to a 32+ character random string
4. Set `DATABASE_URL` to the MySQL service's private `MYSQL_URL` reference.
   Use Railway's variable picker so the service name is exact, for example:

   ```env
   DATABASE_URL=${{MySQL.MYSQL_URL}}
   ```

   If your database tile has another name, replace `MySQL` through autocomplete.
   The backend also accepts `MYSQL_URL` or all five discrete `MYSQL*` variables,
   but it will never fall back to localhost in a hosted deployment.

Review and deploy the staged variable changes. Migrations run automatically on
container start via `run_server.py`; a production deployment will not start if
the database reference is missing, local, or unavailable.

## Contact Support email (Resend)

On the **fleetops** service → **Variables**, add:

| Variable | Value |
|----------|--------|
| `RESEND_API_KEY` | Your Resend key (`re_…`) |
| `FEEDBACK_INBOX_EMAIL` | Your Gmail (or ops inbox) that should receive tickets |
| `EMAIL_FROM` | **Must use a verified Resend domain**, e.g. `FleetOpt <noreply@deliverexapp.com>` |

Do **not** use `notifications@fleetopt.com` unless that domain is verified in Resend — sends will fail silently from the customer’s point of view.

Notes:

1. If `FEEDBACK_INBOX_EMAIL` is empty, the API still emails every **Admin** user email in the database.
2. Resend only delivers when `EMAIL_FROM` is an allowed sender (verify your domain in Resend, or use `onboarding@resend.dev` for sandbox tests).
3. After saving Variables, Railway redeploys — wait for Deployments → Success, then submit Contact Support once to verify.
4. Never commit the API key to GitHub; set it only in Railway Variables.

## Verify

| URL | Expected |
|-----|----------|
| `https://YOUR-RAILWAY-DOMAIN/health` | `{"status":"ok"}` (process liveness only) |
| `https://YOUR-RAILWAY-DOMAIN/ready` | `{"status":"ready"}` |

Railway's deployment healthcheck uses `/ready`, so a release is not marked
healthy unless it can actually connect to MySQL.

Run the `/health` check against the exact domain shown in Railway under
**Settings → Networking → Public Networking**. If Railway returns its own
`404` response with `"message":"Application not found"`, that hostname is
stale or is no longer attached to the service. Generate/restore a public
domain in Railway before changing CORS settings; an unreachable hostname can
look like a CORS failure in the browser because Railway's fallback response
does not include your API's CORS headers.

## Netlify frontend

The production browser should use Netlify as a same-origin API proxy:

```
NEXT_PUBLIC_API_URL=/api-proxy
BACKEND_ORIGIN=https://YOUR-RAILWAY-DOMAIN
```

1. Copy the active Railway public domain from **Settings → Networking**.
2. In Netlify → **Site configuration → Environment variables**, set
   `BACKEND_ORIGIN` to that Railway HTTPS origin. Do not add `/api` or a
   trailing slash. Production intentionally has no localhost or old-provider
   fallback, so a missing/unsafe value fails the build clearly.
3. In Railway Variables, set both `FRONTEND_URL` and `CORS_ORIGINS` to the
   exact Netlify production origin (`https://fleetops.netlify.app`). This is
   also used for password-reset and payment redirect links.
4. Redeploy Railway, verify `/ready`, then redeploy Netlify so its build and
   proxy rules use the current backend domain.

The browser URL becomes `/api-proxy/auth/login`; Netlify forwards it to
`https://YOUR-RAILWAY-DOMAIN/api/auth/login`. Because the browser talks to its
own Netlify origin, routine API requests do not depend on cross-origin CORS.

## Troubleshooting

| Log / symptom | Fix |
|---------------|-----|
| Console says **container is not running (exited)** | Open **Deployments → View Logs** (not Console). Fix env vars below, then redeploy. |
| `FATAL: ... will not fall back to localhost` | Remove any local `DATABASE_URL`; set `DATABASE_URL` to the MySQL service's `MYSQL_URL` reference using Railway autocomplete, then deploy the staged change. |
| `ValidationError` on `SECRET_KEY` / `FRONTEND_URL` | Set all vars in `railway.env.example` |
| Railway response says `Application not found` | The configured Railway hostname is detached/stale. Generate or restore the service's public domain, update Netlify's `BACKEND_ORIGIN`, then redeploy Netlify. |
| Browser reports CORS and the API response is Railway `404` | Fix the Railway public domain first. This response is from Railway's edge, not FastAPI, so changing `CORS_ORIGINS` alone cannot fix it. |
| Browser reports CORS but Railway `/health` is `200` | Set Railway `FRONTEND_URL` and `CORS_ORIGINS` to the exact Netlify origin (currently `https://fleetops.netlify.app`), then redeploy Railway. |
| `No module named 'app'` | Root Directory must be `backend` |
| `/health` OK, `/ready` fails | Check `DATABASE_URL` references the private Railway `MYSQL_URL`; `/health` intentionally does not test MySQL. |
| `'$PORT' is not a valid integer` | Clear Custom Start Command; remove bad `PORT` variable; use Dockerfile + `railway.toml` |
| Login works locally but not on Netlify | Verify Railway `/ready`, set Netlify `BACKEND_ORIGIN` to the active Railway HTTPS origin, confirm `NEXT_PUBLIC_API_URL=/api-proxy`, and redeploy Netlify. |
| Helper proofs upload OK but images 404 later | Mount a **Railway Volume** at `/app/uploads` (`UPLOADS_ROOT`). Ephemeral disk loses files on redeploy. |
| Uploads 404 on Netlify | Confirm Netlify's `BACKEND_ORIGIN` is the active Railway origin; the Next.js `/uploads/*` route uses the same proxy setting. |
