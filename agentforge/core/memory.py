"""
Three-tier Memory system — runtime layer core component.

Architecture analogy (CPU hierarchy):
    WorkingMemory    = CPU Registers   → fastest, smallest, current context only
    ShortTermMemory  = RAM             -> session-scoped, cleared on session end
    LongTermMemory   = Disk (FAISS+BM25) -> persistent knowledge base

Why three tiers?
    LLM Agents need different memory horizons. A single dict is too simple —
    there's no distinction between "what we're doing right now" and "what we
    learned last week". The three-tier model mirrors how human cognition and
    computer architecture both handle memory: fast-local for hot data,
    slower-remote for cold data, with explicit promotion/demotion paths.

Integration:
    MemoryManager composes all three tiers. BaseAgent uses MemoryManager to
    read/write memory. DAG nodes can share short-term memory via ContextStore.
"""

import asyncio
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class MemoryConfig:
    """Per-agent memory configuration. Each Agent declares which tiers it needs."""

    enable_working: bool = True
    enable_short_term: bool = True
    enable_long_term: bool = False
    max_working_items: int = 20  # Small: current turn context only
    max_short_term_items: int = 200  # Medium: full session history
    max_long_term_items: int = 50000  # Large: persistent knowledge base
    long_term_collection: str = "default"  # FAISS collection name


class WorkingMemory:
    """
    CPU Register analogy — fastest, smallest, current context only.

    Stores the immediate context for a single Agent execution turn:
    current input, intermediate results, tool outputs. Cleared after
    each execute() call returns.

    Why OrderedDict? Maintains insertion order for predictable iteration,
    and supports O(1) move-to-end for LRU-style access tracking.
    """

    def __init__(self, max_items: int = 20):
        self._store: OrderedDict[str, Any] = OrderedDict()
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def write(self, key: str, value: Any) -> None:
        """Write a key-value pair. Evicts oldest if at capacity."""
        async with self._lock:
            if key in self._store:
                self._store.move_to_end(key)
            self._store[key] = value
            # Evict oldest entries if over capacity
            while len(self._store) > self._max_items:
                self._store.popitem(last=False)

    async def read(self, key: str) -> Optional[Any]:
        """Read a value. Marks as recently accessed (LRU tracking)."""
        async with self._lock:
            if key not in self._store:
                return None
            self._store.move_to_end(key)
            return self._store[key]

    async def get_all(self) -> dict[str, Any]:
        """Snapshot all current working memory entries."""
        async with self._lock:
            return dict(self._store)

    async def clear(self) -> None:
        """Clear all working memory. Called after Agent execute() completes."""
        async with self._lock:
            self._store.clear()

    @property
    def size(self) -> int:
        return len(self._store)


class ShortTermMemory:
    """
    RAM analogy — session-scoped, cross-turn retention, cleared on session end.

    Stores conversation history, intermediate agent outputs, and user
    preferences within a single session. Survives across multiple turns
    but is volatile — lost when session ends.

    Why separate from WorkingMemory?
        Working memory is per-execution (cleared after each Agent call).
        Short-term memory is per-session (survives across multiple Agent calls
        within the same conversation). This distinction prevents context
        pollution while maintaining conversational continuity.
    """

    def __init__(self, session_id: str, max_items: int = 200):
        self._session_id = session_id
        self._store: dict[str, dict] = {}  # key → {value, created_at, last_accessed}
        self._max_items = max_items
        self._lock = asyncio.Lock()

    async def write(self, key: str, value: Any) -> None:
        """Store a value with metadata. Overwrites existing entries."""
        async with self._lock:
            now = time.time()
            self._store[key] = {
                "value": value,
                "created_at": now,
                "last_accessed": now,
                "access_count": 0,
            }
            # Evict least-recently-accessed if over capacity
            if len(self._store) > self._max_items:
                await self._evict_lru()

    async def read(self, key: str) -> Optional[Any]:
        """Read a value. Updates access metadata."""
        async with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            entry["last_accessed"] = time.time()
            entry["access_count"] += 1
            return entry["value"]

    async def delete(self, key: str) -> bool:
        """Remove a key. Returns True if key existed."""
        async with self._lock:
            return self._store.pop(key, None) is not None

    async def _evict_lru(self) -> None:
        """Evict the least-recently-accessed entry. Called under lock."""
        if not self._store:
            return
        lru_key = min(self._store, key=lambda k: self._store[k]["last_accessed"])
        del self._store[lru_key]

    async def clear(self) -> None:
        """Clear entire session memory. Called on session end."""
        async with self._lock:
            self._store.clear()

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def size(self) -> int:
        return len(self._store)


