# Implementation Gaps (Current Repo Status)

This section tracks architecture items that are documented but not implemented yet in the current codebase.

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
