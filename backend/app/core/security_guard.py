import re
from typing import Dict, List, Tuple, Any, Optional

INJECTION_PATTERNS = [
    r'ignore\s+(?:all\s+)?previous\s+instructions',
    r'bypass\s+(?:system\s+)?prompt',
    r'disregard\s+all\s+prior',
    r'you\s+are\s+now\s+dan',
    r'do\s+anything\s+now',
    r'reveal\s+(?:system\s+)?prompt',
    r'expose\s+(?:vault\s+)?secrets',
    r'override\s+system\s+policy',
    r'jailbreak\s+mode',
    r'print\s+(?:env|environment)\s+variables'
]

PII_PATTERNS = {
    "email": r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b',
    "ssn": r'\b\d{3}-\d{2}-\d{4}\b',
    "credit_card": r'\b(?:\d[ -]*?){13,16}\b',
    "phone": r'\b(?:\+?\d{1,3}[-.\s]?)?\(?\d{3}\)?[-.\s]?\d{3}[-.\s]?\d{4}\b',
    "api_key": r'\b(?:sk-[A-Za-z0-9]{32,64}|ghp_[A-Za-z0-9]{36})\b'
}

class PromptInjectionGuard:
    """Prompt Injection Defense Engine scanning for adversarial jailbreak attempts."""

    def __init__(self):
        self.patterns = [re.compile(p, re.IGNORECASE) for p in INJECTION_PATTERNS]

    def scan_prompt_injection(self, prompt_text: str) -> Dict[str, Any]:
        """Scan input prompt for prompt injection patterns and calculate risk score."""
        if not prompt_text:
            return {"is_injection": False, "risk_score": 0.0, "matched_patterns": []}

        matched = []
        for pat in self.patterns:
            if pat.search(prompt_text):
                matched.append(pat.pattern)

        is_injection = len(matched) > 0
        risk_score = round(min(1.0, len(matched) * 0.5), 2) if is_injection else 0.0

        return {
            "is_injection": is_injection,
            "risk_score": risk_score,
            "matched_patterns": matched,
            "action": "BLOCK" if is_injection else "ALLOW"
        }

class PIIDataMasker:
    """PII Detection & Data Masking Pipeline for redaction before external API calls."""

    def __init__(self):
        self.compiled_patterns = {cat: re.compile(pat) for cat, pat in PII_PATTERNS.items()}

    def mask_pii_entities(self, text: str) -> Tuple[str, Dict[str, int]]:
        """Redact emails, SSNs, credit cards, phone numbers, and API keys."""
        if not text:
            return "", {}

        sanitized_text = text
        masked_counts: Dict[str, int] = {}

        for category, pat in self.compiled_patterns.items():
            matches = pat.findall(sanitized_text)
            if matches:
                masked_counts[category] = len(matches)
                replacement = f"[{category.upper()}_REDACTED]"
                sanitized_text = pat.sub(replacement, sanitized_text)

        return sanitized_text, masked_counts

class SecurityGuardEngine:
    """Enterprise AI Security Suite combining Prompt Injection Defense and PII Redaction."""

    def __init__(self):
        self.injection_guard = PromptInjectionGuard()
        self.pii_masker = PIIDataMasker()

    def process_input_sanitization(self, input_text: str) -> Dict[str, Any]:
        """Run full prompt injection check and PII redaction pipeline in sequence."""
        inj_res = self.injection_guard.scan_prompt_injection(input_text)
        if inj_res["is_injection"]:
            return {
                "status": "BLOCKED",
                "reason": "PROMPT_INJECTION_DETECTED",
                "risk_score": inj_res["risk_score"],
                "sanitized_text": None,
                "pii_masked_counts": {}
            }

        sanitized_text, masked_counts = self.pii_masker.mask_pii_entities(input_text)
        return {
            "status": "PASSED",
            "reason": None,
            "risk_score": 0.0,
            "sanitized_text": sanitized_text,
            "pii_masked_counts": masked_counts
        }


# Singleton Instance Manager
_security_guard_engine_instance: Optional[SecurityGuardEngine] = None

def get_security_guard_engine() -> SecurityGuardEngine:
    """Get global SecurityGuardEngine singleton instance."""
    global _security_guard_engine_instance
    if _security_guard_engine_instance is None:
        _security_guard_engine_instance = SecurityGuardEngine()
    return _security_guard_engine_instance
