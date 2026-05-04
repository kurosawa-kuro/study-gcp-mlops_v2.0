"""Promote a Vertex Model Registry version (Phase 7 / KServe alias mode).

Assigns the ``production`` alias to a target Model version. This is what
``scripts.deploy.kserve_models`` reads to pick which artifact_uri to wire
into the InferenceService. No Vertex Endpoint is deployed (Phase 7
serves via KServe).

Reranker artifact compatibility (Phase 7 KServe LGBServer note)
---------------------------------------------------------------
KServe's stock ``lgbserver:v0.14`` runtime accepts only files ending
with ``.bst`` (see ``MODEL_EXTENSIONS`` in lgbserver's source). The
training pipeline writes ``model.txt`` (LightGBM Booster's default
text format). With ``--bst-rename`` the promote step copies
``model.txt`` → ``model.bst`` in the artifact_uri location so KServe
can load the model on the next ``deploy-kserve-models``. The bytes
are identical — only the extension changes.

Empty-artifact_uri guard
------------------------
If the resolved version's artifact_uri does not actually contain any
files in GCS (the Phase 7 Run 1 ``gs://.../reranker/v1/`` regression),
the script fails fast with a hint to pick a different version, instead
of letting the Pod crashloop later.

Usage
-----
::

    PROJECT_ID=mlops-dev-a make ops-promote-reranker VERSION_ID=1 APPLY=1
    PROJECT_ID=mlops-dev-a make ops-promote-encoder  VERSION_ID=1 APPLY=1

    # With .bst rename for reranker (run once after a fresh train)
    PROJECT_ID=mlops-dev-a make ops-promote-reranker VERSION_ID=1 BST_RENAME=1 APPLY=1
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from typing import Any

from scripts._common import env, fail


def _log(msg: str) -> None:
    print(f"[promote] {msg}", flush=True)


def _resolve_display_name(model_kind: str) -> str:
    """Return the **Model Registry display_name** that ``aiplatform.Model.list``
    filters on.

    This is *not* the Endpoint display name (``property-*-endpoint``). The
    distinction matters because the train pipeline registers Models with
    ``model_display_name="property-reranker"`` / ``"property-encoder"``
    (see ``pipeline/training_job/main.py``), while Terraform creates
    Endpoint *shells* with the ``-endpoint`` suffix. Setting
    ``RERANKER_ENDPOINT_DISPLAY_NAME`` (the old Phase 5/6 ops env) here
    would silently match zero Models.
    """
    return {
        "reranker": env("RERANKER_MODEL_DISPLAY_NAME", "property-reranker"),
        "encoder": env("ENCODER_MODEL_DISPLAY_NAME", "property-encoder"),
    }[model_kind]


def _list_versions(display_name: str) -> list[Any]:
    from google.cloud import aiplatform

    return list(aiplatform.Model.list(filter=f'display_name="{display_name}"'))


def _model_id_of(m: Any) -> str:
    rn = getattr(m, "resource_name", "") or ""
    return rn.rsplit("/", 1)[-1] if rn else ""


def _select_version(
    models: list[Any],
    *,
    version_id: str | None,
    version_alias: str | None,
    model_id: str | None = None,
) -> Any:
    """Pick the model whose selector matches.

    The aiplatform SDK returns one Model object per *registered model
    resource* — when each train upload created a new Model rather than
    a new version of an existing one (the ``mlops-dev-a`` reality), we
    end up with multiple objects sharing ``version_id=1``. The
    ``--model-id`` selector disambiguates between them; ``--version-id``
    is kept for the simple case.

    When neither selector matches we error out instead of guessing —
    silent ``[0]`` selection was the Run 1 footgun that promoted an
    empty-URI version.
    """
    for m in models:
        if model_id is not None and _model_id_of(m) == str(model_id):
            return m
    for m in models:
        vid = str(getattr(m, "version_id", ""))
        aliases = list(getattr(m, "version_aliases", []) or [])
        if version_id is not None and vid == str(version_id):
            return m
        if version_alias is not None and version_alias in aliases:
            return m
    selectors = []
    if model_id is not None:
        selectors.append(f"model_id={model_id!r}")
    if version_id is not None:
        selectors.append(f"version_id={version_id!r}")
    if version_alias is not None:
        selectors.append(f"version_alias={version_alias!r}")
    raise RuntimeError(
        f"no Model matched [{', '.join(selectors) or 'none'}]; "
        f"candidates: {[(_model_id_of(m), m.version_id, m.version_aliases, m.uri) for m in models]}"
    )


def _gsutil_ls(uri: str) -> list[str]:
    """List GCS object names under ``uri``. Empty list on no objects."""
    proc = subprocess.run(["gsutil", "ls", uri], capture_output=True, text=True, check=False)
    if proc.returncode != 0:
        # Treat "no objects" as empty rather than fatal — caller decides.
        return []
    return [line.strip() for line in proc.stdout.splitlines() if line.strip()]


def _bst_rename_if_needed(artifact_uri: str, *, apply: bool) -> str | None:
    """If a `.txt` exists at ``artifact_uri`` but no `.bst`, copy it.

    Returns the URI of the `.bst` file (existing or newly created), or
    None if neither candidate file is found.
    """
    listing = _gsutil_ls(artifact_uri)
    txt = next((u for u in listing if u.endswith("model.txt")), None)
    bst = next((u for u in listing if u.endswith("model.bst")), None)
    if bst:
        _log(f"  .bst already present: {bst}")
        return bst
    if not txt:
        _log(f"  WARN no model.txt at {artifact_uri} — cannot rename")
        return None
    target = txt[: -len("model.txt")] + "model.bst"
    if not apply:
        _log(f"  PLAN gsutil cp {txt} {target}")
        return target
    _log(f"  RUN  gsutil cp {txt} {target}")
    proc = subprocess.run(
        ["gsutil", "cp", txt, target], capture_output=True, text=True, check=False
    )
    if proc.returncode != 0:
        raise RuntimeError(f"gsutil cp failed: {proc.stderr.strip()}")
    return target


def _set_production_alias(target: Any, others: list[Any], *, apply: bool) -> None:
    """Move the ``production`` alias to ``target``, removing it from siblings."""
    for m in others:
        if m is target:
            continue
        if "production" in (getattr(m, "version_aliases", []) or []):
            _log(f"  removing 'production' from version_id={m.version_id}")
            if apply:
                m.versioning_registry.remove_version_aliases(
                    target_aliases=["production"], version=str(m.version_id)
                )
    _log(f"  adding 'production' to version_id={target.version_id}")
    if apply:
        target.versioning_registry.add_version_aliases(
            new_aliases=["production"], version=str(target.version_id)
        )


def _run_alias(args: argparse.Namespace) -> dict[str, Any]:
    project_id = env("PROJECT_ID")
    location = env("VERTEX_LOCATION", env("REGION", "asia-northeast1"))
    if not project_id:
        raise RuntimeError("PROJECT_ID is required")

    from google.cloud import aiplatform

    aiplatform.init(project=project_id, location=location)

    display_name = _resolve_display_name(args.model_kind)
    models = _list_versions(display_name)
    if not models:
        raise RuntimeError(f"no Model registered with display_name={display_name!r}")

    target = _select_version(
        models,
        version_id=args.version_id,
        version_alias=args.version_alias,
        model_id=args.model_id,
    )
    artifact_uri = (getattr(target, "uri", "") or "").rstrip("/") + "/"
    _log(
        f"target: display_name={display_name} version_id={target.version_id} "
        f"existing_aliases={list(target.version_aliases or [])} artifact_uri={artifact_uri}"
    )

    listing = _gsutil_ls(artifact_uri)
    _log(f"  artifact_uri listing: {len(listing)} object(s)")
    for u in listing[:10]:
        _log(f"    {u}")
    if not listing:
        raise RuntimeError(
            f"artifact_uri {artifact_uri!r} is empty in GCS. "
            f"Pick a version_id pointing to a populated bucket "
            f"(see `make ops-vertex-models-list`) or run train + register first."
        )

    bst_uri: str | None = None
    if args.bst_rename and args.model_kind == "reranker":
        bst_uri = _bst_rename_if_needed(artifact_uri, apply=args.apply)
        if bst_uri is None:
            raise RuntimeError(
                f"artifact_uri {artifact_uri!r} has neither model.txt nor model.bst — "
                f"KServe LGBServer cannot load this version"
            )

    _set_production_alias(target, models, apply=args.apply)
    if not args.apply:
        _log("DRY RUN — pass --apply to commit changes")

    return {
        "model_kind": args.model_kind,
        "display_name": display_name,
        "selected_version_id": target.version_id,
        "artifact_uri": artifact_uri,
        "bst_uri": bst_uri,
        "applied": bool(args.apply),
        "next_step": (
            "make deploy-kserve-models  # picks up the production alias"
            if args.apply
            else "rerun with APPLY=1 to commit"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Promote a Vertex Model Registry version")
    parser.add_argument("model_kind", choices=["reranker", "encoder"])
    parser.add_argument(
        "--version-id",
        default=None,
        help="explicit Vertex Model Registry version_id (preferred selector)",
    )
    parser.add_argument(
        "--version-alias",
        default=None,
        help="select by an existing version alias (e.g. 'staging')",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help=(
            "Vertex Model resource numeric id (trailing component of "
            "projects/.../models/<id>). Use this when multiple Model resources "
            "share the same display_name (the mlops-dev-a default — every "
            "register creates a new Model rather than a new version)."
        ),
    )
    parser.add_argument(
        "--bst-rename",
        action="store_true",
        help="reranker only: copy model.txt → model.bst in artifact_uri (KServe LGBServer)",
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    try:
        result = _run_alias(args)
    except Exception as exc:
        return fail(f"promote failed: {exc}")

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
