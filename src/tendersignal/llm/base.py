from __future__ import annotations

from typing import Protocol

from tendersignal.models import ScoredOpportunity


class OpportunityEnricher(Protocol):
    """Optional enrichment interface.

    Implementations must only use source fields and deterministic evidence passed
    in the opportunity object. The default app path uses no LLM.
    """

    def enrich(self, opportunity: ScoredOpportunity) -> ScoredOpportunity:
        ...
