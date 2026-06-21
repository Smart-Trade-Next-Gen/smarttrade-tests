"""AMIS end-to-end full pipeline test.

Dataset generation → Walk-forward validation → Scorecard → Promotion → Rollback

Requires running services:
  - MDS (port 8004) with historical NIFTY 1H data
  - AMIS Core (port 8000)
  - AMIS Lab (port 8016)

Environment:
  JWT_SECRET_KEY must match the services' secret key.
  MDS_USER_JWT_TOKEN should be configured on the Lab service for real data.
"""

import logging
from datetime import datetime, timezone
from uuid import UUID

import pytest

from e2e.clients import AMISCoreClient, AMISLabClient

log = logging.getLogger(__name__)

# Use a 6-week window to ensure enough rows survive feature extraction
# and label generation (horizon_bars=20 drops the last 20 bars)
TEST_INSTRUMENT = "NSE:CASH:INDEX:NIFTY"
TEST_TIMEFRAME = "1h"
TEST_START = datetime(2024, 1, 1, 3, 45, tzinfo=timezone.utc)
TEST_END = datetime(2024, 2, 15, 9, 45, tzinfo=timezone.utc)

WALK_FORWARD_WINDOWS = [
    {
        "train_start": "2024-01-01",
        "train_end": "2024-01-31",
        "test_start": "2024-02-01",
        "test_end": "2024-02-15",
    },
]


