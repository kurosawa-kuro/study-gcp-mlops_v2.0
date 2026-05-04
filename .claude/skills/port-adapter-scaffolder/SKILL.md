---
name: port-adapter-scaffolder
description: 'Walk the user through adding a new Port + adapter + noop double + composition-root wiring + RULES update + docs entry, in dependency order. Use when the user says "add a Port for X" or "I need a new adapter for Y". Proposes edits only; the user applies them.'
argument-hint: 'What concept is the new Port for? (e.g. "Memorystore Redis cache for query embeddings")'
---

# Port-Adapter Scaffolder

## What This Skill Produces

- A 6-step proposal for adding a new Port to the **Phase 7 canonical** structure (`7/study-hybrid-search-gke/`).
- File path, class name, and minimal code skeleton for each step.
- An explicit `scripts/ci/layers.py` patch suggestion so `make check-layers` keeps passing.
- A docs entry (`docs/architecture/03_実装カタログ.md`) line so the implementation catalog stays in sync.

## When to Use

- User wants to add a new Port (e.g. cache, vector store backend, feature store fetcher, alert dispatcher).
- User wants to swap a backend and the new backend doesn't yet have a Port.
- A new GCP/Vertex/BQ/Redis concept is being introduced and you want to do it in the right order.

**Do NOT use this skill for**:
- Modifying an existing Port (use `port-adapter-boundary-reviewer.agent.md` instead).
- Hybrid-search 5-element changes (Meilisearch / ME5 / VVS / RRF / LightGBM) — those are user-decision.
- Pure adapter swaps where the Port already exists (just add the adapter file + composition root entry).

## Workflow

Establish the concept name in `<UpperCamel>` (e.g. `QueryEmbeddingCache`) and the lowercase module name (`query_embedding_cache`). Then propose **all 6 steps in this order** (do not skip):

### Step 1 — Define the Port

Path: `app/services/protocols/<module>.py` (or `ml/<feat>/ports/<module>.py` if it's an ML-side concern like trainer / model store).

Skeleton:
```python
from typing import Protocol


class <Concept>Port(Protocol):
    def <verb>(self, *, <args>) -> <return-type>: ...
```

**Rules**:
- Pure Protocol (PEP 544). No `ABC`, no inheritance, no decorators.
- No `google.cloud.*`, no `lightgbm`, no `pandas`/`numpy` (`ADAPTER_BANS` + per-file bans in `scripts/ci/layers.py`).
- 1 file = 1 Port.

### Step 2 — Noop / InMemory double

Path: `app/services/noop_adapters/<module>.py`

Skeleton:
```python
from app.services.protocols.<module> import <Concept>Port


class Noop<Concept>:
    def <verb>(self, *, <args>) -> <return-type>:
        return <empty-or-default>
```

**Rule**: Without this, `make api-dev` with `SEMANTIC_BACKEND=noop` / `LEXICAL_BACKEND=noop` cannot start.

### Step 3 — Update `scripts/ci/layers.py`

If the new Port lives under an already-covered prefix (`app/services/protocols/` / `ml/<feat>/ports/`), `DIRECTORY_RULES` covers it — **no edit needed**. Verify with `rg "<module>" 7/study-hybrid-search-gke/scripts/ci/layers.py`.

If the new Port lives outside (e.g. you added a new `ml/<new-feat>/ports/` subtree), add to `DIRECTORY_RULES`:
```python
"ml/<new-feat>/ports/": ADAPTER_BANS | frozenset({"lightgbm"}),
```

If the Port file needs **extra bans** beyond the directory default (e.g. file uses Pydantic but not numpy), add to `RULES`:
```python
"app/services/protocols/<module>.py": ADAPTER_BANS | frozenset({"<extra>"}),
```

### Step 4 — Test fake

Path: `tests/_fakes/<module>.py`

Skeleton:
```python
from app.services.protocols.<module> import <Concept>Port


class Fake<Concept>:
    def __init__(self) -> None:
        self.calls: list[<arg-tuple>] = []

    def <verb>(self, *, <args>) -> <return-type>:
        self.calls.append((<args>))
        return <fixture-value>
```

### Step 5 — Wire into composition root

Path: `app/composition_root.py` + `app/container/{infra,ml,search}.py`

Decide which builder owns it:
- **InfraBuilder** — GCP SDK clients, HTTP clients, Pub/Sub, BigQuery, Vertex, KServe, Redis, Meilisearch.
- **MlBuilder** — ML model wrappers, encoders, rerankers, training/registry adapters.
- **SearchBuilder** — high-level search service composition.

Add a getter: `def get_<concept>(self) -> <Concept>Port: return self._<concept>`. Wire it through FastAPI `Depends`.

### Step 6 — Production adapter

Path: `app/services/adapters/<backend>_<module>.py` (e.g. `redis_query_embedding_cache.py`).

This is the only step where `google.cloud.*` / `redis` / `httpx` / etc. import is allowed (`EXCLUSIONS` covers `app/services/adapters/`).

Skeleton:
```python
from app.services.protocols.<module> import <Concept>Port


class <Backend><Concept>:
    def __init__(self, <client>) -> None:
        self._client = <client>

    def <verb>(self, *, <args>) -> <return-type>:
        ...  # SDK call
```

**Update**: append a row to `7/study-hybrid-search-gke/docs/architecture/03_実装カタログ.md` (Port × adapter table) so the implementation snapshot stays accurate.

## Decision Points

- **app vs ml side** — if the Port is consumed at request time by `app/services/`, put it in `app/services/protocols/`. If it's consumed at training/registry/serving lifecycle in batch jobs, put it in `ml/<feat>/ports/`. Never both (no duplicate Port names across trees).
- **Builder ownership** — pick **one** builder. Cross-builder injection is allowed (`SearchBuilder` consumes `InfraBuilder`/`MlBuilder` outputs), but the Port's owner is single.
- **Adapter naming** — use the backend prefix (`Redis<Concept>`, `BigQuery<Concept>`, `KServe<Concept>`, `Meilisearch<Concept>`). Avoid generic names like `Default<Concept>`.
- **Terraform follow-up** — if the new Port has a GCP resource backing (Memorystore, Pub/Sub topic, FOS feature view), open `infra/terraform/modules/<concept>/` in a follow-up PR. **One concept = one module.**

## Completion Criteria

- All 6 steps proposed (none skipped).
- `RULES`/`DIRECTORY_RULES` patch is shown if needed (or "no edit needed" with verification command).
- One line for `docs/architecture/03_実装カタログ.md`.
- A final command for the user to run: `cd 7/study-hybrid-search-gke && make check-layers`.

## Suggested Verification Commands

- After applying: `cd 7/study-hybrid-search-gke && make check-layers` — must exit 0.
- After applying: `cd 7/study-hybrid-search-gke && SEMANTIC_BACKEND=noop LEXICAL_BACKEND=noop make api-dev` then `curl localhost:8000/livez` — must return 200.
- Find any forgotten Port: `rg "class \w+Port" 7/study-hybrid-search-gke/app/services/protocols/ 7/study-hybrid-search-gke/ml/`.
- Confirm composition root is the only `new`-site for the new adapter: `rg "<Backend><Concept>\(" 7/study-hybrid-search-gke/app/`.
