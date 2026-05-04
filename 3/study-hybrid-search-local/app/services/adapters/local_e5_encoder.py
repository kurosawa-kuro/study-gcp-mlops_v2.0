"""Phase 3 — Local in-process multilingual-e5 encoder.

sentence-transformers を直接プロセス内に load してクエリ / passage を embed する。
Phase 7 では KServe InferenceService 経由 (cluster-local HTTP) だが、Phase 3 は
ローカル完結のため in-process。

ME5 のお作法:
- query 側は ``query: ...`` prefix
- passage 側は ``passage: ...`` prefix
- 出力は L2 正規化済 (sentence-transformers default = normalize_embeddings=True)

Phase 4 で encoder を Cloud Run service に外出しする際、本 adapter を Cloud Run
HTTP 呼び出し adapter に差し替える。
"""

from __future__ import annotations

from typing import Literal

from app.services.protocols.encoder_client import EncoderClient
from ml.common import get_logger


class LocalE5Encoder(EncoderClient):
    """In-process sentence-transformers encoder."""

    def __init__(
        self,
        *,
        model_name: str = "intfloat/multilingual-e5-small",
        max_seq_length: int = 512,
    ) -> None:
        # 遅延 import: image にライブラリは焼き込まれているが、test 環境で
        # sentence-transformers が無い場合に import 失敗を回避する。
        from sentence_transformers import SentenceTransformer

        self._logger = get_logger("app.adapters.local_e5_encoder")
        self._model = SentenceTransformer(model_name)
        self._model.max_seq_length = max_seq_length
        self._model_name = model_name

    @property
    def model_name(self) -> str:
        return self._model_name

    def embed(self, text: str, kind: Literal["query", "passage"]) -> list[float]:
        prefix = "query: " if kind == "query" else "passage: "
        prepared = prefix + (text or "")
        # encode は numpy.ndarray を返す。normalize_embeddings=True で L2 正規化。
        vec = self._model.encode(
            [prepared],
            normalize_embeddings=True,
            show_progress_bar=False,
        )[0]
        return [float(x) for x in vec]
