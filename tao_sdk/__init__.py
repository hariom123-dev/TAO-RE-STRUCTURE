"""
TAO Python SDK — Zero-Boilerplate Oversight Gateway & @tao_shield Decorator.
"""

from tao_sdk.client import TAOClient
from tao_sdk.decorator import tao_shield
from tao_sdk.exceptions import TAOError, TAOAlignmentViolationError

__all__ = [
    "TAOClient",
    "tao_shield",
    "TAOError",
    "TAOAlignmentViolationError",
]
