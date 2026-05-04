"""Phase 6 T2 — Dataflow (Apache Beam) streaming pipelines.

Sidecar to the Phase 5 BQ Subscription that lands raw ranking-log events.
This package computes hourly CTR aggregates from the same Pub/Sub topic
and writes ``mlops.ranking_log_hourly_ctr`` in parallel, leaving the
existing ranking_log raw path untouched.
"""
