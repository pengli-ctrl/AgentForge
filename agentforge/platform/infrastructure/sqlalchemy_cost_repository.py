from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from agentforge.platform.domain.cost import CostRecord
from agentforge.platform.infrastructure.db.models import CostRecordRecord


class SQLAlchemyCostRepository:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def save(self, record: CostRecord) -> None:
        async with self._session_factory() as session:
            session.add(
                CostRecordRecord(
                    tenant_id=record.tenant_id,
                    task_id=record.task_id,
                    model_name=record.model_name,
                    provider=record.provider,
                    input_tokens=record.input_tokens,
                    output_tokens=record.output_tokens,
                    amount=record.amount,
                    created_at=record.created_at,
                )
            )
            await session.commit()

    async def total_for_tenant(self, tenant_id: str) -> float:
        async with self._session_factory() as session:
            statement = select(func.coalesce(func.sum(CostRecordRecord.amount), 0.0)).where(
                CostRecordRecord.tenant_id == tenant_id
            )
            return float((await session.execute(statement)).scalar_one())

    async def summary_for_tenant(self, tenant_id: str) -> dict:
        statement = (
            select(
                CostRecordRecord.model_name,
                CostRecordRecord.provider,
                func.count(CostRecordRecord.id),
                func.coalesce(func.sum(CostRecordRecord.input_tokens), 0),
                func.coalesce(func.sum(CostRecordRecord.output_tokens), 0),
                func.coalesce(func.sum(CostRecordRecord.amount), 0.0),
            )
            .where(CostRecordRecord.tenant_id == tenant_id)
            .group_by(CostRecordRecord.model_name, CostRecordRecord.provider)
        )
        async with self._session_factory() as session:
            rows = (await session.execute(statement)).all()
        by_model = [
            {
                "model_name": row[0],
                "provider": row[1],
                "request_count": int(row[2]),
                "input_tokens": int(row[3]),
                "output_tokens": int(row[4]),
                "amount": float(row[5]),
            }
            for row in rows
        ]
        return {
            "tenant_id": tenant_id,
            "request_count": sum(item["request_count"] for item in by_model),
            "input_tokens": sum(item["input_tokens"] for item in by_model),
            "output_tokens": sum(item["output_tokens"] for item in by_model),
            "total_amount": sum(item["amount"] for item in by_model),
            "by_model": by_model,
        }
