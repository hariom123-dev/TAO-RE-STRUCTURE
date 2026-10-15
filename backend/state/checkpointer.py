"""
Pipeline State Checkpointer — LangGraph Time-Travel & Counterfactual Forking.
Follows Pillar 4 of the TAO Advanced Roadmap:

Snapshots IncidentState at each milestone node transition:
  Router → Tier 1 Step k → Debate Round r → Tier 3 Sentinel → Guardrails

Enables operators to click any historical node in a completed run, modify variables
(e.g., toggle constitutional principles, inject counter-critiques, tighten KL thresholds),
and replay the pipeline forward from that exact checkpoint without re-running prior steps.
"""

import time
import uuid
from typing import Any, Optional
from backend.models import CheckpointSnapshot


class PipelineCheckpointer:
    """
    In-memory state checkpointer for pipeline time-travel and counterfactual execution.
    Maintains ring-buffered snapshots of execution states.
    """

    def __init__(self, max_checkpoints: int = 200):
        self.max_checkpoints = max_checkpoints
        self._checkpoints: dict[str, CheckpointSnapshot] = {}
        self._request_index: dict[str, list[str]] = {}

    def save_checkpoint(
        self,
        request_id: str,
        node_name: str,
        state_data: dict[str, Any],
        summary: str = "",
    ) -> CheckpointSnapshot:
        """Save a new state checkpoint for a pipeline node transition."""
        chk_id = f"chk_{request_id[:8]}_{node_name}_{int(time.time() * 1000) % 100000}"
        snapshot = CheckpointSnapshot(
            checkpoint_id=chk_id,
            request_id=request_id,
            node_name=node_name,
            timestamp=time.time(),
            summary=summary or f"State at node: {node_name}",
            state_data=state_data,
        )

        # Evict oldest if capacity reached
        if len(self._checkpoints) >= self.max_checkpoints:
            oldest_id = next(iter(self._checkpoints))
            del self._checkpoints[oldest_id]

        self._checkpoints[chk_id] = snapshot
        if request_id not in self._request_index:
            self._request_index[request_id] = []
        self._request_index[request_id].append(chk_id)

        return snapshot

    def get_checkpoint(self, checkpoint_id: str) -> Optional[CheckpointSnapshot]:
        """Retrieve a specific checkpoint by ID."""
        return self._checkpoints.get(checkpoint_id)

    def get_checkpoints_for_request(self, request_id: str) -> list[CheckpointSnapshot]:
        """Retrieve all chronological checkpoints recorded for a specific request."""
        chk_ids = self._request_index.get(request_id, [])
        return [self._checkpoints[cid] for cid in chk_ids if cid in self._checkpoints]


pipeline_checkpointer = PipelineCheckpointer()
