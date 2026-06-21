"""AMIS Core REST client for E2E testing.

Wraps registry and promotion APIs to drive the full artifact lifecycle.
"""

import logging
from typing import Optional
from uuid import UUID

import httpx

log = logging.getLogger(__name__)


class AMISCoreClient:
    """Async REST client for AMIS Core service."""

    def __init__(self, base_url: str, token: str, timeout: float = 60.0):
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

    # ── Registry: Datasets ───────────────────────────────

    async def register_dataset(self, payload: dict) -> dict:
        resp = await self._client.post(
            f"{self.base_url}/api/v1/registry/datasets",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def upload_dataset_content(self, dataset_id: UUID, content: bytes) -> dict:
        files = {"file": ("dataset.parquet", content, "application/octet-stream")}
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = await self._client.post(
            f"{self.base_url}/api/v1/registry/datasets/{dataset_id}/content",
            headers=headers,
            files=files,
        )
        resp.raise_for_status()
        return resp.json()

    async def download_dataset_content(self, dataset_id: UUID) -> bytes:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/registry/datasets/{dataset_id}/content",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.content

    async def get_dataset(self, dataset_id: UUID) -> dict:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/registry/datasets/{dataset_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Registry: Feature Schemas / Labels ───────────────

    async def register_feature_schema(self, payload: dict) -> dict:
        resp = await self._client.post(
            f"{self.base_url}/api/v1/registry/feature-schemas",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def register_label_version(self, payload: dict) -> dict:
        resp = await self._client.post(
            f"{self.base_url}/api/v1/registry/label-versions",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Research Contexts ────────────────────────────────

    async def create_research_context(
        self,
        *,
        name: str,
        instrument_ids: list,
        primary_timeframe: str,
        higher_timeframe: str,
        candidate_name: str,
        research_group: str,
        candidate_type: str = "CLASSIFICATION",
        creation_mode: str = "RESEARCH_IDEA",
        description: str = "E2E test context",
        vix_min: float = None,
    ) -> dict:
        """Create a research context + candidate workspace in AMIS Core."""
        resp = await self._client.post(
            f"{self.base_url}/api/v1/research/workspaces",
            headers=self._headers(),
            json={
                "context": {
                    "name": name,
                    "instrument_ids": instrument_ids,
                    "primary_timeframe": primary_timeframe,
                    "higher_timeframe": higher_timeframe,
                    "description": description,
                    "vix_min": vix_min,
                },
                "candidate": {
                    "candidate_name": candidate_name,
                    "research_group": research_group,
                    "candidate_type": candidate_type,
                    "creation_mode": creation_mode,
                    "description": description,
                },
            },
        )
        resp.raise_for_status()
        return resp.json()

    # ── Registry: Training Runs ──────────────────────────

    async def register_training_run(self, payload: dict) -> dict:
        resp = await self._client.post(
            f"{self.base_url}/api/v1/registry/training-runs",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Promotion: Artifacts ─────────────────────────────

    async def submit_artifact(self, payload: dict) -> dict:
        resp = await self._client.post(
            f"{self.base_url}/api/v1/promotion/artifacts",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def upload_artifact_content(self, artifact_id: UUID, content: bytes) -> dict:
        files = {"file": ("model.pkl", content, "application/octet-stream")}
        headers = {"Authorization": f"Bearer {self.token}"}
        resp = await self._client.post(
            f"{self.base_url}/api/v1/promotion/artifacts/{artifact_id}/content",
            headers=headers,
            files=files,
        )
        resp.raise_for_status()
        return resp.json()

    async def download_artifact_content(self, artifact_id: UUID) -> bytes:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/promotion/artifacts/{artifact_id}/content",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.content

    async def get_artifact(self, artifact_id: UUID) -> dict:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/promotion/artifacts/{artifact_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    async def list_artifacts(
        self,
        artifact_type: Optional[str] = None,
        domain: Optional[str] = None,
        status: Optional[str] = None,
    ) -> dict:
        params = {}
        if artifact_type:
            params["artifact_type"] = artifact_type
        if domain:
            params["domain"] = domain
        if status:
            params["status"] = status
        resp = await self._client.get(
            f"{self.base_url}/api/v1/promotion/artifacts",
            headers=self._headers(),
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    # ── Promotion: Scorecards ──────────────────────────

    async def submit_scorecard(self, payload: dict) -> dict:
        resp = await self._client.post(
            f"{self.base_url}/api/v1/promotion/scorecards",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def get_scorecard(self, scorecard_id: UUID) -> dict:
        resp = await self._client.get(
            f"{self.base_url}/api/v1/promotion/scorecards/{scorecard_id}",
            headers=self._headers(),
        )
        resp.raise_for_status()
        return resp.json()

    # ── Promotion: Lifecycle ─────────────────────────────

    async def submit_for_review(self, artifact_id: UUID, deployment_context: Optional[dict] = None) -> dict:
        payload = {"deployment_context": deployment_context or {}}
        resp = await self._client.post(
            f"{self.base_url}/api/v1/promotion/artifacts/{artifact_id}/submit",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def approve_artifact(
        self,
        artifact_id: UUID,
        decision_reason: str,
        is_manual_override: bool = False,
        override_justification: Optional[str] = None,
        override_authorizer: Optional[str] = None,
        effective_at: Optional[str] = None,
    ) -> dict:
        payload = {
            "decision_reason": decision_reason,
            "is_manual_override": is_manual_override,
            "override_justification": override_justification,
            "override_authorizer": override_authorizer,
        }
        if effective_at:
            payload["effective_at"] = effective_at
        resp = await self._client.post(
            f"{self.base_url}/api/v1/promotion/artifacts/{artifact_id}/approve",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def reject_artifact(self, artifact_id: UUID, decision_reason: str) -> dict:
        payload = {"decision_reason": decision_reason}
        resp = await self._client.post(
            f"{self.base_url}/api/v1/promotion/artifacts/{artifact_id}/reject",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def rollback_artifact(
        self,
        artifact_id: UUID,
        decision_reason: str,
        target_artifact_id: Optional[UUID] = None,
        is_emergency: bool = False,
        emergency_justification: Optional[str] = None,
    ) -> dict:
        payload = {
            "decision_reason": decision_reason,
            "is_emergency": is_emergency,
        }
        if target_artifact_id:
            payload["target_artifact_id"] = str(target_artifact_id)
        if emergency_justification:
            payload["emergency_justification"] = emergency_justification
        resp = await self._client.post(
            f"{self.base_url}/api/v1/promotion/artifacts/{artifact_id}/rollback",
            headers=self._headers(),
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
