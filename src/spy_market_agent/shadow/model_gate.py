from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from spy_market_agent.shadow.types import (
    BLOCKED_NO_APPROVED_MODEL,
    NO_APPROVED_SHADOW_MODEL,
    ModelAdmissionDecision,
    ModelAdmissionStatus,
    ShadowMode,
    ShadowModelMetadata,
)


@dataclass(frozen=True, slots=True)
class ShadowAdmissionIssue:
    code: str
    message: str


class ShadowModelAdmissionError(ValueError):
    """Raised when a Phase 4 model-connected shadow run is not admitted."""

    def __init__(self, issue: ShadowAdmissionIssue) -> None:
        self.issue = issue
        super().__init__(f"{issue.code}: {issue.message}")


def evaluate_model_admission(
    mode: ShadowMode,
    metadata: ShadowModelMetadata | None,
) -> ModelAdmissionDecision:
    if mode == ShadowMode.OBSERVATION_ONLY_NO_MODEL:
        return ModelAdmissionDecision(
            status=ModelAdmissionStatus.NOT_REQUIRED_OBSERVATION_ONLY,
            inference_allowed=False,
            model_id=None,
            reasons=(BLOCKED_NO_APPROVED_MODEL,),
        )

    if metadata is None:
        _raise_model_gate_error(
            BLOCKED_NO_APPROVED_MODEL,
            NO_APPROVED_SHADOW_MODEL,
        )

    if metadata.approval_status != "approved" or not metadata.approved_for_shadow:
        _raise_model_gate_error(
            "model_not_approved_for_shadow",
            "model metadata is not explicitly approved for shadow operation.",
        )

    return ModelAdmissionDecision(
        status=ModelAdmissionStatus.APPROVED_FOR_SHADOW,
        inference_allowed=True,
        model_id=metadata.model_id,
        reasons=(),
    )


def require_model_admission(metadata: ShadowModelMetadata | None) -> ModelAdmissionDecision:
    return evaluate_model_admission(ShadowMode.MODEL_CONNECTED, metadata)


def _raise_model_gate_error(code: str, message: str) -> NoReturn:
    raise ShadowModelAdmissionError(ShadowAdmissionIssue(code=code, message=message))
