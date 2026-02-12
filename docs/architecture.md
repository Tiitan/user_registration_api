# Architecture - Registration API (Direct Provider Send)

## 1. Purpose

This document defines a production-oriented architecture for a user Registration API with account activation.

Core capabilities:

- Create a user account with email and password.
- Generate a 4-digit activation code.
- Send activation emails through a third-party HTTP provider.
- Activate account using Basic Auth and activation code.
- Enforce a 60-second activation window once delivery timestamp is available, while allowing activation during async `sent_at` write race.

Delivery model:

- The API commits registration state first, then dispatches email asynchronously in-process.
- Delivery is best-effort (no durable delivery queue in baseline architecture).

## 2. Principles and Constraints

- Language: Python.
- Framework: FastAPI.
- Data access: no ORM; explicit SQL.
- Database: MySQL 8.4.
- Email provider: third-party HTTP API.
- Service runs in containers.

Design principles:

- Strong separation of concerns.
- Deterministic business rules under concurrency.
- Secure credential handling.
- Fast request path with bounded external-call impact.
- Explicit trade-offs around delivery guarantees.

Resilience baseline:

- Short provider timeout.
- Bounded retries for retryable failures.
- No durable recovery queue in baseline.

Trade-off in baseline:
- Simpler and faster to operate (no separate email worker runtime).
- Email delivery is best-effort, not durable at-least-once.
- after an email is successfully sent, if "sent_at" fails to be written into the database multiple times, then the code has no expiration 
    (risk mitigation: code invalidated after 5 attempt and code deleted after 1h)


## 3. High-Level Architecture

```text
[Client]
   |
   | HTTPS/JSON + Basic Auth
   v
[FastAPI API Service] -----> [Email Provider HTTP API]
   |
   v
[MySQL] (users, activation_codes)
```

The API persists business state in MySQL, then triggers asynchronous post-commit email dispatch from within the API process.

## 4. Runtime Components

- API service (`FastAPI`): endpoints, validation, domain orchestration, DB writes, post-commit email dispatch.
- MySQL: system of record for users and activation codes.
- Email provider: external HTTP dependency used by API dispatch logic (mocked).

## 5. Internal Service Modules

```text
api/app/
  main.py                    -> app creation, lifespan, DI wiring
  routers/                   -> HTTP endpoints
  schemas/                   -> request/response validation
  services/
    registration_service.py  -> registration + post-commit dispatch trigger
    activation_service.py    -> activation use case
    email_dispatcher.py      -> retries/backoff/concurrency-limited dispatch
  repositories/              -> SQL access layer
  exceptions/                -> domain errors + HTTP mapping
  db/                        -> pool, transaction helpers, migrations
  integrations/              -> email provider implementation(mocked)
```

## 6. Data Model

## 6.1 `users`

- `id` BIGINT PK AUTO_INCREMENT
- `email` VARCHAR(320) NOT NULL UNIQUE
- `password_hash` VARCHAR(255) NOT NULL
- `status` ENUM('PENDING','ACTIVE') NOT NULL DEFAULT 'PENDING'
- `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
- `activated_at` DATETIME(6) NULL

## 6.2 `activation_codes`

- `id` BIGINT PK AUTO_INCREMENT
- `user_id` BIGINT NOT NULL
- `code` CHAR(4) NOT NULL
- `sent_at` DATETIME(6) NULL
- `used_at` DATETIME(6) NULL
- `attempt_count` INT NOT NULL DEFAULT 0
- `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)

Constraints/indexes:

- `FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE`
- `INDEX(user_id, created_at DESC)`

Rules:

- `sent_at` is set only after provider send success.
- Activation validity is derived from `sent_at + 60s` when `sent_at` is available.
- Activation code is stored as plaintext by design for this scope.

## 7. API Contract

## 7.1 `POST /v1/users`

Creates a pending account and triggers asynchronous activation email delivery.
If the user is pending, overwrite password, generate a new code, and trigger new delivery.

Request:

```json
{
  "email": "user@example.com",
  "password": "StrongPassw0rd!"
}
```

Responses:

- `201 Created` account created/reset.
- `409 Conflict` email already belongs to active account.
- `422 Unprocessable Entity` invalid payload.

Behavior note:

- Response is not blocked on confirmed provider delivery.

## 7.2 `POST /v1/users/activate`

Activate the user.
If code is expired, generate/send a new code.

Requires `Authorization: Basic base64(email:password)`.

Request:

```json
{
  "code": "1234"
}
```

Responses:

- `200 OK` account activated.
- `400 Bad Request` invalid code.
- `401 Unauthorized` invalid credentials.
- `404 Not Found` account not found.
- `409 Conflict` account already active.
- `410 Gone` code expired.
- `422 Unprocessable Entity` invalid code format.

Activation eligibility:

- A matching code exists.
- If `sent_at` is set, current time is `<= sent_at + 60s`.
- If `sent_at` is not set yet, activation is still allowed to avoid rejecting users during the async persistence race.
- Code has not been used.

## 7.3 `GET /heartbeat`

- `200 OK` with `{ "status": "ok" }`.
- Liveness probe only (process is running).

## 7.4 `GET /readiness`

- Readiness probe validating operational dependencies:
- DB connectivity with a lightweight SQL check (`SELECT 1`).
- Email provider connectivity with a provider probe call (mocked in baseline runtime).
- `200 OK` with `{ "status": "ok" }` when both probes succeed.
- `503 Service Unavailable` with `{ "detail": "database unavailable" }` when DB probe fails.
- `503 Service Unavailable` with `{ "detail": "email provider unavailable" }` when provider probe fails.

