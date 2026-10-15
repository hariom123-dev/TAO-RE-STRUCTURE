"""
TAO SDK Exceptions.
"""

from typing import Any, Optional


class TAOError(Exception):
    """Base exception for TAO SDK errors."""
    pass


class TAOAlignmentViolationError(TAOError):
    """
    Raised when an output fails constitutional oversight, debate scrutiny,
    or steganography anomaly checks.
    """
    def __init__(
        self,
        message: str,
        violation_type: str = "AlignmentViolation",
        receipt: Optional[dict[str, Any]] = None,
        verdict: str = "flagged",
    ):
        super().__init__(message)
        self.violation_type = violation_type
        self.receipt = receipt
        self.verdict = verdict

    def __repr__(self) -> str:
        return f"TAOAlignmentViolationError(type={self.violation_type}, verdict={self.verdict}, msg={super().__str__()})"
