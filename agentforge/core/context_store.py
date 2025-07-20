"""
ContextStore — inter-node data flow store for DAG execution.

Provides shared state between DAG nodes with:
    - Async-safe read/write (asyncio.Lock for parallel node protection)
    - Reference resolution: $ctx.key and $input.key syntax
    - Read isolation: each node sees a consistent snapshot at read time
    - No write conflicts: each node writes to its own output_key

Design choices:
    - Not Redis-based (in-process, same event loop) — DAG execution is single-process
    - asyncio.Lock (not threading.Lock) — all agents run in same event loop
    - $ctx.{key} resolves to another node's output (written via write())
    - $input.{key} resolves to the original request input_data
    - Literal values (no $ prefix) pass through unchanged

This was originally embedded in dag_engine.py. Extracted as a standalone
module because:
    1. PlannerAgent needs to understand ContextStore semantics
    2. Future: persistent ContextStore backed by Redis for multi-process DAGs
    3. Cleaner separation — DAG engine orchestrates, ContextStore stores
"""

import asyncio
import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ContextStore:
    """
    Inter-node data flow store with reference resolution.

    Thread-safe via asyncio.Lock (not thread-safe for cross-thread access,
    but all DAG execution happens within a single event loop).

    Reference syntax:
        $ctx.node_output   → read from store (another node's output)
        $input.field_name  → read from original input_data
        literal_value      → pass through as-is (no $ prefix)
    """

    def __init__(self):
        self._store: dict[str, Any] = {}
        self._input: dict[str, Any] = {}
        self._lock = asyncio.Lock()
        self._access_log: list[dict] = []  # Optional: trace who reads what

    async def initialize(self, input_data: dict) -> None:
        """
        Initialize the store with the original request input.
        Called once before DAG execution begins.

        Args:
            input_data: The original request payload.
        """
        async with self._lock:
            self._input = dict(input_data)
            logger.debug("ContextStore initialized with %d input fields", len(input_data))

    async def write(self, key: str, value: Any) -> None:
        """
        Write a node's output to the store.
        Each node writes to its own output_key — no write conflicts.

        Args:
            key: The output key (usually node_id or explicit output_key).
            value: The node's execution result.
        """
        async with self._lock:
            self._store[key] = value

    async def read(self, key: str) -> Optional[Any]:
        """
        Read a value from the store.

        Args:
            key: The key to look up.

        Returns:
            The stored value, or None if not found.
        """
        async with self._lock:
            return self._store.get(key)

    async def read_with_mapping(self, input_mapping: dict[str, str]) -> dict[str, Any]:
        """
        Resolve input_mapping references to concrete values.

        This is the core data-flow mechanism. Each DAGNode has an input_mapping
        that specifies where its inputs come from. This method resolves those
        references to actual values.

        Example:
            input_mapping = {"query": "$ctx.result", "original": "$input.user_query"}
            → {"query": <value from store["result"]>, "original": <value from input["user_query"]>}

        Reference types:
            $ctx.{key}    → read from self._store (another node's output)
            $input.{key}  → read from self._input (original request data)
            other         → literal pass-through (the value itself)

        Args:
            input_mapping: Dict of {param_name: reference_or_literal}.

        Returns:
            Dict of {param_name: resolved_value}.
        """
        async with self._lock:
            resolved = {}
            for target, ref in input_mapping.items():
                if ref.startswith("$ctx."):
                    ctx_key = ref[5:]  # Strip "$ctx."
                    resolved[target] = self._store.get(ctx_key)
                    if ctx_key not in self._store:
                        logger.debug(
                            "ContextStore: $ctx.%s not found for param '%s'", ctx_key, target
                        )
                elif ref.startswith("$input."):
                    input_key = ref[7:]  # Strip "$input."
                    resolved[target] = self._input.get(input_key)
                    if input_key not in self._input:
                        logger.debug(
                            "ContextStore: $input.%s not found for param '%s'", input_key, target
                        )
                else:
                    # Literal value pass-through
                    resolved[target] = ref
            return resolved

    async def get_all(self) -> dict[str, Any]:
        """
        Get a snapshot of all stored values.
        Used for debugging, tracing, and L3 degradation decisions.

        Returns:
            Copy of the entire store.
        """
        async with self._lock:
            return dict(self._store)

    async def get_input(self) -> dict[str, Any]:
        """
        Get a snapshot of the original input data.

        Returns:
            Copy of the input data.
        """
        async with self._lock:
            return dict(self._input)

    async def has(self, key: str) -> bool:
        """Check if a key exists in the store."""
        async with self._lock:
            return key in self._store

    async def delete(self, key: str) -> bool:
        """
        Delete a key from the store.
        Used for cleanup after a node's output is no longer needed.

        Returns:
            True if key existed and was deleted.
        """
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def clear(self) -> None:
        """Clear all stored values. Called after DAG execution completes."""
        async with self._lock:
            self._store.clear()
            self._access_log.clear()
            logger.debug("ContextStore cleared")

    def size(self) -> int:
        """Number of entries currently in the store (non-async, approximate)."""
        return len(self._store)

    async def log_access(self, node_id: str, keys_read: list[str]) -> None:
        """
        Log which keys a node accessed. Used for tracing and debugging.

        Args:
            node_id: The node that performed the read.
            keys_read: List of keys that were read.
        """
        async with self._lock:
            self._access_log.append(
                {
                    "node_id": node_id,
                    "keys_read": keys_read,
                    "store_size": len(self._store),
                }
            )

    async def get_access_log(self) -> list[dict]:
        """Get the full access log for tracing."""
        async with self._lock:
            return list(self._access_log)
