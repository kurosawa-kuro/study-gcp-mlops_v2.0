from __future__ import annotations

import numpy as np

from ml.serving import encoder as encoder_module


class _FakeEncoder:
    def _encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray([[float(len(texts[0]))], [float(len(texts[1]))]], dtype=float)


def test_normalize_instance_accepts_prefixed_string() -> None:
    assert encoder_module._normalize_instance("query: 赤羽") == "query: 赤羽"


def test_normalize_instance_accepts_legacy_object_payload() -> None:
    item = encoder_module.EncoderInstance(text="赤羽", kind="passage")
    assert encoder_module._normalize_instance(item) == "passage: 赤羽"


def test_predict_accepts_mixed_request_shapes() -> None:
    encoder_module.app.state.encoder = _FakeEncoder()
    request = encoder_module.EncoderRequest(
        instances=["query: 赤羽", {"text": "西新宿", "kind": "passage"}]
    )

    response = encoder_module.predict(request)

    assert len(response.predictions) == 2
    assert response.predictions[0] == [float(len("query: 赤羽"))]
    assert response.predictions[1] == [float(len("passage: 西新宿"))]
