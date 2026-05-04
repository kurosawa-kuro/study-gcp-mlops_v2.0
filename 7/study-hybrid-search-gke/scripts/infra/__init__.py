"""Infrastructure cleanup / state-management helpers.

業務ロジック (terraform state 操作 / kubectl context 設定 / GCS bucket 空化 /
Vertex Endpoint cleanup) を `scripts/setup/{deploy,destroy}_all.py` から
切り出した topical module 群。orchestrator は from scripts.infra.* import
で必要な関数だけ呼ぶ。

I/O OK (subprocess / gcloud / kubectl / network)。ただし `scripts.setup`
を import してはならない (循環防止 — orchestrator が消費側、本パッケージ
は被消費側)。
"""
