from __future__ import annotations

import argparse
import asyncio
import json

from agentforge.platform.application.outbox_admin_service import OutboxAdminService
from agentforge.platform.infrastructure.db.base import create_session_factory
from agentforge.platform.infrastructure.outbox_store import SQLAlchemyOutboxStore
from agentforge.platform.settings import get_settings


async def run(args: argparse.Namespace) -> int:
    settings = get_settings()
    store = SQLAlchemyOutboxStore(create_session_factory(settings.database_url))
    service = OutboxAdminService(store)
    if args.command == "list":
        print(json.dumps(await service.list_failed(limit=args.limit), indent=2))
        return 0
    if args.command == "replay":
        return 0 if await service.replay(args.event_id) else 1
    if args.command == "replay-all":
        print(await service.replay_all(limit=args.limit))
        return 0
    return 2


def main() -> int:
    parser = argparse.ArgumentParser(description="AgentForge Outbox administration")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--limit", type=int, default=100)

    replay_parser = subparsers.add_parser("replay")
    replay_parser.add_argument("event_id")

    replay_all_parser = subparsers.add_parser("replay-all")
    replay_all_parser.add_argument("--limit", type=int, default=100)

    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
