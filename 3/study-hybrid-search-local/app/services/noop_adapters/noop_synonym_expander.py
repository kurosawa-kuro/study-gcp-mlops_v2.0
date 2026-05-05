"""Null ``SynonymExpanderPort`` — returns query unchanged.

Selected when ``synonym_backend=none`` or the Redis URL is empty.
Hybrid retrieval still runs the lexical side; query expansion simply
never happens, matching the pre-Wave 5 Phase 3 behaviour.
"""

from __future__ import annotations

from app.services.protocols.synonym_expander import SynonymExpanderPort


class NoopSynonymExpander(SynonymExpanderPort):
    def expand(self, query: str) -> str:
        return query
