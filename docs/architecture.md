# Architecture - Registration API

## 1. Purpose

This document defines a production-ready architecture for a user Registration API with account activation.

Core capabilities:

- Create a user account with email and password.
- Generate a 4-digit activation code.
- Deliver activation emails asynchronously outside request flow.
- Activate account using Basic Auth and activation code.
- Enforce a 60-second activation window starting when email delivery succeeds.

## 2. Principles and Constraints

- Language: Python.
- Framework: FastAPI.
- Data access: no ORM; explicit SQL in repository layer.
- Database: MySQL 8.4.
- Email provider is a third-party service exposed over HTTP API.
- Service runs in containers with operational runbooks.

Design principles:

- Strong separation of concerns.
- Reliable failure handling and retry behavior.
- Secure credential and code handling.
- Clear observability and operability.
- Deterministic business behavior under concurrency.

## 3. High-Level Architecture

```text
[Client]
   |
   | HTTPS/JSON + Basic Auth
   v
[FastAPI API Service]
   |
   v
[MySQL] (users, activation_codes, outbox_events)
   |
   | polling + claim loop
   v
[Email Worker Service]
   |
   v
[Email Provider HTTP API]
```

The API commits business state in MySQL, then a separate worker polls outbox events and sends email asynchronously.

## 4. Runtime Components

- API service (`FastAPI`): exposes endpoints, validates input, runs domain logic, writes DB state.
- MySQL: system of record for users, activation codes, and outbox events.
- Email worker: polls and claims outbox events, calls provider, applies retry/backoff.
- Cleanup cron worker: runs periodic cleanup jobs (`registration_cleanup` every hour).

## 5. Internal Service Modules

```text
api/app/
  main.py                  -> app creation, lifespan, DI wiring
  routers/                 -> HTTP endpoints
  schemas/                 -> request/response validation
  services/                -> use-case orchestration
  repositories/            -> SQL access layer
  security/                -> hashing + Basic Auth helpers
  messaging/               -> outbox write abstractions
  exceptions/              -> domain errors + HTTP mapping
  db/                      -> pool, transaction helpers, migrations
worker/
  main.py                  -> worker bootstrap
  outbox_poller.py         -> polling + claiming loop
  email_provider_client.py -> provider integration
  retry.py                 -> backoff + dead-letter policy
  cleanup_cron.py          -> schedule and run cleanup jobs
  cleanup_tasks.py         -> SQL cleanup statements
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

Rule:

- `sent_at` is set by worker only after provider confirms email delivery.
- Activation code is stored as plaintext by design to keep implementation simple.

## 6.3 `outbox_events`

- `id` BIGINT PK AUTO_INCREMENT
- `event_type` VARCHAR(100) NOT NULL
- `payload` JSON NOT NULL
- `status` ENUM('PENDING','PROCESSING','DONE','FAILED') NOT NULL DEFAULT 'PENDING'
- `attempts` INT NOT NULL DEFAULT 0
- `next_attempt_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
- `last_error` VARCHAR(500) NULL
- `locked_by` VARCHAR(100) NULL
- `locked_at` DATETIME(6) NULL
- `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
- `processed_at` DATETIME(6) NULL

Indexes:

- `INDEX(status, next_attempt_at)`
- `INDEX(locked_at)`

## 7. API Contract

## 7.1 `POST /v1/users`

Creates a pending account and schedules asynchronous activation email delivery.
If the user is pending, override the password, generate and send a new code.

Request:

```json
{
  "email": "user@example.com",
  "password": "StrongPassw0rd!"
}
```

Responses:

- `201 Created` account created.
- `409 Conflict` email already exists.
- `422 Unprocessable Entity` invalid payload.

Example response:

```json
{
  "id": 123,
  "email": "user@example.com",
  "status": "PENDING"
}
```

## 7.2 `POST /v1/users/activate`
Activate the user.
If the code is expired, generate and send a new code.

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
- Code was not previously used.

## 7.3 `GET /heartbeat`

- `200 OK` with `{ "status": "ok" }`.

## 8. Core Flows

## 8.1 Registration

```text
Client -> API: POST /v1/users
API -> Service: register_user
Service -> DB (tx): insert users + activation_codes(sent_at NULL) + outbox_events
Service -> API: created
API -> Client: 201

Worker -> DB: select claimable outbox rows (status=PENDING and next_attempt_at<=NOW)
Worker -> Email Provider: send activation email
Worker -> DB (tx):
  - set activation_codes.sent_at = NOW
  - mark outbox event DONE
