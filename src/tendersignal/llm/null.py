from __future__ import annotations

from tendersignal.llm.base import OpportunityEnricher
from tendersignal.models import ScoredOpportunity


class NullEnricher(OpportunityEnricher):
    def enrich(self, opportunity: ScoredOpportunity) -> ScoredOpportunity:
        return opportunity
