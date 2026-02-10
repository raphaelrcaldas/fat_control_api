from dataclasses import dataclass, field
from typing import Literal


@dataclass
class CleanupTaskResult:
    task_name: str
    status: Literal['success', 'error', 'skipped']
    rows_affected: int = 0
    duration_seconds: float = 0.0
    errors: list[str] = field(default_factory=list)
    details: dict = field(default_factory=dict)