```

Key behavior:

- User creation never waits for external provider response.
- 60-second window starts when delivery succeeds.

## 8.2 Activation

```text
Client -> API: POST /v1/users/activate + Basic Auth
API -> Security: verify credentials
API -> Service: activate_user
Service -> DB (tx): lock user + most recent valid code
Service -> DB (tx): verify code, sent_at, expiry, then set user ACTIVE and code used
Service -> API: success
API -> Client: 200
```

## 9. Polling Strategy

Recommended baseline values:

- Poll interval: 5 second.
- Batch size: 50 events per cycle.
- Claim timeout recovery: reclaim `PROCESSING` rows with stale `locked_at`.

Claiming pattern:

- Use transaction.
- Select eligible rows with lock (`FOR UPDATE SKIP LOCKED` where supported).
- Transition to `PROCESSING` with `locked_by` and `locked_at`.
- Commit claim before calling provider.

This is reactive enough for the 60-second activation window because countdown starts at send success, not account creation.

## 10. Security

- Password storage: `argon2id`

- Activation code: plaintext

- Authentication: Basic Auth (for activation endpoint).

- Input validation:
- `EmailStr` for email.
- Password policy (minimum length and complexity).
- Code format regex: `^\d{4}$`.

## 11. Consistency and Concurrency

- Unique email enforced by DB unique constraint.
- Activation uses transaction + row locking (`SELECT ... FOR UPDATE`).
- Status transition guarded in transaction (`PENDING` -> `ACTIVE` only once).
- Code validation always targets most recent unused code with non-null `sent_at`.
- Failed checks atomically increment `attempt_count`.
- Activation is blocked once `attempt_count` reaches configured limit.

## 12. Error Model

Domain errors:

- `EmailAlreadyExistsError`
- `InvalidCredentialsError`
- `UserNotFoundError`
- `AccountAlreadyActiveError`
- `ActivationCodeNotDeliveredError`
- `ActivationCodeExpiredError`
- `ActivationCodeMismatchError`
- `ActivationCodeAttemptsExceededError`

FastAPI exception handlers map domain errors to stable HTTP responses:

```json
{
  "error": "activation_code_expired",
  "message": "Activation code expired",
  "details": null
}
```

## 13. Dependency Injection and Lifespan

Lifespan-managed resources:

- MySQL connection pool.
- Shared HTTP client for provider calls.

`Depends` wiring:

- `get_db_pool`
- `get_user_repository`
- `get_activation_code_repository`
- `get_outbox_repository`
- `get_registration_service`
- `get_activation_service`

## 14. Observability

- Structured logs with request/correlation IDs.
- Domain event logging for registration and activation lifecycle.
- Worker metrics:
- outbox depth
- poll cycle duration
- processing latency
- retry count
- failed event count
- provider latency and error rates

## 15. SQL Migration Strategy

- Keep explicit SQL migrations in `api/app/db/migrations/`.
- Apply migrations through a dedicated migration command/container.
- Monotonic versioning, e.g., `001_init.sql`, `002_outbox.sql`.

## 16. Periodic cleanup Cron Jobs

- `registration_cleanup` every hour:
  - Delete abandoned pending users 
  - Delete activation_codes
  - retention window (24 hours)

## 17. Docker Topology

Baseline:

- `api` service.
- `mysql` service.
- `worker` service.

Optional local service:

- email capture service for non-production environments.

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
  repositories/
    user_repository.py
    activation_code_repository.py
    outbox_repository.py
  security/
    hashing.py
    basic_auth.py
  messaging/
    outbox_writer.py
  exceptions/
    domain.py
    handlers.py
  db/
    pool.py
    migrations/
      001_init.sql
      002_outbox.sql
worker/
  main.py
  outbox_poller.py
  email_provider_client.py
  retry.py
  cleanup_cron.py
  cleanup_tasks.py
```

## 19. Trade-offs and Upgrade Path

- Polling outbox is simple and operationally lightweight for this scope.
- Polling may add small dispatch delay; acceptable because activation TTL begins on send success.
- CDC-based event propagation is the next upgrade for lower latency and higher throughput.
- Basic Auth is simple and requirement-compatible; token-based auth can be introduced later.

## 20. Implementation Roadmap

1. Add user and activation endpoints with schema validation.
2. Implement repositories and transactional service logic in raw SQL.
3. Add secure hashing for passwords.
4. Create `outbox_events` table and worker polling/claim loop.
5. Set `sent_at` only after provider send success and derive validity as `sent_at + 60s`.
6. Add provider adapter with retry/backoff and dead-letter policy.
7. Implement centralized exception handling and error schema.
8. Add operational dashboards/alerts for API and worker.
9. Publish runbooks for startup, rollback, and incident handling.
