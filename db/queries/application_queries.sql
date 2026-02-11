-- Application SQL catalog derived from docs/architecture.md
-- Target DB: MySQL 8.4
-- Placeholder style uses %s (compatible with asyncmy/aiomysql drivers)

-- ============================================================================
-- 1) REGISTRATION FLOW
-- ============================================================================

-- 1.1 Lock by email (used to decide create vs pending reset vs active conflict)
SELECT id, email, password_hash, status, created_at, activated_at
FROM users
WHERE email = %s
FOR UPDATE;

-- 1.2 Create a new pending user
INSERT INTO users (email, password_hash, status)
VALUES (%s, %s, 'PENDING');

-- 1.3 Replace password for existing pending user
UPDATE users
SET password_hash = %s
WHERE id = %s
  AND status = 'PENDING';

-- 1.4 Create activation code (sent_at stays NULL until email delivery succeeds)
INSERT INTO activation_codes (user_id, code)
VALUES (%s, %s);

-- 1.5 Insert outbox event for async email delivery
-- payload example:
-- {
--   "user_id": 123,
--   "email": "user@example.com",
--   "activation_code_id": 456,
--   "code": "1234"
-- }
INSERT INTO outbox_events (event_type, payload, status, next_attempt_at)
VALUES ('activation_code_email_requested', CAST(%s AS JSON), 'PENDING', CURRENT_TIMESTAMP(6));

-- 1.6 Registration response fetch (optional)
SELECT id, email, status
FROM users
WHERE id = %s;


-- ============================================================================
-- 2) ACTIVATION FLOW
-- ============================================================================

-- 2.1 Load + lock user by email for credential verification and status transition
SELECT id, email, password_hash, status, activated_at
FROM users
WHERE email = %s
FOR UPDATE;

-- 2.2 Load + lock most recent delivered and unused code
SELECT id, user_id, code, sent_at, used_at, attempt_count, created_at
FROM activation_codes
WHERE user_id = %s
  AND sent_at IS NOT NULL
  AND used_at IS NULL
ORDER BY created_at DESC, id DESC
LIMIT 1
FOR UPDATE;

-- 2.3 Increment attempts when code check fails
UPDATE activation_codes
SET attempt_count = attempt_count + 1
WHERE id = %s;

-- 2.4 Mark code as used (successful activation)
UPDATE activation_codes
SET used_at = CURRENT_TIMESTAMP(6)
WHERE id = %s
  AND used_at IS NULL;

-- 2.5 Activate account (idempotent guard)
UPDATE users
SET status = 'ACTIVE',
    activated_at = CURRENT_TIMESTAMP(6)
WHERE id = %s
  AND status = 'PENDING';

-- 2.6 When current code is expired, create a fresh code + outbox event
INSERT INTO activation_codes (user_id, code)
VALUES (%s, %s);

INSERT INTO outbox_events (event_type, payload, status, next_attempt_at)
VALUES ('activation_code_email_requested', CAST(%s AS JSON), 'PENDING', CURRENT_TIMESTAMP(6));

-- 2.7 Optional read used by domain checks (if not using query 2.2)
SELECT id, user_id, code, sent_at, used_at, attempt_count, created_at
FROM activation_codes
WHERE user_id = %s
ORDER BY created_at DESC, id DESC
LIMIT 1
FOR UPDATE;


-- ============================================================================
-- 3) OUTBOX CLAIM + PROCESSING
-- ============================================================================

-- 3.1 Reclaim stale in-progress rows (worker crash recovery)
UPDATE outbox_events
SET status = 'PENDING',
    locked_by = NULL,
    locked_at = NULL,
    next_attempt_at = CURRENT_TIMESTAMP(6),
    last_error = COALESCE(last_error, 'reclaimed stale processing lock')
WHERE status = 'PROCESSING'
  AND locked_at IS NOT NULL
  AND locked_at < (CURRENT_TIMESTAMP(6) - INTERVAL %s SECOND);

-- 3.2 Claim a batch of due events (run in transaction)
SELECT id
FROM outbox_events
WHERE status = 'PENDING'
  AND next_attempt_at <= CURRENT_TIMESTAMP(6)
