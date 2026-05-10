# Extension Notes

## Hilma Ingestion

Verified public references show that Hankintailmoitukset.fi has an official API developer portal. AVP-Read is for fetching open data from Hankintailmoitukset.fi, is free to use, allows commercial usage, and requires an API subscription key in the `Ocp-Apim-Subscription-Key` header.

TenderSignal includes `tendersignal.sources.hilma.HilmaClient`, but it deliberately fails until a real subscription key is configured. This prevents a demo from silently substituting TED data or synthetic Hilma notices.

Environment variables:

```bash
export HILMA_AVP_SUBSCRIPTION_KEY="..."
python scripts/ingest_hilma.py --days-back 21 --limit 100
```

Defaults:

- Base URL: `https://api.hankintailmoitukset.fi`
- Search endpoint: `/avp/eformnotices/docs/search`
- Index definition endpoint: `/avp/eformnotices`

## Named Account And Territory Mapping

Use `config/sales_territory_mapping.csv`. The file is blank by design. Add only real internal account, segment, territory, or owner mappings.

## Tender Documents

TED document, PDF, XML, buyer profile, and contract URLs are collected into `document_links`. Procurement platforms may still require registration or login. TenderSignal exposes links but does not bypass portal permissions.

## Optional LLM Enrichment

The OpenAI enricher is opt-in and source-constrained. It receives only the normalized source fields, deterministic evidence, and uncertainty list. It is disabled unless:

```bash
export TENDERSIGNAL_ENABLE_LLM=1
export TENDERSIGNAL_LLM_PROVIDER=openai
export OPENAI_API_KEY="..."
```

Install with:

```bash
pip install -e ".[llm]"
```