class LongTermMemory:
    """
    Disk analogy (FAISS + BM25) — persistent vector-indexed knowledge base.

    Provides semantic search over stored knowledge using embedding similarity.
    In production, this wraps FAISS for dense retrieval and BM25 for sparse
    retrieval, with hybrid scoring (0.7 * dense + 0.3 * sparse).

    Current implementation uses in-memory vector storage for portability.
    Production deployments should replace _vectors with a persistent FAISS index
    and optionally add a BM25 index (e.g., rank_bm25 library).

    Why hybrid retrieval?
        Dense (embedding) search excels at semantic similarity but can miss
        exact keyword matches. Sparse (BM25) search excels at keyword matches
        but misses synonyms. Combining both gives robust retrieval.
        The 0.7/0.3 weighting favors semantic similarity as it's generally
        more useful for Agent knowledge retrieval.
    """

    def __init__(self, collection: str = "default", max_items: int = 50000):
        self._collection = collection
        self._max_items = max_items
        # In-memory storage; production: replace with FAISS index file
        self._vectors: dict[str, dict] = {}  # key → {embedding, metadata, text}
        self._lock = asyncio.Lock()

    async def store(
        self,
        key: str,
        text: str,
        embedding: list[float],
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Store a document with its embedding for later retrieval.

        Args:
            key: Unique identifier for this document.
            text: Original text content (for BM25 and display).
            embedding: Dense vector representation (from embedding model).
            metadata: Optional metadata (source, timestamp, tags, etc.).
        """
        async with self._lock:
            self._vectors[key] = {
                "text": text,
                "embedding": embedding,
                "metadata": metadata or {},
                "created_at": time.time(),
            }

    async def search(
        self,
        query_embedding: list[float],
        top_k: int = 5,
        min_similarity: float = 0.7,
    ) -> list[dict]:
        """
        Search for similar documents using cosine similarity.

        Args:
            query_embedding: Query vector from embedding model.
            top_k: Maximum number of results.
            min_similarity: Minimum cosine similarity threshold.

        Returns:
            List of {key, text, score, metadata} sorted by score descending.
        """
        async with self._lock:
            results = []
            for key, doc in self._vectors.items():
                score = self._cosine_similarity(query_embedding, doc["embedding"])
                if score >= min_similarity:
                    results.append(
                        {
                            "key": key,
                            "text": doc["text"],
                            "score": score,
                            "metadata": doc["metadata"],
                        }
                    )

        # Sort by score descending, return top_k
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    async def delete(self, key: str) -> bool:
        """Remove a document from the knowledge base."""
        async with self._lock:
            return self._vectors.pop(key, None) is not None

    @staticmethod
    def _cosine_similarity(v1: list[float], v2: list[float]) -> float:
        """Compute cosine similarity between two vectors."""
        if len(v1) != len(v2) or not v1:
            return 0.0
        dot = sum(a * b for a, b in zip(v1, v2))
        norm1 = sum(a * a for a in v1) ** 0.5
        norm2 = sum(b * b for b in v2) ** 0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot / (norm1 * norm2)

    @property
    def size(self) -> int:
        return len(self._vectors)


class MemoryManager:
    """
    Composes three memory tiers into a unified interface.

    BaseAgent instantiates one MemoryManager per agent, configured via
    MemoryConfig. The manager routes read/write/search calls to the
    appropriate tier based on the `level` parameter.

    Cross-tier operations:
        - search() queries long-term memory (only tier with vector index)
        - promote() moves data from working → short-term (explicit)
        - No automatic promotion to long-term (requires explicit embedding)
    """

    def __init__(
        self,
        config: MemoryConfig,
        session_id: str = "default",
    ):
        self._config = config
        self.working = (
            WorkingMemory(max_items=config.max_working_items) if config.enable_working else None
        )
        self.short_term = (
            ShortTermMemory(session_id, max_items=config.max_short_term_items)
            if config.enable_short_term
            else None
        )
        self.long_term = (
            LongTermMemory(config.long_term_collection, max_items=config.max_long_term_items)
            if config.enable_long_term
            else None
        )

    async def read(self, level: str, key: str) -> Optional[Any]:
        """
        Read from a specific memory tier.

        Args:
            level: "working", "short_term", or "long_term"
            key: The key to look up.
        """
        if level == "working" and self.working:
            return await self.working.read(key)
        elif level == "short_term" and self.short_term:
            return await self.short_term.read(key)
        elif level == "long_term":
            # Long-term requires vector search, not direct key lookup
            raise ValueError("Use search() for long-term memory retrieval")
        return None

    async def write(self, level: str, key: str, value: Any, **kwargs) -> None:
        """
        Write to a specific memory tier.

        Args:
            level: "working", "short_term", or "long_term"
            key: The key to store under.
            value: The value to store.
            **kwargs: For long_term, requires `embedding` and `text`.
        """
        if level == "working" and self.working:
            await self.working.write(key, value)
        elif level == "short_term" and self.short_term:
            await self.short_term.write(key, value)
        elif level == "long_term" and self.long_term:
            await self.long_term.store(
                key=key,
                text=kwargs.get("text", str(value)),
                embedding=kwargs.get("embedding", []),
                metadata=kwargs.get("metadata"),
            )
        else:
            raise ValueError(f"Memory tier '{level}' is not enabled")

    async def search(self, query_embedding: list[float], top_k: int = 5) -> list[dict]:
        """
        Semantic search across long-term memory.
        Returns list of {key, text, score, metadata}.
        """
        if not self.long_term:
            return []
        return await self.long_term.search(query_embedding, top_k=top_k)

    async def clear_working(self) -> None:
        """Clear working memory. Called after each Agent execution."""
        if self.working:
            await self.working.clear()

    async def clear_session(self) -> None:
        """Clear all session-scoped memory. Called on session end."""
        if self.working:
            await self.working.clear()
        if self.short_term:
            await self.short_term.clear()
