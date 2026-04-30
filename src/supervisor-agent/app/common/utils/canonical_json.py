import json
import hashlib
from typing import Any, Dict


class CanonicalJsonSerializer:
    """
    Implements canonical serialization rules from doc 31.
    Ensures deterministic output for hashing.
    """
    
    @staticmethod
    def serialize(data: Any) -> str:
        """
        Serializes data to a canonical JSON string.
        Rules:
        - Sorted keys
        - No extra whitespace
        - UTF-8 encoding
        """
        return json.dumps(
            data,
            sort_keys=True,
            separators=(',', ':'),
            ensure_ascii=False
        )

    @staticmethod
    def calculate_hash(data: Any) -> str:
        """
        Calculates SHA-256 hash of canonicalized data.
        """
        canonical_str = CanonicalJsonSerializer.serialize(data)
        return hashlib.sha256(canonical_str.encode('utf-8')).hexdigest()


class PlanHashCalculator:
    """
    Calculates hashes specifically for execution plans as per doc 31.
    """
    
    @staticmethod
    def calculate_request_hash(params: Dict[str, Any]) -> str:
        # Filter only canonicalizable fields for request hash
        payload = {
            "session_id": params.get("session_id"),
            "request_id": params.get("request_id"),
            "execution_mode": params.get("execution_mode", "STREAM"),
            "normalized_user_input": params.get("message", params.get("normalized_user_input")),
            "normalized_business_params": params.get("normalized_business_params", {})
        }
        return CanonicalJsonSerializer.calculate_hash(payload)

    @staticmethod
    def calculate_frozen_plan_hash(plan_data: Dict[str, Any]) -> str:
        # Canonicalize the frozen plan envelope
        payload = {
            "schema_version": plan_data.get("schema_version", 1),
            "canonicalization_version": plan_data.get("canonicalization_version", 1),
            "routing_queue": plan_data.get("routing_queue", []),
            "execution_constraints": plan_data.get("execution_constraints", {}),
            "planner_metadata": plan_data.get("planner_metadata", {})
        }
        return CanonicalJsonSerializer.calculate_hash(payload)
