## Deployment Checklist — Qimen API

### Goal
Ensure that we can safely deploy the FastAPI backend by:

- Providing a complete list of the environment variables the service requires.
- Documenting a deterministic health check endpoint that operators (or orchestrators) can use to confirm the app is running.
- Describing the database migration/initialization workflow that keeps the PostgreSQL schema in sync with the SQLAlchemy models.

### 1. Environment Variables
| Name | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | ✅ | PostgreSQL connection string used by SQLAlchemy. Example: `postgresql://<user>:<password>@<host>:<port>/postgres`. Must use SSL if your provider requires it. |
| `STRIPE_SECRET_KEY` | ✅ | Secret API key for Stripe server-side calls (charging customers, handling subscriptions). |
| `STRIPE_WEBHOOK_SECRET` | ✅ | Signing secret used to validate webhook payloads from Stripe. |
| `SECRET_KEY` | ✅ | JWT signing key. Generate with `python -c "import secrets; print(secrets.token_urlsafe(48))"`. (`JWT_SECRET_KEY` is accepted as an alias.) |
| `REVENUECAT_WEBHOOK_TOKEN` | ✅ | Shared secret for the RevenueCat S2S webhook. **If unset the endpoint returns 503 and grants no credits** (fail-closed). There is no default token. |
| `RESEND_API_KEY` | ✅ | API key for the Resend HTTP API, used by `/api/v1/auth/forgot-password`. **Without it, password reset returns 503.** |
| `STRIPE_API_KEY` | ⚠️ | Publishable key that can be returned to the frontend (when present in docs or client callbacks). |
| `STRIPE_PRICE_VIP` | ⚠️ | Price ID for the VIP monthly tier. Unset prices are simply unavailable for purchase. |
| `STRIPE_PRICE_LIFETIME` | ⚠️ | Price ID for the lifetime membership tier. |
| `STRIPE_PRICE_5_CREDITS` | ⚠️ | Price ID that grants 5 credits (micro purchase). |
| `STRIPE_PRICE_15_CREDITS` | ⚠️ | Price ID that grants 15 credits. |
| `DEEPSEEK_API_KEY` | ⚠️ | API key used to call the DeepSeek inference backend. Without it, `/divination/interpret` returns 503. |
| `RESEND_FROM_EMAIL` | ⚠️ | Sender address for password-reset mail. Defaults to `onboarding@resend.dev`. |
| `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY` | ⚠️ | When both are set, membership/credit writes are mirrored directly into Supabase. |
| `ALLOWED_ORIGINS` | ⚠️ | Comma-separated CORS allow-list. Defaults to localhost + the Hugging Face Space origin. Do **not** set `*` in production. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | ⚠️ | JWT lifetime in minutes. Defaults to `60`. |
| `GMAIL_APP_PASSWORD` | ⚠️ | Legacy SMTP credential. Password reset now uses Resend, so this is normally unused. |

**Notes**

- `config.py` loads the `.env` file at startup, so you can define these variables locally in an `.env` file or inject them via your deployment platform (Docker secrets, Kubernetes secrets, etc.).
- Copy `.env.example` to `.env` and fill in real values. **Never commit `.env`** — it is git-ignored, along with `pw.txt`, `API KEY.txt`, `*credential*.json` and `*service_account*.json`.
- Never paste secrets into source files. A webhook signing secret that has ever been committed must be treated as compromised and rotated.

### 2. Health Check Endpoint

`GET /health` is implemented in `main.py`. It runs a lightweight `SELECT 1` against the database and returns:

```json
{"status": "ok", "database": true}
```

- `200` — service and database are healthy.
- `503` — the process is up but the database probe failed (`{"status":"degraded","database":false}`).

#### Deployment guidance

- Configure your load balancer/orchestrator to hit `GET /health` before routing traffic.
- Any 5xx or timeout should trigger a restart of the pod/container.

### 3. Database Migration / Schema Initialization
This service relies on SQLAlchemy models defined in `models/db.py` and uses `Base.metadata.create_all()` for schema creation.

#### Startup migration flow

1. **Ensure `DATABASE_URL` is valid** and points to your target PostgreSQL database. This value is required before any database actions can succeed.
2. **Install dependencies** via `pip install -r requirements.txt` (only once per environment or inside your Dockerfile).
3. **Run schema creation** by starting the app as normal (`uvicorn main:app --host 0.0.0.0 --port 7860`)—the lifespan hook in `main.py` calls `init_db()` automatically, which does `Base.metadata.create_all(bind=engine)`.
4. Alternatively, run the initialization manually (useful for CI/CD jobs) with:

```bash
python -c "from models.db import init_db; init_db()"
```

This ensures tables like `users`, `history` and `revenuecat_events` exist before the service processes requests.

> **Note:** `revenuecat_events` is an idempotency ledger. RevenueCat retries webhook deliveries; recording each processed event id prevents credits being granted twice for the same purchase.

#### Handling schema changes

- There is currently no migration framework such as Alembic. When you add/remove columns, update the models in `models/db.py` and then rerun the initialization command above. SQLAlchemy will issue `CREATE TABLE` statements for missing tables, but it will not automatically alter existing columns—handle those manually with `ALTER TABLE` statements or add a migration tool if you need more control.
- Consider adding Alembic (or another migration tool) in the future if the schema evolves frequently.

#### Verification

- Connect to the database (`psql` or any SQL client) and run `SELECT table_name FROM information_schema.tables WHERE table_schema='public';` to ensure `users`, `history` and `revenuecat_events` exist.
- You can also verify that users can be created by invoking the `/auth` endpoints or hitting your own scripts that use `get_db()`.

### 4. Deployment Checklist Summary

1. [ ] Populate all required environment variables securely before deployment—use a secret manager / `.env` for local testing.
2. [ ] Rotate any credential that has ever been committed to the repository (Stripe webhook secret, Stripe keys, DeepSeek key, Google API key, RevenueCat token, JWT `SECRET_KEY`).
3. [ ] Ensure `pip install -r requirements.txt` runs within your build process or Dockerfile.
4. [ ] Run the database initialization command manually (optional) and/or rely on the lifespan hook built into `main.py`.
5. [ ] Deploy the service behind a load balancer that probes `GET /health` before routing traffic.
6. [ ] Point the Stripe dashboard webhook at `/api/v1/payment/webhook` and the RevenueCat dashboard webhook at `/api/v1/payment/webhook/revenuecat`.
7. [ ] Monitor logs for errors from the DeepSeek, Stripe and Resend integrations.

Once every checkbox is green, the app should be ready for production traffic.
