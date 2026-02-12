# Project Review & Recommendations

> **Project:** FastAPI User Registration API
> **Purpose:** Staff job interview demonstration
> **Review date:** 2026-02-12

---

## What's Done Well

- Clean layered architecture (routers → services → repositories) with no ORM leakage
- Explicit SQL with row-level locking for transactional correctness
- Post-commit async dispatch pattern separating the write path from side effects
- Argon2id password hashing (current best practice)
- Structured JSON logging with request/correlation ID propagation
- Prometheus metrics with custom in-memory collector
- Multi-stage Docker build with separate runtime, test, and cleanup targets
- Comprehensive quality pipeline (ruff + mypy + bandit + pip-audit + pytest)

---

## Security

### 1. Add rate limiting on the activation endpoint

The `POST /v1/users/activate` endpoint has per-code attempt limits (5), but no global rate limit. An attacker could cycle through codes by triggering re-registration.

**Recommendation:** Add IP-based rate limiting middleware (e.g. `slowapi` or a custom middleware).

### 2. Consider larger activation codes

A 4-digit code has only 10,000 combinations. With 5 attempts per code the probability of guessing is 0.05%, which is acceptable — but combined with the ability to re-register (which resets the code), this could be exploited.

**Recommendation:**
- Add a cooldown between re-registration attempts for the same email
- Use 6-digit codes for a stronger security margin

### 4. Secrets in docker-compose.yml

DB credentials are hardcoded in the compose file.

**Recommendation:** For a production deployment, use Docker secrets or an external vault. Fine for demo purposes, but worth a note in the docs.

---

## Resilience & Correctness

### 5. Email dispatch is fire-and-forget

If the process crashes between commit and email delivery, the code exists in DB but the user never receives it. The cleanup job handles stale records eventually.

**Recommendation:**
- Add a startup recovery sweep that retries `sent_at IS NULL` codes on boot
- Document this trade-off explicitly in `docs/architecture.md`

### 6. No health check for DB connectivity

The `GET /heartbeat` endpoint returns `{"status": "ok"}` without checking DB availability.

**Recommendation:** Add a `GET /readiness` endpoint that verifies the pool is connected. Kubernetes distinguishes liveness (process alive) from readiness (can serve traffic) — both are useful.

### 7. Pool exhaustion under load

`mysql_pool_maxsize=10` with `email_dispatch_max_concurrency=50` means background dispatchers could starve API requests for connections.

**Recommendation:** Either use a separate pool for background tasks or reduce dispatch concurrency to be <= pool size.

---

## Code Quality

### 8. Missing `__all__` exports

Most `__init__.py` files are empty.

**Recommendation:** Add explicit `__all__` lists to make the public API of each module clearer, especially for `services/`, `repositories/`, and `exceptions/`.

### 9. PasswordHasher instantiation per request

`registration_service.py` creates a new `PasswordHasher()` instance on each request via `get_registration_service` in `dependencies.py`. `PasswordHasher` is stateless.

**Recommendation:** Create it once at startup and inject it, or make it a module-level constant.

### 10. Verify activation code randomness

If `random.randint` is used instead of `secrets`, it is not cryptographically secure.

**Recommendation:** Verify that activation codes are generated using `secrets.choice` or `secrets.randbelow`. This is a common interview discussion point.

---

## Testing

### 11. No unit tests

All tests are integration tests hitting a live MySQL instance.

**Recommendation:** Add unit tests for:
- Password validation logic (pure function, no DB needed)
- Activation code expiry checks
- Metrics recording

This would also speed up the test suite significantly.

### 12. No tests for the cleanup script

`scripts/registration_cleanup.py` has no test coverage.

**Recommendation:** Test dry-run mode and edge cases (no stale records, mixed states).

### 13. Fragile test isolation

The `clean_tables_for_users_integration_tests` fixture in `conftest.py` uses filename-based conditional logic. Renaming a test file would silently skip cleanup.

**Recommendation:** Use pytest markers instead (`@pytest.mark.db_cleanup`).

---

## Observability

### 14. No request duration metric

Provider latency (`provider_latency_ms`) is tracked, but not overall API request latency.

**Recommendation:** Add a middleware-level histogram for request duration per endpoint. Valuable for SLO monitoring.

### 15. No error rate metric

HTTP 4xx/5xx responses are not counted.

**Recommendation:** Track response status as counters (`http_requests_total{status="4xx"}`). This is standard Prometheus practice and rounds out the observability story.

---

## Documentation & Developer Experience

### 16. No mention of auto-generated API docs

FastAPI auto-generates OpenAPI docs at `/docs` and `/redoc`.

**Recommendation:** Mention this in the README. Interviewers may look for it.

### 17. Postman collection maintenance

The Postman collection is useful but can drift from the actual API.

**Recommendation:** Generate it from the OpenAPI spec or add a note about keeping it in sync.

---

## Minor Nits

### 18. Starlette pinned separately in requirements.txt

FastAPI already depends on Starlette. Pinning it separately risks version conflicts.

**Recommendation:** Remove the explicit pin and let FastAPI manage its own Starlette dependency.

### 19. Typo in git history

Commit `3bcb98e` reads "osbervability" instead of "observability".