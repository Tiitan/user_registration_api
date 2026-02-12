"""Periodic cleanup script for registration data retention."""

from __future__ import annotations

import argparse
import asyncio
import logging
from dataclasses import dataclass

from api.app.db.pool import create_mysql_pool_with_retry
from api.app.db.transaction import transactional_cursor
from api.app.repositories.activation_codes import ActivationCodeRepository
from api.app.repositories.users import UserRepository

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CleanupResult:
    """Deleted (or matched in dry-run) row counts."""

    pending_users: int
    stale_activation_codes: int
    dry_run: bool


def parse_args() -> argparse.Namespace:
    """Build CLI arguments for cleanup policies."""
    parser = argparse.ArgumentParser(description="Delete abandoned pending users and stale activation codes.")
    parser.add_argument("--pending-user-retention-hours", type=int, default=24, help="Delete pending users older than this many hours (default: 24).")
    parser.add_argument("--activation-code-retention-hours", type=int, default=1, help="Delete activation codes older than this many hours (default: 1).")
    parser.add_argument("--dry-run", action="store_true", help="Show how many rows would be deleted without modifying data.")
    return parser.parse_args()


async def run_cleanup(*, pending_user_retention_hours: int, activation_code_retention_hours: int, dry_run: bool) -> CleanupResult:
    """Execute cleanup queries in a single transaction."""
    if pending_user_retention_hours < 0 or activation_code_retention_hours < 0:
        raise ValueError("Retention hours must be >= 0")

    db_pool = await create_mysql_pool_with_retry()
    try:
        user_repository = UserRepository()
        activation_code_repository = ActivationCodeRepository()
        async with transactional_cursor(db_pool) as cursor:
            if dry_run:
                pending_users = await user_repository.count_stale_pending_users(cursor=cursor, retention_hours=pending_user_retention_hours)
                stale_activation_codes = await activation_code_repository.count_stale_activation_codes(cursor=cursor, retention_hours=activation_code_retention_hours)
            else:
                pending_users = await user_repository.delete_stale_pending_users(cursor=cursor, retention_hours=pending_user_retention_hours)
                stale_activation_codes = await activation_code_repository.delete_stale_activation_codes(cursor=cursor, retention_hours=activation_code_retention_hours)

        return CleanupResult(pending_users=pending_users, stale_activation_codes=stale_activation_codes, dry_run=dry_run)
    finally:
        db_pool.close()
        await db_pool.wait_closed()


async def amain() -> int:
    """Script entrypoint."""
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")

    result = await run_cleanup(pending_user_retention_hours=args.pending_user_retention_hours, activation_code_retention_hours=args.activation_code_retention_hours, dry_run=args.dry_run)

    mode = "DRY-RUN" if result.dry_run else "EXECUTED"
    logger.info("[%s] registration_cleanup pending_users=%s stale_activation_codes=%s", mode, result.pending_users, result.stale_activation_codes)
    return 0


def main() -> None:
    """Run async script and map unhandled errors to non-zero exit."""
    try:
        raise SystemExit(asyncio.run(amain()))
    except Exception:
        logger.exception("registration_cleanup failed")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