@pytest.mark.slow
@pytest.mark.amis
@pytest.mark.asyncio
async def test_amis_full_pipeline(
    amis_core_client: AMISCoreClient,
    amis_lab_client: AMISLabClient,
    research_context_id: str,
):
    """
    End-to-end AMIS pipeline:
      1. Generate dataset via Lab (fetches from MDS, uploads to Core)
      2. Run walk-forward via Lab (trains on windows, uploads models to Core)
      3. Generate scorecard via Lab (submits to Core)
      4. Submit artifact for review via Core
      5. Approve with manual override via Core
      6. Verify artifact promoted to PRODUCTION
      7. Rollback via Core
      8. Verify artifact rolled back
    """
    log.info("=" * 60)
    log.info("AMIS E2E: Full Pipeline Test")
    log.info("=" * 60)

    # ── 0. Create research context in Core ─────────────────────────
    log.info("Step 0: Creating research context in AMIS Core")
    import uuid as uuid_lib
    unique_suffix = str(uuid_lib.uuid4())[:8]
    ctx = await amis_core_client.create_research_context(
        name=f"E2E Full Pipeline Test {unique_suffix}",
        instrument_ids=[TEST_INSTRUMENT],
        primary_timeframe=TEST_TIMEFRAME,
        higher_timeframe="1d",
        candidate_name=f"e2e_rg16_test_{unique_suffix}",
        research_group="e2e",
        candidate_type="CLASSIFICATION",
        creation_mode="RESEARCH_IDEA",
        description="End-to-end AMIS pipeline test context",
        vix_min=int(unique_suffix[:4], 16) / 1000.0,  # unique value to vary context hash
    )
    real_research_context_id = UUID(ctx["context_id"])
    log.info("Research context created: id=%s", real_research_context_id)

    # ── 1. Generate dataset ───────────────────────────────────────
    log.info("Step 1: Generating dataset (%s %s %s → %s)", TEST_INSTRUMENT, TEST_TIMEFRAME, TEST_START, TEST_END)
    ds = await amis_lab_client.generate_dataset(
        instrument_id=TEST_INSTRUMENT,
        timeframe=TEST_TIMEFRAME,
        start_date=TEST_START,
        end_date=TEST_END,
        feature_set="V1",
        research_context_id=real_research_context_id,
    )
    dataset_id = UUID(ds["dataset_id"])
    feature_schema_id = UUID(ds["feature_schema_id"])
    label_version_id = UUID(ds["label_version_id"])
    log.info("Dataset generated: id=%s samples=%s features=%s", dataset_id, ds["sample_count"], ds["feature_count"])

    # Verify dataset content is stored in Core
    ds_meta = await amis_core_client.get_dataset(dataset_id)
    assert ds_meta["storage_path"], "Dataset should have storage_path after upload"
    assert ds_meta["storage_checksum"], "Dataset should have checksum after upload"

    # ── 2. Walk-forward validation ────────────────────────────────
    log.info("Step 2: Running walk-forward validation (%d windows)", len(WALK_FORWARD_WINDOWS))
    wf = await amis_lab_client.run_walk_forward(
        artifact_id="e2e_rg16_test_001",
        windows=WALK_FORWARD_WINDOWS,
        instruments=[TEST_INSTRUMENT],
        dataset_id=dataset_id,
        feature_schema_id=feature_schema_id,
        label_version_id=label_version_id,
        model_type="RANDOM_FOREST",
        hyperparameters={"n_estimators": 50, "max_depth": 4},
        research_context_id=real_research_context_id,
    )
    job_id = wf["job_id"]
    log.info("Walk-forward job created: %s status=%s", job_id, wf["status"])

    # Walk-forward is synchronous in the endpoint; results are in the response
    assert wf["status"] == "COMPLETED", f"Walk-forward failed: {wf}"
    windows = wf.get("results", [])
    assert len(windows) == len(WALK_FORWARD_WINDOWS), f"Expected {len(WALK_FORWARD_WINDOWS)} windows, got {len(windows)}"

    completed_windows = [w for w in windows if w.get("status") == "COMPLETED"]
    assert len(completed_windows) >= 1, f"No windows completed: {windows}"
    log.info("Walk-forward completed: %d/%d windows OK", len(completed_windows), len(windows))

    # Pick the first completed window's artifact for promotion
    first_artifact_id = None
    for w in completed_windows:
        aid = w.get("artifact_id")
        if aid:
            first_artifact_id = UUID(aid)
            break
    assert first_artifact_id is not None, "No artifact_id found in window results"
    log.info("Target artifact for promotion: %s", first_artifact_id)

    # ── 3. Generate scorecard ──────────────────────────────────────
    log.info("Step 3: Generating scorecard for job %s", wf.get("id", job_id))
    # The walk-forward result may contain the job internal UUID or job_id string
    # Use the job_id string to fetch the job details and get the internal UUID
    job_detail = await amis_lab_client.get_validation_job(job_id)
    job_uuid = UUID(job_detail["id"])
    scorecard = await amis_lab_client.generate_scorecard(job_uuid)
    log.info("Scorecard generated: %s passed=%s", scorecard.get("scorecard_id"), scorecard.get("overall_passed"))

    # Verify scorecard exists in Core
    scorecard_id = UUID(scorecard["scorecard_id"])
    sc = await amis_core_client.get_scorecard(scorecard_id)
    assert sc["artifact_id"] == str(first_artifact_id), "Scorecard should reference the correct artifact"

    # ── 4. Submit for review ────────────────────────────────────────
    log.info("Step 4: Submitting artifact %s for review", first_artifact_id)
    artifact_before_review = await amis_core_client.get_artifact(first_artifact_id)
    current_status = artifact_before_review["status"]
    log.info("Artifact current status before review: %s", current_status)

    if current_status == "PENDING":
        review = await amis_core_client.submit_for_review(first_artifact_id)
        current_status = review["status"]
    elif current_status == "UNDER_REVIEW":
        log.info("Artifact already UNDER_REVIEW (idempotent from prior run)")
    elif current_status == "REJECTED":
        log.info("Artifact already REJECTED (idempotent from prior run)")
    else:
        raise AssertionError(f"Unexpected artifact status: {current_status}")

    if current_status == "UNDER_REVIEW":
        # ── 5. Approve with manual override ────────────────────────────
        log.info("Step 5: Approving artifact %s (manual override)", first_artifact_id)
        approval = await amis_core_client.approve_artifact(
            artifact_id=first_artifact_id,
            decision_reason="E2E test promotion with manual override",
            is_manual_override=True,
            override_justification="Fewer than 4 windows in fast E2E test",
            override_authorizer="e2e-test-suite",
        )
        assert approval["status"] == "PRODUCTION", f"Expected PRODUCTION, got {approval['status']}"
        log.info("Artifact approved: status=%s effective_at=%s", approval["status"], approval.get("effective_at"))

        # Verify artifact promoted in Core
        artifact = await amis_core_client.get_artifact(first_artifact_id)
        assert artifact["status"] == "PRODUCTION", f"Artifact status should be PRODUCTION, got {artifact['status']}"
        assert artifact["storage_path"].startswith("core/"), f"Artifact should be in core bucket: {artifact['storage_path']}"
        log.info("Artifact verified in Core: status=%s storage_path=%s", artifact["status"], artifact["storage_path"])

        # ── 6. Rollback ────────────────────────────────────────────────
        log.info("Step 6: Rolling back artifact %s", first_artifact_id)
        rollback = await amis_core_client.rollback_artifact(
            artifact_id=first_artifact_id,
            decision_reason="E2E test rollback",
        )
        assert rollback["status"] == "ROLLED_BACK", f"Expected ROLLED_BACK, got {rollback['status']}"
        log.info("Artifact rolled back: status=%s", rollback["status"])

        # Verify artifact rolled back in Core
        artifact_after = await amis_core_client.get_artifact(first_artifact_id)
        assert artifact_after["status"] == "ROLLED_BACK", f"Artifact status should be ROLLED_BACK, got {artifact_after['status']}"
        log.info("Rollback verified in Core: status=%s", artifact_after["status"])
    elif current_status == "REJECTED":
        log.info("Artifact rejected (expected for weak E2E model)")
        artifact = await amis_core_client.get_artifact(first_artifact_id)
        assert artifact["status"] == "REJECTED", f"Artifact status should be REJECTED, got {artifact['status']}"

    log.info("=" * 60)
    log.info("AMIS E2E: Full Pipeline Test PASSED")
    log.info("=" * 60)
