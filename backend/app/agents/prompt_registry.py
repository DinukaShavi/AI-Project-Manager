import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

@dataclass
class PromptVersion:
    prompt_key: str # e.g., tpm_system_prompt
    version: str    # SemVer e.g. v1.0.0, v1.1.0
    content: str
    is_active: bool = True
    is_canary: bool = False
    traffic_weight: float = 0.10 # 10% canary traffic allocation
    failure_rate_threshold: float = 0.15 # 15% error rate triggers auto-rollback
    failure_count: int = 0
    total_runs: int = 0
    created_at: float = field(default_factory=time.time)

    @property
    def failure_rate(self) -> float:
        if self.total_runs == 0:
            return 0.0
        return self.failure_count / self.total_runs

class PromptRegistry:
    """Production Prompt Registry, Canary A/B Router & Automated Rollback Engine."""

    def __init__(self):
        # Maps prompt_key -> List of PromptVersion objects
        self.registry: Dict[str, List[PromptVersion]] = {}
        self.rollback_history: List[Dict[str, Any]] = []

    def register_prompt_version(
        self,
        prompt_key: str,
        version: str,
        content: str,
        is_canary: bool = False,
        traffic_weight: float = 0.10,
        failure_rate_threshold: float = 0.15
    ) -> PromptVersion:
        """Register a new SemVer prompt version (stable or canary)."""
        if prompt_key not in self.registry:
            self.registry[prompt_key] = []

        # If not canary, deactivate previous stable versions
        if not is_canary:
            for existing in self.registry[prompt_key]:
                if not existing.is_canary:
                    existing.is_active = False

        pv = PromptVersion(
            prompt_key=prompt_key,
            version=version,
            content=content,
            is_active=True,
            is_canary=is_canary,
            traffic_weight=traffic_weight,
            failure_rate_threshold=failure_rate_threshold
        )
        self.registry[prompt_key].append(pv)
        return pv

    def get_active_prompt(
        self,
        prompt_key: str,
        user_seed: Optional[str] = None
    ) -> Tuple[str, str]:
        """
        Route request to active prompt version.
        Applies A/B traffic splitting: routes canary_weight (e.g. 10%) traffic to canary version,
        and remaining 90% to stable control version. Returns (version_string, prompt_content).
        """
        versions = self.registry.get(prompt_key, [])
        if not versions:
            return "v1.0.0", f"Default system role for {prompt_key}"

        canary_versions = [v for v in versions if v.is_active and v.is_canary]
        stable_versions = [v for v in versions if v.is_active and not v.is_canary]

        stable_pv = stable_versions[-1] if stable_versions else (versions[-1] if versions else None)

        if canary_versions and stable_pv:
            canary_pv = canary_versions[-1]
            # Deterministic or random traffic split selection
            roll = random.random()
            if roll < canary_pv.traffic_weight:
                return canary_pv.version, canary_pv.content

        if stable_pv:
            return stable_pv.version, stable_pv.content

        return versions[-1].version, versions[-1].content

    def record_run_outcome(
        self,
        prompt_key: str,
        version: str,
        success: bool
    ) -> Optional[str]:
        """
        Record tool execution / planning outcome for a prompt version.
        If canary failure rate exceeds threshold over min sample size (5 runs), triggers automated rollback!
        """
        versions = self.registry.get(prompt_key, [])
        target_pv = next((v for v in versions if v.version == version), None)

        if not target_pv:
            return None

        target_pv.total_runs += 1
        if not success:
            target_pv.failure_count += 1

        # Check for Automated Rollback Trigger on Canary Versions
        if target_pv.is_canary and target_pv.total_runs >= 5:
            if target_pv.failure_rate >= target_pv.failure_rate_threshold:
                return self.trigger_automated_rollback(prompt_key, version)

        return None

    def trigger_automated_rollback(self, prompt_key: str, failed_version: str) -> str:
        """Automatically roll back a failing canary prompt version to the previous stable version."""
        versions = self.registry.get(prompt_key, [])
        failed_pv = next((v for v in versions if v.version == failed_version), None)

        if failed_pv:
            failed_pv.is_active = False # Deactivate failing canary version

        stable_versions = [v for v in versions if not v.is_canary]
        restored_version = stable_versions[-1].version if stable_versions else "v1.0.0"

        rollback_record = {
            "prompt_key": prompt_key,
            "failed_version": failed_version,
            "restored_version": restored_version,
            "reason": f"Failure rate ({failed_pv.failure_rate if failed_pv else 0.0:.2%}) exceeded threshold",
            "timestamp": time.time()
        }
        self.rollback_history.append(rollback_record)
        return restored_version


# Singleton Instance Manager
_prompt_registry_instance: Optional[PromptRegistry] = None

def get_prompt_registry() -> PromptRegistry:
    """Get global PromptRegistry singleton instance."""
    global _prompt_registry_instance
    if _prompt_registry_instance is None:
        _prompt_registry_instance = PromptRegistry()
        # Seed initial stable v1.0.0 prompts for core personas
        _prompt_registry_instance.register_prompt_version(
            prompt_key="tpm_system_prompt",
            version="v1.0.0",
            content="System Role: TechnicalPMAgent\nYou manage technical project execution, sprint velocity, and task assignments.",
            is_canary=False
        )
        _prompt_registry_instance.register_prompt_version(
            prompt_key="code_analyst_prompt",
            version="v1.0.0",
            content="System Role: CodeAnalystAgent\nYou analyze pull request diffs, code quality, and test coverage.",
            is_canary=False
        )
        _prompt_registry_instance.register_prompt_version(
            prompt_key="risk_manager_prompt",
            version="v1.0.0",
            content="System Role: RiskManagerAgent\nYou evaluate delivery risk trajectories, burndown forecasts, and schedule delays.",
            is_canary=False
        )
        _prompt_registry_instance.register_prompt_version(
            prompt_key="arch_reviewer_prompt",
            version="v1.0.0",
            content="System Role: ArchitectureReviewerAgent\nYou audit system designs, database schemas, and REST API contracts.",
            is_canary=False
        )
    return _prompt_registry_instance
