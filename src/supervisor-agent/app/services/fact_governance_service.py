import structlog
from typing import Dict, Any, List
from ..ports.store_ports import SwarmStateStore

logger = structlog.get_logger()

class FactGovernanceService:
    """
    Extracts and manages session-wide shared facts (Doc 03).
    Ensures agents don't repeat questions and share common context.
    """
    def __init__(self, swarm_state_store: SwarmStateStore):
        self.swarm_state_store = swarm_state_store

    async def update_facts(self, session_id: str, last_result: Dict[str, Any]):
        """
        Extracts facts from the agent's result and merges them into SwarmState.
        Currently simple heuristic-based; can be upgraded to LLM-based extraction.
        """
        if not last_result or last_result.get("status") != "COMPLETED":
            return

        payload = last_result.get("payload", {})
        agent_key = last_result.get("agent_key", "unknown")
        
        # 1. Load current swarm state
        current_state = await self.swarm_state_store.get_swarm_state(session_id) or {}
        
        # 2. Extract Facts (Simplified: look for 'data' fields or specific fact keys)
        facts = current_state.get("facts", {})
        raw_data = payload.get("data", {})
        
        new_facts_count = 0
        if isinstance(raw_data, dict):
            # Extract common entities (Mock logic for demonstration)
            for key in ["user_profile", "preferences", "last_action", "confirmed_items"]:
                if key in raw_data:
                    facts[key] = raw_data[key]
                    new_facts_count += 1
        
        # Also store the last answer from this agent as a fact
        if payload.get("answer"):
            facts[f"last_answer_{agent_key}"] = payload.get("answer")
            new_facts_count += 1

        if new_facts_count > 0:
            current_state["facts"] = facts
            current_state["last_updated_by"] = agent_key
            
            # 3. Save back to store
            await self.swarm_state_store.save_swarm_state(session_id, current_state)
            logger.info("swarm_facts_updated", 
                        session_id=session_id, 
                        agent=agent_key, 
                        new_facts=new_facts_count)
