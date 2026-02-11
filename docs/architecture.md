# Architecture - Registration API (Direct Provider Send)

## 1. Purpose

This document defines a production-oriented architecture for a user Registration API with account activation.

Core capabilities:

- Create a user account with email and password.
- Generate a 4-digit activation code.
- Send activation emails through a third-party HTTP provider.
- Activate account using Basic Auth and activation code.
- Enforce a 60-second activation window starting when email delivery succeeds.

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
- Email provider: external HTTP dependency used by API dispatch logic.

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
  integrations/
    email_provider_client.py -> HTTP provider integration
  repositories/              -> SQL access layer
  security/                  -> hashing + Basic Auth helpers
  exceptions/                -> domain errors + HTTP mapping
  db/                        -> pool, transaction helpers, migrations
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
- Activation validity is derived from `sent_at + 60s`.
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
- `sent_at` is set.
- Current time is `<= sent_at + 60s`.
- Code has not been used.

## 7.3 `GET /heartbeat`

- `200 OK` with `{ "status": "ok" }`.

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
- The 60-second activation window starts only when `sent_at` is written.

## 8.2 Activation

```text
Client -> API: POST /v1/users/activate + Basic Auth
API -> Security: verify credentials
API -> Service: activate_user
Service -> DB (tx): lock user + latest valid code
Service -> DB (tx): verify code, sent_at, expiry, then set ACTIVE + used_at
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
- Code validation targets latest delivered, unused code.
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

- Structured logs with request/correlation IDs.
- Domain event logs for registration and activation lifecycle.
- Dispatch metrics:
  - dispatch attempts
  - dispatch successes
  - dispatch failures (terminal)
  - provider latency
  - provider error rate
  - undelivered activation code count (`sent_at IS NULL`)

## 15. SQL Migration Strategy

- Keep explicit SQL migrations in `api/app/db/migrations/`.
- Apply migrations through a dedicated migration command/container.
- Monotonic versioning, e.g., `001_init.sql`, `002_*.sql`.

## 16. Periodic Cleanup

- `registration_cleanup` every hour:
  - delete abandoned pending users older than retention window (e.g., 24h)
  - delete stale activation codes according to retention policy

## 17. Docker Topology

Baseline:

- `api` service
- `mysql` service

Optional local service:

- email capture/mock service for non-production environments

## 18. Project Layout

```text
api/app/
  main.py
  routers/
    heartbeat.py
    users.py
  schemas/
    users.py
    errors.py
  services/
    registration_service.py
    activation_service.py
    email_dispatcher.py
  integrations/
    email_provider_client.py
  repositories/
  security/
    hashing.py
    basic_auth.py
  exceptions/
    domain.py
    handlers.py
  db/
    pool.py
    migrations/
      001_init.sql
```

## 19. Trade-offs and Upgrade Path

Trade-off in baseline:

- Simpler and faster to operate (no separate worker runtime).
- Delivery is best-effort, not durable at-least-once.

Upgrade path:

- Introduce outbox + worker/queue for durable at-least-once dispatch when scale/guarantees require it.

## 20. Implementation Roadmap

1. Implement registration and activation endpoints with schema validation.
2. Implement transactional SQL service logic (no ORM).
3. Add password hashing and Basic Auth verification.
4. Integrate provider HTTP client in API process.
5. Add post-commit async dispatch trigger from registration and resend flows.
6. Implement bounded retry/backoff + concurrency limits for provider calls.
7. Set `sent_at` only after provider success.
8. Add dispatch observability and incident/runbook guidance.
