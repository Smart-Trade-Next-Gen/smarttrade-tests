"""AMIS Lab REST client for E2E testing.

Wraps research and validation APIs to drive dataset generation and walk-forward.
"""

import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import httpx

log = logging.getLogger(__name__)


class AMISLabClient:
    """Async REST client for AMIS Lab service."""

    def __init__(self, base_url: str, token: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}

    async def generate_dataset(
        self,
        instrument_id: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        feature_set: str = "V1",
        label_config: Optional[dict] = None,
        research_context_id: Optional[UUID] = None,
    ) -> dict:
        """Generate a supervised dataset from MDS historical candles."""
        payload = {
            "instrument_id": instrument_id,
            "timeframe": timeframe,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "feature_set": feature_set,
            "label_config": label_config or {},
            "research_context_id": str(research_context_id) if research_context_id else str(UUID(int=0)),
        }
        resp = await self._client.post(
            f"{self.base_url}/api/v1/research/datasets/generate",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def run_walk_forward(
        self,
        artifact_id: str,
        windows: list,
        instruments: list,
        dataset_id: UUID,
        feature_schema_id: UUID,
        label_version_id: UUID,
        model_type: str = "RANDOM_FOREST",
        hyperparameters: Optional[dict] = None,
        research_context_id: Optional[UUID] = None,
    ) -> dict:
        """Run walk-forward validation."""
        payload = {
            "artifact_id": artifact_id,
            "windows": windows,
            "instruments": instruments,
            "dataset_id": str(dataset_id),
            "feature_schema_id": str(feature_schema_id),
            "label_version_id": str(label_version_id),
            "model_type": model_type,
            "hyperparameters": hyperparameters or {},
        }
        if research_context_id:
            payload["research_context_id"] = str(research_context_id)
        resp = await self._client.post(
            f"{self.base_url}/api/v1/validation/walk-forward",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_validation_job(self, job_id: str) -> dict:
        """Get validation job by job_id string (e.g. wf_abc123)."""
        resp = await self._client.get(
            f"{self.base_url}/api/v1/validation/jobs/by-job-id/{job_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def generate_scorecard(self, job_id: UUID) -> dict:
        """Generate a scorecard from a validation job and submit to Core."""
        resp = await self._client.post(
            f"{self.base_url}/api/v1/validation/scorecards/{job_id}/submit",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def list_validation_jobs(self, artifact_id: Optional[str] = None) -> dict:
        params = {}
        if artifact_id:
            params["artifact_id"] = artifact_id
        resp = await self._client.get(
            f"{self.base_url}/api/v1/validation/jobs",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()
