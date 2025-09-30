from __future__ import annotations

from datetime import datetime, timedelta, timezone

from agentforge.platform.domain.cost import CostRecord


class MemoryCostRepository:
    def __init__(self) -> None:
        self.records: list[CostRecord] = []

    async def save(self, record: CostRecord) -> None:
        self.records.append(record)

    async def total_for_tenant(self, tenant_id: str) -> float:
        return sum(record.amount for record in self.records if record.tenant_id == tenant_id)

    async def daily_summary(self, tenant_id: str, days: int = 30) -> list[dict]:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        bucket: dict[str, dict] = {}
        for record in self.records:
            if record.tenant_id != tenant_id:
                continue
            if record.created_at < cutoff:
                continue
            day = record.created_at.date().isoformat()
            entry = bucket.setdefault(
                day,
                {
                    "date": day,
                    "request_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "amount": 0.0,
                },
            )
            entry["request_count"] += 1
            entry["input_tokens"] += record.input_tokens
            entry["output_tokens"] += record.output_tokens
            entry["amount"] += record.amount
        return [bucket[key] for key in sorted(bucket)]

    async def list_tenants(self) -> list[str]:
        seen: dict[str, None] = {}
        for record in self.records:
            seen.setdefault(record.tenant_id, None)
        return list(seen.keys())

    async def summary_for_tenant(self, tenant_id: str) -> dict:
        records = [record for record in self.records if record.tenant_id == tenant_id]
        by_model: dict[tuple[str, str], dict] = {}
        for record in records:
            key = (record.model_name, record.provider)
            summary = by_model.setdefault(
                key,
                {
                    "model_name": record.model_name,
                    "provider": record.provider,
                    "request_count": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "amount": 0.0,
                },
            )
            summary["request_count"] += 1
            summary["input_tokens"] += record.input_tokens
            summary["output_tokens"] += record.output_tokens
            summary["amount"] += record.amount
        return {
            "tenant_id": tenant_id,
            "request_count": len(records),
            "input_tokens": sum(record.input_tokens for record in records),
            "output_tokens": sum(record.output_tokens for record in records),
            "total_amount": sum(record.amount for record in records),
            "by_model": list(by_model.values()),
        }
