# User Registration API

Production-style FastAPI service for user registration and account activation with:
- MySQL persistence (no ORM, explicit SQL repositories)
- asynchronous activation email dispatch (mock provider)
- 4-digit activation code with 60-second validity window (when `sent_at` is known)
- structured logging + request/correlation IDs
- Prometheus-compatible metrics endpoint
- hourly cleanup job for stale pending registrations and old activation codes

## Project Contents

Key folders:
- `api/app`: FastAPI app, routers, services, repositories, DB access, observability
- `db/init`: MySQL schema initialization SQL
- `scripts`: cleanup script and quality pipeline
- `scripts/cron`: cron schedule and scheduler launcher
- `tests`: integration and observability tests
- `docs`: architecture and specification notes
- `postman`: Postman collection

## How It Works

1. `POST /v1/users` creates (or resets) a `PENDING` user, generates a 4-digit code, and stores it with `sent_at=NULL`.
2. After DB commit, email sending is scheduled in a background task.
3. The mock email provider simulates delivery, then the dispatcher sets `activation_codes.sent_at` and records metrics.
4. `POST /v1/users/activate` uses Basic Auth (`email:password`) + code:
   - validates credentials
   - checks latest code, attempt limit, and expiration (`sent_at + 60s`)
   - activates user and marks code as used on success
5. A cleanup container runs hourly and deletes stale data by retention policy.

## Run With Docker Compose

```bash
docker compose up --build
```

Services:
- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Heartbeat: `http://localhost:8000/heartbeat`
- Readiness: `http://localhost:8000/readiness`
- Metrics: `http://localhost:8000/metrics`
- MySQL: `localhost:3306`

Reset DB state (re-run init SQL):

```bash
docker compose down -v
docker compose up --build
```

## API Usage

Create user:

```bash
curl -X POST http://localhost:8000/v1/users \
  -H "Content-Type: application/json" \
  -d '{"email":"user@example.com","password":"StrongPass123"}'
```

Get activation code from API logs (mock provider prints it):

```bash
docker logs user_registration_api --tail 200
```

Look for log lines containing `Simulated email provider HTTP request ... code=1234`.

Activate user:

```bash
curl -X POST http://localhost:8000/v1/users/activate \
  -u "user@example.com:StrongPass123" \
  -H "Content-Type: application/json" \
  -d '{"code":"1234"}'
```

## Endpoints

- `POST /v1/users`
  - Creates a new pending user or resets a pending one.
  - Returns `201`, or `409` if email already belongs to an active account.
- `POST /v1/users/activate`
  - Requires Basic Auth and `{"code":"dddd"}`.
  - Returns `200` on success.
  - Can return `400`, `401`, `404`, `409`, `410`, `422` depending on domain state.
- `GET /heartbeat`
  - Liveness probe (`{"status":"ok"}`).
- `GET /readiness`
  - Readiness probe with dependency checks:
  - SQL connectivity check (`SELECT 1`)
  - Email provider probe (mock provider readiness hook)
  - Returns `200 {"status":"ok"}` when dependencies are reachable.
  - Returns `503 {"detail":"database unavailable"}` when DB is not reachable.
  - Returns `503 {"detail":"email provider unavailable"}` when provider probe fails.
- `GET /metrics`
  - Prometheus text exposition for dispatch/latency/gauge metrics.

## Cleanup Job

The `cleanup` service runs this command on startup and then every hour:

```bash
python -m scripts.registration_cleanup
```

Defaults:
- delete `PENDING` users older than 24h
- delete activation codes older than 1h

Manual examples:

```bash
python -m scripts.registration_cleanup --dry-run
python -m scripts.registration_cleanup --pending-user-retention-hours 48 --activation-code-retention-hours 2
```

## Testing

Run tests in Docker:

```bash
docker compose run --rm test
```

Or with profile:

```bash
docker compose --profile test up --build test
```

Run local quality pipeline (ruff, bandit, mypy, pip-audit, pytest):

```bash
python -m scripts.quality_test_all
```

## Configuration

Main environment variables (see `api/app/config.py`):
- `MYSQL_HOST`, `MYSQL_PORT`, `MYSQL_USER`, `MYSQL_PASSWORD`, `MYSQL_DATABASE`
- `ACTIVATION_CODE_TTL_SECONDS` (default `60`)
- `ACTIVATION_CODE_MAX_ATTEMPTS` (default `5`)
- `EMAIL_PROVIDER_MAX_RETRIES` (default `3`)
- `EMAIL_DISPATCH_MAX_CONCURRENCY` (default `50`)
- `LOG_LEVEL` (default `INFO`)
- `CORS_ALLOW_ORIGINS` (default `http://localhost:3000,http://127.0.0.1:3000`)
- `CORS_ALLOW_CREDENTIALS` (default `true`)
- `CORS_ALLOW_METHODS` (default `*`)
- `CORS_ALLOW_HEADERS` (default `*`)

## Additional References

- Architecture details: `docs/architecture.md`
- Original specification: `docs/specifications.md`
- Postman collection: `postman/user_registration_api.postman_collection.json`
