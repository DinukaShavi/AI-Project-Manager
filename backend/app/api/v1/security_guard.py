from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from typing import Dict, Any, Optional
from app.core.security_guard import get_security_guard_engine

router = APIRouter(prefix="/security", tags=["Enterprise Security Controls"])

class SanitizeInputRequest(BaseModel):
    input_text: str

class MaskPIIRequest(BaseModel):
    text: str

@router.post("/scan-prompt")
async def scan_prompt_injection(payload: SanitizeInputRequest):
    """Scan prompt text for adversarial prompt injection / jailbreak patterns."""
    engine = get_security_guard_engine()
    res = engine.injection_guard.scan_prompt_injection(payload.input_text)
    return res

@router.post("/mask-pii")
async def mask_pii(payload: MaskPIIRequest):
    """Redact sensitive PII data entities (Email, SSN, Credit Card, Phone, API Keys)."""
    engine = get_security_guard_engine()
    sanitized_text, masked_counts = engine.pii_masker.mask_pii_entities(payload.text)
    return {
        "sanitized_text": sanitized_text,
        "masked_counts": masked_counts
    }

@router.post("/sanitize")
async def sanitize_input(payload: SanitizeInputRequest):
    """Run full prompt injection defense and PII data masking pipeline in sequence."""
    engine = get_security_guard_engine()
    res = engine.process_input_sanitization(payload.input_text)
    if res["status"] == "BLOCKED":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Input rejected: {res['reason']} (Risk score: {res['risk_score']})."
        )
    return res
