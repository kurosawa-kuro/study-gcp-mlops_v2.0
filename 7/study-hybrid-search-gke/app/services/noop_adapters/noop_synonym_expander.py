"""Null ``SynonymExpanderPort`` — returns query unchanged.

Selected when ``synonym_backend=none`` or ``redis_url`` is empty.
Hybrid retrieval still runs the lexical side; query expansion simply
never happens, matching Phase 5 / 6 behaviour exactly.
"""

from __future__ import annotations

from app.services.protocols.synonym_expander import SynonymExpanderPort


class NoopSynonymExpander(SynonymExpanderPort):
    def expand(self, query: str) -> str:
        return query
