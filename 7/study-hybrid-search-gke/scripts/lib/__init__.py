"""Shared library — pure-data constants and schema generators.

Modules under this package must NOT perform I/O (no subprocess, no network,
no filesystem access). They centralise GCP resource names and config schemas
that were previously hardcoded in multiple places, removing the drift
surface that produced the Phase 7 W2-5 ConfigMap rollout failure.
"""
