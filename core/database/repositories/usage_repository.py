"""
Repository for AI Token Usage and API Cost Monitoring.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal
import logging
from typing import Any, Dict, List, Optional
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from core.cost.models import TokenUsage, UsageSource
from core.database.models.ai_token_usage import AiTokenUsage

logger = logging.getLogger("edgemind.repositories.usage")


class UsageRepository:
    """
    Handles database persistence and aggregated querying for AI token usage and cost accounting.
    Enforces tenant isolation by scoping all queries to authenticated user and/or project IDs.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def record_usage(
        self,
        usage: TokenUsage,
        session_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
    ) -> AiTokenUsage:
        """Persist a single token usage record idempotently scoped to (provider, request_id)."""
        target_session_id = session_id or usage.analysis_session_id
        target_user_id = user_id or usage.user_id
        target_project_id = project_id or usage.project_id
        target_provider = usage.provider or "openai"

        # Idempotency check: if request_id is present, avoid duplicate insertion for (provider, request_id)
        if usage.request_id:
            stmt = select(AiTokenUsage).where(
                AiTokenUsage.provider == target_provider,
                AiTokenUsage.request_id == usage.request_id,
            )
            res = await self.db.execute(stmt)
            existing = res.scalars().first()
            if existing:
                logger.info(
                    "Duplicate usage record skipped for provider=%s, request_id=%s",
                    target_provider,
                    usage.request_id,
                )
                return existing

        entry = AiTokenUsage(
            session_id=target_session_id,
            user_id=target_user_id,
            project_id=target_project_id,
            provider=target_provider,
            model=usage.model or "unknown",
            prompt_tokens=usage.prompt_tokens or 0,
            completion_tokens=usage.completion_tokens or 0,
            total_tokens=usage.total_tokens or ((usage.prompt_tokens or 0) + (usage.completion_tokens or 0)),
            estimated_cost_usd=usage.estimated_cost_usd,
            pricing_version=usage.pricing_version,
            usage_source=usage.usage_source.value if hasattr(usage.usage_source, "value") else str(usage.usage_source),
            request_id=usage.request_id,
        )
        try:
            async with self.db.begin_nested():
                self.db.add(entry)
                await self.db.flush()
            return entry
        except IntegrityError:
            # Handle race condition: concurrent insertion committed same (provider, request_id)
            if usage.request_id:
                stmt = select(AiTokenUsage).where(
                    AiTokenUsage.provider == target_provider,
                    AiTokenUsage.request_id == usage.request_id,
                )
                res = await self.db.execute(stmt)
                existing = res.scalars().first()
                if existing:
                    logger.info(
                        "Concurrent duplicate usage record caught for provider=%s, request_id=%s",
                        target_provider,
                        usage.request_id,
                    )
                    return existing
            raise

    async def record_usages_batch(
        self,
        usages: List[TokenUsage],
        session_id: Optional[uuid.UUID] = None,
        user_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
    ) -> List[AiTokenUsage]:
        """Persist a collection of token usage records within an analysis session with in-batch deduplication."""
        records: List[AiTokenUsage] = []
        seen_in_batch = set()
        for usage in usages:
            prov = usage.provider or "openai"
            if usage.request_id:
                key = (prov, usage.request_id)
                if key in seen_in_batch:
                    logger.info(
                        "Duplicate in-batch usage record skipped for provider=%s, request_id=%s",
                        prov,
                        usage.request_id,
                    )
                    continue
                seen_in_batch.add(key)
            rec = await self.record_usage(
                usage=usage,
                session_id=session_id,
                user_id=user_id,
                project_id=project_id,
            )
            records.append(rec)
        return records

    async def get_by_session_id(
        self,
        session_id: uuid.UUID,
        user_id: Optional[uuid.UUID] = None,
        is_admin: bool = False,
    ) -> List[AiTokenUsage]:
        """Retrieve token usage records for a specific session with tenant isolation."""
        stmt = select(AiTokenUsage).where(AiTokenUsage.session_id == session_id)
        if not is_admin and user_id is not None:
            stmt = stmt.where(AiTokenUsage.user_id == user_id)
        stmt = stmt.order_by(AiTokenUsage.created_at.asc())
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_summary(
        self,
        user_id: Optional[uuid.UUID] = None,
        project_id: Optional[uuid.UUID] = None,
        period: str = "month",
        is_admin: bool = False,
    ) -> Dict[str, Any]:
        """
        Aggregate token usage and costs across sessions with tenant isolation.

        Periods:
            - "day": last 24 hours
            - "month": last 30 days
            - "all": all recorded history
        """
        stmt = select(AiTokenUsage)
        if not is_admin:
            if user_id is None:
                # Unauthenticated users cannot view general usage
                return {
                    "total_prompt_tokens": 0,
                    "total_completion_tokens": 0,
                    "total_tokens": 0,
                    "total_estimated_cost_usd": None,
                    "requests_count": 0,
                    "period": period,
                    "by_model": {},
                    "by_source": {},
                    "is_estimated_cost_known": False,
                }
            stmt = stmt.where(AiTokenUsage.user_id == user_id)

        if project_id is not None:
            stmt = stmt.where(AiTokenUsage.project_id == project_id)

        now = datetime.now(timezone.utc)
        if period == "day":
            since = now - timedelta(days=1)
            stmt = stmt.where(AiTokenUsage.created_at >= since)
        elif period == "month":
            since = now - timedelta(days=30)
            stmt = stmt.where(AiTokenUsage.created_at >= since)

        result = await self.db.execute(stmt)
        records = list(result.scalars().all())

        total_prompt = 0
        total_completion = 0
        total_tokens = 0
        total_cost_dec = Decimal("0.0")
        has_any_cost = False
        by_model: Dict[str, Dict[str, Any]] = {}
        by_source: Dict[str, int] = {}

        for r in records:
            total_prompt += r.prompt_tokens
            total_completion += r.completion_tokens
            total_tokens += r.total_tokens

            if r.estimated_cost_usd is not None:
                has_any_cost = True
                total_cost_dec += Decimal(str(r.estimated_cost_usd))

            m = r.model or "unknown"
            if m not in by_model:
                by_model[m] = {
                    "model": m,
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0,
                    "requests_count": 0,
                    "estimated_cost_usd": None,
                    "is_estimated_cost_known": False,
                }
            by_model[m]["prompt_tokens"] += r.prompt_tokens
            by_model[m]["completion_tokens"] += r.completion_tokens
            by_model[m]["total_tokens"] += r.total_tokens
            by_model[m]["requests_count"] += 1
            if r.estimated_cost_usd is not None:
                current_cost = by_model[m]["estimated_cost_usd"] or Decimal("0.0")
                by_model[m]["estimated_cost_usd"] = current_cost + Decimal(str(r.estimated_cost_usd))
                by_model[m]["is_estimated_cost_known"] = True

            src = r.usage_source or "UNKNOWN"
            by_source[src] = by_source.get(src, 0) + 1

        return {
            "total_prompt_tokens": total_prompt,
            "total_completion_tokens": total_completion,
            "total_tokens": total_tokens,
            "total_estimated_cost_usd": total_cost_dec if has_any_cost else None,
            "requests_count": len(records),
            "period": period,
            "by_model": by_model,
            "by_source": by_source,
            "is_estimated_cost_known": has_any_cost,
        }
