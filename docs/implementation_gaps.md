# Implementation Gaps (Current Repo Status)

This section tracks architecture items that are documented but not implemented yet in the current codebase.

### 1 Missing Module Boundaries

- `integrations/email_provider_client.py` is not implemented as a separate integration client.
- `repositories/` SQL access layer package is not implemented; SQL currently lives in service classes.
- `security/` package (e.g., hashing/basic_auth helpers) is not implemented as separate modules; logic is currently inside services/routers.
- `exceptions/handlers.py` is not implemented; HTTP mapping is handled inline in routers.

### 2 Email Provider Integration Gaps

- No real third-party HTTP provider client integration is implemented yet.
- `EmailDispatcher` currently simulates provider delivery with logging only.
- Provider-specific retry classification is not implemented (`408`, `425`, `429`, `5xx` retryable; other `4xx` non-retryable).
- Provider timeout handling (2-3s target) is not implemented.
- Shared HTTP client lifecycle resource for provider calls is not implemented.

### 3 Dependency Injection Gaps

- `get_email_dispatcher` dependency is not exposed in `dependencies.py`.
- `get_email_provider_client` dependency is not exposed in `dependencies.py`.

### 4 Observability Gaps

- Structured logging with request/correlation IDs is not implemented.
- Dispatch metrics are not implemented:
  - dispatch attempts
  - dispatch successes
  - dispatch terminal failures
  - provider latency
  - provider error rate
  - undelivered activation code count (`sent_at IS NULL`)

### 5 Periodic Cleanup Gaps

- Hourly `registration_cleanup` job is not implemented.
- Pending-user retention cleanup is not implemented.
- Stale activation code cleanup is not implemented.
