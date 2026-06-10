## Deployment Checklist — Qimen API

### Goal
Ensure that we can safely deploy the FastAPI backend by:

- Providing a complete list of the environment variables the service requires.
- Documenting a deterministic health check endpoint that operators (or orchestrators) can use to confirm the app is running.
- Describing the database migration/initialization workflow that keeps the PostgreSQL schema in sync with the SQLAlchemy models.

### 1. Environment Variables
| Name | Required | Description |
| --- | --- | --- |
| `DATABASE_URL` | ✅ | PostgreSQL connection string used by SQLAlchemy. Example: `postgresql://<user>:<pass>@<host>:<port>/postgres`. Must use SSL if your provider requires it.
| `STRIPE_SECRET_KEY` | ✅ | Secret API key for Stripe server-side calls (charging customers, handling subscriptions).
| `STRIPE_API_KEY` | ✅ | Publishable key that can be returned to the frontend (when present in docs or client callbacks).
| `STRIPE_WEBHOOK_SECRET` | ✅ | Signing secret used to validate webhook payloads from Stripe.
| `STRIPE_PRICE_VIP` | ✅ | Price ID for the VIP tier handled in the billing flows.
| `STRIPE_PRICE_LIFETIME` | ✅ | Price ID for the lifetime membership tier.
| `STRIPE_PRICE_5_CREDITS` | ✅ | Price ID that grants 5 credits (micro purchase).
| `STRIPE_PRICE_15_CREDITS` | ✅ | Price ID that grants 15 credits.
| `DEEPSEEK_API_KEY` | ✅ | API key used by `services/qimen.py` to call the Deepseek inference backend.
| `GMAIL_APP_PASSWORD` | ⚠️ | Optional, only required if you send emails via Gmail/SMTP. Paired with `SENDER_EMAIL` and the built-in SMTP settings defined in `config.py`.

**Notes**

- `config.py` loads the `.env` file at startup, so you can define these variables locally in an `.env` file or inject them via your deployment platform (Docker secrets, Kubernetes secrets, etc.).
- Avoid committing the `.env` file with secrets—store it securely and reference it through the deployment environment.
- The SMTP server and port (`smtp.gmail.com:587`) and sender email (`kenttangtel@gmail.com`) are hard-coded in `config.py`, so no additional variables are needed for them.

### 2. Health Check Endpoint
The repository currently does not expose a dedicated `/health` endpoint. Please add one with a minimal implementation so the deployment platform can detect readiness and liveness.

#### Recommended implementation

```python
from fastapi import FastAPI

app = FastAPI()

@app.get("/health")
async def health_check():
    return {"status": "ok"}
```

This handler should be registered alongside the other routers (`divination`, `auth`, etc.) so it is always available.

#### Deployment guidance

- Configure your load balancer/orchestrator to hit `GET /health` (or a similar `/healthz` route) before routing traffic.
- Expect a `200 OK` response with a JSON body like `{"status":"ok"}`. Any other status (5xx or timeouts) should trigger a restart of the pod/container.
- Optionally, extend the handler to perform lightweight checks (e.g., database connectivity) if you need a more thorough signal.

### 3. Database Migration / Schema Initialization
This service relies on SQLAlchemy models defined in `models/db.py` and currently relies on `Base.metadata.create_all()` for schema creation.

#### Startup migration flow

1. **Ensure `DATABASE_URL` is valid** and points to your target PostgreSQL database. This value is required before any database actions can succeed.
2. **Install dependencies** via `pip install -r requirements.txt` (only once per environment or inside your Dockerfile). Include the same requirement list when packaging the container.
3. **Run schema creation** by starting the app as normal (`uvicorn main:app --host 0.0.0.0 --port 8000`)—the startup hook in `main.py` calls `init_db()` automatically, which does `Base.metadata.create_all(bind=engine)`.
4. Alternatively, you can run the initialization manually (useful for CI/CD jobs) with:

```bash
python -c "from models.db import init_db; init_db()"
```

This ensures tables like `users` and `history` exist before the service processes requests.

#### Handling schema changes

- Currently there is no migration framework such as Alembic. When you add/remove columns, update the models in `models/db.py` and then rerun the initialization command above. SQLAlchemy will issue `CREATE TABLE` statements for missing tables, but it will not automatically alter existing columns—handle those manually with `ALTER TABLE` statements or add a migration tool if you need more control.
- Consider adding Alembic (or another migration tool) in the future if the schema evolves frequently.

#### Verification

- Connect to the database (`psql` or any SQL client) and run `SELECT table_name FROM information_schema.tables WHERE table_schema='public';` to ensure `users` and `history` exist.
- You can also verify that users can be created by invoking the `/auth` endpoints or hitting your own scripts that use `get_db()`.

### 4. Deployment Checklist Summary

1. [ ] Populate all required environment variables securely before deployment—use a secret manager / `.env` for local testing.
2. [ ] Ensure `pip install -r requirements.txt` runs within your build process or Dockerfile.
3. [ ] Run the database initialization command manually (optional) and/or rely on the startup hook built into `main.py`.
4. [ ] Deploy the service behind a load balancer that probes `GET /health` (or your configured endpoint) before routing traffic.
5. [ ] Monitor logs for any errors coming from the Deepseek or Stripe integrations; missing secrets will raise immediate exceptions during startup.

Once every checkbox is green, the app should be ready for production traffic.