import structlog
from typing import Dict, Any, List, Optional
from ..ports.store_ports import SwarmStateStore

logger = structlog.get_logger()


class FactGovernanceService:
    """
    Extracts and manages session-wide shared facts (Doc 03).
    Ensures agents don't repeat questions and share common context.
    Uses optimistic versioning for concurrent-safe swarm state updates.
    """
    def __init__(self, swarm_state_store: SwarmStateStore):
        self.swarm_state_store = swarm_state_store

    async def update_facts(self, session_id: str, last_result: Dict[str, Any]):
        """
        Extracts facts from the agent's result and merges them into SwarmState.
        Uses CAS (versioned write) to prevent lost updates under concurrency.
        """
        if not last_result or last_result.get("status") != "COMPLETED":
            return

        payload = last_result.get("payload", {})
        agent_key = last_result.get("agent_key", "unknown")

        raw_data = payload.get("data", {})
        new_facts = self._extract_facts(raw_data, payload, agent_key)
        if not new_facts:
            return

        for attempt in range(3):
            current_state, version = await self.swarm_state_store.get_swarm_state_with_version(session_id)
            facts = current_state.get("facts", {})
            facts.update(new_facts)
            current_state["facts"] = facts
            current_state["last_updated_by"] = agent_key
            try:
                await self.swarm_state_store.save_swarm_state(session_id, current_state, expected_version=version)
                logger.info("swarm_facts_updated", session_id=session_id, agent=agent_key, facts_count=len(new_facts))
                return
            except ValueError:
                if attempt < 2:
                    continue
                logger.warning("swarm_facts_update_conflict", session_id=session_id, agent=agent_key)

    def _extract_facts(self, raw_data: Any, payload: Dict[str, Any], agent_key: str) -> Dict[str, Any]:
        facts: Dict[str, Any] = {}
        if isinstance(raw_data, dict):
            for key, value in raw_data.items():
                if isinstance(value, (str, int, float, bool, list, dict)):
                    facts[key] = value
        if payload.get("answer"):
            facts[f"last_answer_{agent_key}"] = payload.get("answer")
        return facts
