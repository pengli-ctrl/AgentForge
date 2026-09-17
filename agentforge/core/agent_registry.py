"""
Agent Registry — hot-pluggable registration for 12+ Agent types.

Adding a new Agent requires exactly 3 steps:
    1. Inherit BaseAgent
    2. Implement execute()
    3. Register with AgentRegistry.register()

No modification to DAG engine code is needed. The registry acts as a
service locator — the DAG engine looks up agents by name at execution time.

Design rationale:
    Why a registry instead of direct instantiation?
    1. Hot-plug: add/remove agents at runtime without restarting
    2. Testability: swap real agents with mocks in tests
    3. Decoupling: DAG definition only references agent names, not classes
    4. Discovery: list_agents() provides runtime introspection
"""

import logging
from typing import Optional, Type

from agentforge.core.agent import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    """
    Singleton-style registry mapping agent names to their classes/instances.

    Supports both class registration (lazy instantiation) and instance
    registration (pre-configured agents). Thread-safe via asyncio.Lock
    for concurrent DAG node lookups.

    Usage:
        # Class registration (lazy)
        registry.register("classifier", ClassifierAgent)
        agent = await registry.get("classifier")  # instantiated on first call

        # Instance registration (eager)
        agent_instance = ClassifierAgent(name="classifier_v2")
        registry.register_instance("classifier_v2", agent_instance)
    """

    def __init__(self):
        self._classes: dict[str, Type[BaseAgent]] = {}
        self._instances: dict[str, BaseAgent] = {}
        self._metadata: dict[str, dict] = {}  # agent_name → {registered_at, version, ...}
        import asyncio

        self._lock = asyncio.Lock()

    async def register(
        self,
        name: str,
        agent_class: Type[BaseAgent],
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Register an Agent class by name. Instantiated lazily on first get().

        Args:
            name: Unique agent identifier (e.g., "classifier", "planner").
            agent_class: Must be a subclass of BaseAgent.
            metadata: Optional metadata (version, description, etc.).

        Raises:
            ValueError: If agent_class is not a BaseAgent subclass.
            KeyError: If name is already registered.
        """
        if not issubclass(agent_class, BaseAgent):
            raise ValueError(
                f"Cannot register '{name}': {agent_class.__name__} "
                f"is not a subclass of BaseAgent"
            )

        async with self._lock:
            if name in self._classes or name in self._instances:
                raise KeyError(f"Agent '{name}' is already registered")

            self._classes[name] = agent_class
            self._metadata[name] = metadata or {}
            logger.info("Registered agent class: %s → %s", name, agent_class.__name__)

    async def register_instance(
        self,
        name: str,
        agent: BaseAgent,
        metadata: Optional[dict] = None,
    ) -> None:
        """
        Register a pre-configured Agent instance.

        Use this when you need custom initialization (specific memory config,
        tools, etc.) before registration.
        """
        if not isinstance(agent, BaseAgent):
            raise ValueError(f"Cannot register '{name}': instance is not a BaseAgent")

        async with self._lock:
            if name in self._classes or name in self._instances:
                raise KeyError(f"Agent '{name}' is already registered")

            self._instances[name] = agent
            self._metadata[name] = metadata or {}
            logger.info("Registered agent instance: %s", name)

    async def get(self, name: str) -> BaseAgent:
        """
        Get an Agent instance by name. Creates from class if not yet instantiated.

        Args:
            name: The registered agent name.

        Returns:
            BaseAgent instance ready for execution.

        Raises:
            KeyError: If name is not registered.
        """
        async with self._lock:
            # Already instantiated?
            if name in self._instances:
                return self._instances[name]

            # Registered as class? Instantiate now (lazy init).
            if name in self._classes:
                agent_class = self._classes[name]
                instance = agent_class(name=name)
                self._instances[name] = instance
                logger.info("Lazy-initialized agent: %s", name)
                return instance

            raise KeyError(f"Agent '{name}' is not registered")

    async def unregister(self, name: str) -> bool:
        """
        Remove an agent from the registry. Supports hot-unplug.

        Returns True if agent was found and removed, False otherwise.
        Warning: if the agent is currently running in a DAG, this may
        cause that DAG execution to fail on next node referencing it.
        """
        async with self._lock:
            removed = False
            if name in self._classes:
                del self._classes[name]
                removed = True
            if name in self._instances:
                del self._instances[name]
                removed = True
            if name in self._metadata:
                del self._metadata[name]
            if removed:
                logger.info("Unregistered agent: %s", name)
            return removed

    def list_agents(self) -> list[str]:
        """List all registered agent names (both classes and instances)."""
        return sorted(set(self._classes.keys()) | set(self._instances.keys()))

    def get_agent_info(self, name: str) -> Optional[dict]:
        """Get metadata and status for a specific agent."""
        if name not in self._metadata and name not in self._classes:
            return None
        info = dict(self._metadata.get(name, {}))
        if name in self._instances:
            info["status"] = self._instances[name].stats
        elif name in self._classes:
            info["status"] = "class_registered"
            info["class"] = self._classes[name].__name__
        return info

    async def get_all_stats(self) -> dict[str, dict]:
        """Get execution stats for all instantiated agents."""
        stats = {}
        for name, agent in self._instances.items():
            stats[name] = agent.stats
        return stats

    async def reset_all(self) -> None:
        """Reset all agents to IDLE state. Used for system recovery."""
        for agent in self._instances.values():
            agent.reset()
        logger.info("Reset all %d agents to IDLE", len(self._instances))

    @property
    def count(self) -> int:
        """Total number of registered agents (unique names)."""
        return len(set(self._classes.keys()) | set(self._instances.keys()))
