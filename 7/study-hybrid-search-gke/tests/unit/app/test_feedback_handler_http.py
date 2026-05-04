"""HTTP-level tests for the ``/feedback`` handler."""

from __future__ import annotations


def test_feedback_endpoint_records_event(fake_client, fake_feedback_recorder) -> None:
    response = fake_client.post(
        "/feedback",
        json={"request_id": "r-1", "property_id": "P-001", "action": "click"},
    )

    assert response.status_code == 200
    assert response.json() == {"accepted": True}
    assert len(fake_feedback_recorder.events) == 1
    event = fake_feedback_recorder.events[0]
    assert event.request_id == "r-1"
    assert event.property_id == "P-001"
    assert event.action == "click"


def test_feedback_endpoint_rejects_invalid_action(fake_client) -> None:
    response = fake_client.post(
        "/feedback",
        json={"request_id": "r-1", "property_id": "P-001", "action": "evil"},
    )
    # Pydantic regex pattern enforces (click|favorite|inquiry)
    assert response.status_code == 422
