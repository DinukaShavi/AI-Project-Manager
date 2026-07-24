from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from app.agents.prompt_registry import get_prompt_registry

router = APIRouter(prefix="/prompts", tags=["Prompts & Versioning"])

class PromptRegisterRequest(BaseModel):
    prompt_key: str
    version: str
    content: str
    is_canary: bool = False
    traffic_weight: float = 0.10
    failure_rate_threshold: float = 0.15

class OutcomeRecordRequest(BaseModel):
    prompt_key: str
    version: str
    success: bool

@router.get("/{prompt_key}")
async def get_prompt_version(prompt_key: str):
    """Get currently active prompt version and content for a prompt key."""
    registry = get_prompt_registry()
    ver, content = registry.get_active_prompt(prompt_key)
    versions = registry.registry.get(prompt_key, [])
    return {
        "prompt_key": prompt_key,
        "active_version": ver,
        "content": content,
        "total_registered_versions": len(versions),
        "versions": [
            {
                "version": v.version,
                "is_active": v.is_active,
                "is_canary": v.is_canary,
                "traffic_weight": v.traffic_weight,
                "failure_rate": f"{v.failure_rate:.2%}",
                "total_runs": v.total_runs
            } for v in versions
        ]
    }

@router.post("/register", status_code=status.HTTP_201_CREATED)
async def register_prompt_version(payload: PromptRegisterRequest):
    """Register a new SemVer prompt version (Canary or Stable)."""
    registry = get_prompt_registry()
    pv = registry.register_prompt_version(
        prompt_key=payload.prompt_key,
        version=payload.version,
        content=payload.content,
        is_canary=payload.is_canary,
        traffic_weight=payload.traffic_weight,
        failure_rate_threshold=payload.failure_rate_threshold
    )
    return {
        "message": "Prompt version registered successfully.",
        "prompt_key": pv.prompt_key,
        "version": pv.version,
        "is_canary": pv.is_canary,
        "traffic_weight": pv.traffic_weight
    }

@router.post("/outcome")
async def record_prompt_outcome(payload: OutcomeRecordRequest):
    """Record execution outcome for a prompt version and evaluate auto-rollback conditions."""
    registry = get_prompt_registry()
    restored = registry.record_run_outcome(
        prompt_key=payload.prompt_key,
        version=payload.version,
        success=payload.success
    )
    return {
        "prompt_key": payload.prompt_key,
        "version": payload.version,
        "recorded_success": payload.success,
        "rollback_triggered": bool(restored),
        "restored_version": restored
    }

@router.post("/{prompt_key}/rollback")
async def trigger_rollback(prompt_key: str, failed_version: str):
    """Manually trigger an immediate rollback to the active stable version."""
    registry = get_prompt_registry()
    restored = registry.trigger_automated_rollback(prompt_key, failed_version)
    return {
        "message": f"Prompt '{prompt_key}' successfully rolled back from '{failed_version}' to '{restored}'.",
        "prompt_key": prompt_key,
        "restored_version": restored
    }
