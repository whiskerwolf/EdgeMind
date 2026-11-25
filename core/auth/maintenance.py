"""
EdgeMind Scheduled Database Maintenance CLI.

Safely prunes expired and aged revoked refresh token sessions on a schedule
without disturbing active user sessions, historical analyses, or token reuse
detection windows.

Usage:
    python -m core.auth.maintenance
    python -m core.auth.maintenance --dry-run
    python -m core.auth.maintenance --expired-grace-days 1 --revoked-grace-days 7 --json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from typing import Any, Dict, Optional, Sequence

from core.auth.service import AuthService
from core.config import get_settings
from core.database.connection import close_db, get_session_factory

logger = logging.getLogger("edgemind.maintenance")


async def run_maintenance(
    expired_grace_days: Optional[int] = None,
    revoked_grace_days: Optional[int] = None,
    dry_run: bool = False,
    close_on_exit: bool = False,
) -> Dict[str, Any]:
    """
    Execute scheduled refresh token maintenance against the configured database.

    When no database is configured (`get_session_factory() is None`), returns a
    clean `skipped` summary instead of failing so stateless environments remain healthy.
    Errors sanitize credentials before logging or re-raising.
    """
    settings = get_settings()
    resolved_expired_days = (
        settings.refresh_token_cleanup_grace_days
        if expired_grace_days is None
        else expired_grace_days
    )
    resolved_revoked_days = (
        settings.refresh_token_revoked_grace_days
        if revoked_grace_days is None
        else revoked_grace_days
    )

    if resolved_expired_days < 0 or resolved_revoked_days < 0:
        raise ValueError("Grace days must be non-negative integers.")

    try:
        factory = get_session_factory()
        if factory is None:
            logger.warning(
                "Database session factory unavailable; skipping scheduled token maintenance cleanly."
            )
            return {
                "status": "skipped",
                "reason": "database_not_configured",
                "dry_run": dry_run,
                "deleted_count": 0,
                "eligible_count": 0,
                "expired_grace_days": resolved_expired_days,
                "revoked_grace_days": resolved_revoked_days,
            }

        async with factory() as session:
            try:
                auth_service = AuthService(session)
                summary = await auth_service.cleanup_expired_refresh_tokens(
                    expired_grace_days=resolved_expired_days,
                    revoked_grace_days=resolved_revoked_days,
                    dry_run=dry_run,
                )
                if dry_run:
                    await session.rollback()
                else:
                    await session.commit()
            except Exception as exc:
                await session.rollback()
                sanitized = settings.sanitize_error(str(exc))
                logger.error("Scheduled database maintenance failed: %s", sanitized)
                raise RuntimeError(f"Database maintenance failed: {sanitized}") from exc

        result = {"status": "ok", **summary}
        logger.info(
            "Database maintenance completed status=%s dry_run=%s eligible=%d deleted=%d",
            result["status"],
            result["dry_run"],
            result["eligible_count"],
            result["deleted_count"],
        )
        return result
    finally:
        if close_on_exit:
            await close_db()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run EdgeMind scheduled database token maintenance."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count eligible expired/revoked refresh tokens without deleting any rows.",
    )
    parser.add_argument(
        "--expired-grace-days",
        type=int,
        default=None,
        help="Override grace days after refresh token expiry before pruning (default from settings).",
    )
    parser.add_argument(
        "--revoked-grace-days",
        type=int,
        default=None,
        help="Override retention days for revoked refresh tokens before pruning (default from settings).",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON summary to stdout.",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    """CLI entrypoint for systemd timers, cron jobs, or manual operator invocation."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )

    try:
        result = asyncio.run(
            run_maintenance(
                expired_grace_days=args.expired_grace_days,
                revoked_grace_days=args.revoked_grace_days,
                dry_run=args.dry_run,
                close_on_exit=True,
            )
        )
    except Exception as exc:
        settings = get_settings()
        sanitized = settings.sanitize_error(str(exc))
        if args.json:
            print(json.dumps({"status": "error", "error": sanitized}), file=sys.stderr)
        else:
            print(f"ERROR: {sanitized}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result))
    else:
        print(
            f"Maintenance {result['status']}: dry_run={result['dry_run']} "
            f"eligible={result['eligible_count']} deleted={result['deleted_count']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
