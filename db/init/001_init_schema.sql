CREATE TABLE IF NOT EXISTS users (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  email VARCHAR(320) NOT NULL,
  password_hash VARCHAR(255) NOT NULL,
  status ENUM('PENDING', 'ACTIVE') NOT NULL DEFAULT 'PENDING',
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  activated_at DATETIME(6) NULL,
  UNIQUE KEY uq_users_email (email)
);

CREATE TABLE IF NOT EXISTS activation_codes (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  user_id BIGINT NOT NULL,
  code CHAR(4) NOT NULL,
  sent_at DATETIME(6) NULL,
  used_at DATETIME(6) NULL,
  attempt_count INT NOT NULL DEFAULT 0,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  CONSTRAINT fk_activation_codes_user_id
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_activation_codes_user_created (user_id, created_at)
);

CREATE TABLE IF NOT EXISTS outbox_events (
  id BIGINT AUTO_INCREMENT PRIMARY KEY,
  event_type VARCHAR(100) NOT NULL,
  payload JSON NOT NULL,
  status ENUM('PENDING', 'PROCESSING', 'DONE', 'FAILED') NOT NULL DEFAULT 'PENDING',
  attempts INT NOT NULL DEFAULT 0,
  next_attempt_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  last_error VARCHAR(500) NULL,
  locked_by VARCHAR(100) NULL,
  locked_at DATETIME(6) NULL,
  created_at DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  processed_at DATETIME(6) NULL,
  INDEX idx_outbox_status_next_attempt (status, next_attempt_at),
  INDEX idx_outbox_locked_at (locked_at)
);