ORDER BY id
LIMIT %s
FOR UPDATE SKIP LOCKED;

-- 3.3 Mark selected rows as PROCESSING (build IN list dynamically)
UPDATE outbox_events
SET status = 'PROCESSING',
    locked_by = %s,
    locked_at = CURRENT_TIMESTAMP(6)
WHERE id IN (/* dynamic ids */)
  AND status = 'PENDING';

-- 3.4 Load claimed events for execution
SELECT id, event_type, payload, attempts, created_at
FROM outbox_events
WHERE status = 'PROCESSING'
  AND locked_by = %s
ORDER BY id;


-- ============================================================================
-- 4) OUTBOX RESULT HANDLING
-- ============================================================================

-- 4.1 On email delivery success, set sent_at only if still unset
UPDATE activation_codes
SET sent_at = CURRENT_TIMESTAMP(6)
WHERE id = %s
  AND sent_at IS NULL;

-- 4.2 Mark event done
UPDATE outbox_events
SET status = 'DONE',
    processed_at = CURRENT_TIMESTAMP(6),
    locked_by = NULL,
    locked_at = NULL,
    last_error = NULL
WHERE id = %s
  AND status = 'PROCESSING';

-- 4.3 Retryable failure: increment attempts and schedule next attempt
UPDATE outbox_events
SET status = 'PENDING',
    attempts = attempts + 1,
    next_attempt_at = DATE_ADD(CURRENT_TIMESTAMP(6), INTERVAL %s SECOND),
    last_error = %s,
    locked_by = NULL,
    locked_at = NULL
WHERE id = %s
  AND status = 'PROCESSING';

-- 4.4 Terminal failure (dead-letter)
UPDATE outbox_events
SET status = 'FAILED',
    attempts = attempts + 1,
    processed_at = CURRENT_TIMESTAMP(6),
    last_error = %s,
    locked_by = NULL,
    locked_at = NULL
WHERE id = %s
  AND status = 'PROCESSING';


-- ============================================================================
-- 5) CLEANUP JOBS (registration_cleanup hourly)
-- ============================================================================

-- 5.1 Delete abandoned pending users older than retention window (hours)
-- Activation codes are removed by ON DELETE CASCADE.
DELETE FROM users
WHERE status = 'PENDING'
  AND created_at < (CURRENT_TIMESTAMP(6) - INTERVAL %s HOUR);

-- 5.2 Optional explicit cleanup for old activation codes (if you keep users)
DELETE FROM activation_codes
WHERE created_at < (CURRENT_TIMESTAMP(6) - INTERVAL %s HOUR);

-- 5.3 Optional outbox compaction (not required by architecture but operationally useful)
DELETE FROM outbox_events
WHERE status IN ('DONE', 'FAILED')
  AND processed_at IS NOT NULL
  AND processed_at < (CURRENT_TIMESTAMP(6) - INTERVAL %s DAY);


-- ============================================================================
-- 6) OBSERVABILITY / OPERATIONS QUERIES
-- ============================================================================

-- 6.1 Outbox depth by status
SELECT status, COUNT(*) AS total
FROM outbox_events
GROUP BY status;

-- 6.2 Number of due pending events
SELECT COUNT(*) AS due_pending
FROM outbox_events
WHERE status = 'PENDING'
  AND next_attempt_at <= CURRENT_TIMESTAMP(6);

-- 6.3 Processing lag (seconds) for in-progress rows
SELECT id,
       TIMESTAMPDIFF(SECOND, locked_at, CURRENT_TIMESTAMP(6)) AS processing_age_seconds
FROM outbox_events
WHERE status = 'PROCESSING'
  AND locked_at IS NOT NULL
ORDER BY processing_age_seconds DESC;

-- 6.4 Pending accounts not yet delivered code
SELECT u.id, u.email, u.created_at, ac.id AS activation_code_id
FROM users u
JOIN activation_codes ac ON ac.user_id = u.id
WHERE u.status = 'PENDING'
  AND ac.sent_at IS NULL
ORDER BY u.created_at ASC;