## 7.5 `GET /metrics`

Prometheus scrape endpoint exposing in-process instrumentation metrics.

Response:

- `200 OK` with Prometheus text exposition content type (`text/plain; version=...`).
- Includes counters, gauges, and histogram `_count`/`_sum` lines for dispatch metrics.

## 8. Core Flows

## 8.1 Registration

```text
Client -> API: POST /v1/users
API -> Service: register_user
Service -> DB (tx): upsert pending user + insert activation_codes(sent_at NULL)
Service -> DB: commit
Service -> Dispatcher: schedule async send task (post-commit)
API -> Client: 201

Dispatcher -> Email Provider: send activation email (retry policy)
Dispatcher -> DB: set activation_codes.sent_at = NOW on success
Dispatcher -> Logs/Metrics: record final failure after retries
```

Key behavior:

- User creation stays fast and decoupled from provider latency.
- The 60-second activation window is enforced when `sent_at` is available; activation is still allowed before `sent_at` is persisted.

## 8.2 Activation

```text
Client -> API: POST /v1/users/activate + Basic Auth
API -> verify credentials
API -> Service: activate_user
Service -> DB (tx): lock user + latest created code
Service -> DB (tx): verify code, expiry, then set ACTIVE + used_at
Service -> API: success
API -> Client: 200
```

## 9. Dispatch Strategy

Recommended defaults:

- Provider timeout: 2-3 seconds.
- Max retries: 2 additional attempts (3 total tries).
- Backoff: exponential with bounded jitter.
- Concurrency control: semaphore cap for in-process dispatch workers.

Retryable conditions:

- Transport errors/timeouts.
- Provider status: `408`, `425`, `429`, `5xx`.

Non-retryable conditions:

- Other `4xx` errors.

Known limitation (best-effort):

- If process crashes after DB commit and before successful send completion, delivery attempt may be lost.

## 10. Security

- Password storage: `argon2id`.
- Activation code: plaintext in DB for this project scope.
- Authentication: Basic Auth for activation endpoint.
- Input validation:
  - email: `EmailStr`
  - password complexity policy
  - activation code regex: `^\d{4}$`

## 11. Consistency and Concurrency

- Unique email enforced by DB unique constraint.
- Registration and activation use DB transactions with row locking where needed.
- Status transition guarded (`PENDING -> ACTIVE` once).
- Code validation targets latest created.
- Failed activation checks atomically increment `attempt_count`.

## 12. Error Model

Domain errors:

- `EmailAlreadyExistsError`
- `InvalidCredentialsError`
- `UserNotFoundError`
- `AccountAlreadyActiveError`
- `ActivationCodeExpiredError`
- `ActivationCodeMismatchError`
- `ActivationCodeAttemptsExceededError`

Delivery errors:

- Provider dispatch errors are operational concerns.
- They are logged/metriced, not directly exposed as user-facing registration failures in baseline mode.

## 13. Dependency Injection and Lifespan

Lifespan-managed resources:

- MySQL connection pool.
- Shared HTTP client for provider calls.
- Email dispatcher runtime dependencies (retry policy, concurrency limiter).

`Depends` wiring baseline:

- `get_db_pool`
- `get_registration_service`
- `get_activation_service`
- `get_email_dispatcher`
- `get_email_provider_client`

## 14. Observability

- Structured JSON logs include:
  - `timestamp`, `level`, `logger`, `event`, `message`
  - `request_id`, `correlation_id`
  - optional fields: `user_id`, `activation_code_id`, `provider`, `error_type`, `error_code`, `duration_ms`
- Request context propagation:
  - incoming `X-Request-ID` and `X-Correlation-ID` are reused when present
  - values are generated when missing
  - both headers are returned on responses
- Domain errors are logged in exception handlers with `event=api_error` and stable `error_code`.
- Dispatch instrumentation (in-memory recorder in baseline, no reporting endpoint):
  - `dispatch_attempts_total`: counts every dispatch start; baseline denominator for success/failure ratios and volume trends.
  - `dispatch_successes_total`: counts dispatches that complete provider send and `sent_at` persistence path; validates delivery pipeline health.
  - `dispatch_terminal_failures_total`: counts dispatches that end in terminal failure (provider failure or final `sent_at` update failure); measures lost deliveries in the best-effort model.
  - `provider_latency_ms`: observes provider call duration; tracks external dependency performance and slowdown risk.
  - `provider_errors_total`: counts provider-call errors by `provider` and `error_type`; supports failure taxonomy and derived error-rate calculations.
  - `activation_codes_undelivered` gauge (`sent_at IS NULL`): tracks current undelivered activation code count; indicates delivery backlog/risk exposure at a point in time.
  - `provider_error_rate` is derived externally as `provider_errors_total / dispatch_attempts_total`; it is not stored as a standalone metric.
- Metrics are exposed for scraping at `GET /metrics`; no dashboarding/alerting implementation is part of this baseline scope.

## 15. Periodic Cleanup

- `registration_cleanup` every hour:
  - delete abandoned pending users older than retention window (24h)
  - delete stale activation codes according to retention policy (1h)

## 16. Docker Topology

Baseline:

- `api` service
- `mysql` service
