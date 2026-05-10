# TenderSignal

TenderSignal is a local Python + Streamlit MVP for an interview demo with Finnish K Group's building and house technic department. It acts as an AI-assisted public procurement opportunity copilot for building and technical trade, with the first version intentionally built without LLM enrichment.

The app fetches real public procurement notices from TED, filters construction and technical-trade CPV areas, classifies opportunities for Onninen-like technical wholesale and K-Rauta Pro-like professional builder retail, scores each notice, and creates a short source-grounded sales briefing.

## What It Does

- Ingests real notices from the public TED Search API.
- Stores normalized notices and raw source payloads in SQLite.
- Classifies notices with CPV and keyword rules.
- Scores technical trade and pro builder relevance transparently.
- Generates sales briefings using only source fields and deterministic evidence.
- Converts real public Hilma award winners into prospect lists for Onninen/K-Rauta Pro outreach.
- Exports scored opportunities to CSV.
- Provides data reliability visibility, including failed ingestion runs.

## Data Sources

TenderSignal uses only real public procurement data:

- TED Search API, `POST https://api.ted.europa.eu/v3/notices/search`.
- Hilma / Hankintailmoitukset AVP-Read Search Notices, `POST https://api.hankintailmoitukset.fi/avp/eformnotices/docs/search`.

Official documentation:

- [TED API docs](https://docs.ted.europa.eu/api/latest/)
- [TED Search API](https://docs.ted.europa.eu/api/latest/search.html)
- [TED Search API reuse notes](https://docs.ted.europa.eu/ODS/latest/reuse/search-api.html)
- [TED search fields](https://docs.ted.europa.eu/ODS/latest/reuse/field-list.html)
- [Hilma API developer portal](https://hns-hilma-prod-apim.developer.azure-api.net/)
- [Hilma API GitHub documentation](https://github.com/Hankintailmoitukset/hilma-api)

The cache files under `data/cache/` contain real public notice payloads from successful ingestion runs, not synthetic examples.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Ingest Real Notices

```bash
python scripts/ingest_ted.py --days-back 21 --limit 100
```

If the TED API is unavailable or network access fails, the script exits with an error and records a failed ingestion run in SQLite. It does not fabricate fallback notices.

To load the cached real sample instead:

```bash
python scripts/ingest_ted.py --use-cache
```

For production-style 2026 coverage:

```bash
python scripts/ingest_ted.py --year 2026 --limit 10000
HILMA_AVP_SUBSCRIPTION_KEY="..." python scripts/ingest_hilma.py --year 2026 --include-expired --limit 10000
HILMA_AVP_SUBSCRIPTION_KEY="..." python scripts/ingest_hilma_awards.py --days-back 1460
HILMA_AVP_SUBSCRIPTION_KEY="..." python scripts/ingest_winner_leads.py --days-back 1460
```

Or run the combined refresh:

```bash
HILMA_AVP_SUBSCRIPTION_KEY="..." python scripts/refresh_2026.py
```

The Streamlit sidebar also includes a `Refresh 2026 YTD` button. It refreshes TED, Hilma, Hilma award intelligence, and the Hilma winner-lead radar together when `HILMA_AVP_SUBSCRIPTION_KEY` is visible to the Streamlit server process. The publication-date filter lets users analyze all loaded 2026 data or narrow to a current operating window.

## Run The App

```bash
HILMA_AVP_SUBSCRIPTION_KEY="..." python -m streamlit run app/streamlit_app.py --server.port 8502
```

For hosted recruiter demo mode, the key is optional. If `data/tendersignal.sqlite` is missing, the app seeds it on first start from the bundled real public cache in `data/cache/`.

Pages:

- K business radar
- Opportunity map
- Winner lead radar
- Award & competitor intelligence
- Buyer 360
- Today's opportunities
- Category pipeline
- Notice detail / sales brief
- Data reliability
- Export

The `Page` selector is the topmost sidebar control. Each page includes an in-app guide covering what the page is used for, who uses it, business benefit, and next steps. A fuller version is in `docs/page_guide.md`.

Use the sidebar `Analyze source` selector to filter the whole dashboard to `Both sources`, `Hankintailmoitus (Hilma)`, or `TED`.

## Deploy

The app is prepared for Streamlit Community Cloud. Main file:

```text
app/streamlit_app.py
```

Deployment notes are in `docs/deployment.md`. Do not commit live API keys; use Streamlit secrets only if you want hosted live Hilma refresh.

## Export

```bash
python scripts/export_opportunities.py
```

Exports are written to `data/exports/`.

## Scoring Logic

Each relevance score is capped at 100 and is built from visible components:

- CPV match: up to 40 points.
- Keyword match in title/description: up to 25 points.
- Deadline urgency: up to 15 points.
- Location availability: up to 10 points.
- Text confidence: up to 10 points.

The app stores evidence and uncertainties for each notice. Briefings are assembled from title, buyer, country/location, deadline, CPV codes, source description, score evidence, and source URL.

## K Business Lens

TenderSignal derives a business lens for Kesko's building and technical trade using only public notice fields:

- `k_business_lane`: Onninen technical trade, K-Rauta Pro builder retail, or joint B2B opportunity.
- `strategic_demand_signal`: energy transition/electrification, renovation and repair, infrastructure and utilities, public buildings and facilities, site equipment/tools/safety, or general demand.
- `recommended_k_action`: a deterministic routing suggestion based on the lane, source, signal and score.

These fields are heuristics for analyst triage and sales steering; they do not add private customer facts.

## Award And Competitor Intelligence

Hilma award notices can be ingested into a separate `award_notices` table:

```bash
HILMA_AVP_SUBSCRIPTION_KEY="..." python scripts/ingest_hilma_awards.py --days-back 1460
HILMA_AVP_SUBSCRIPTION_KEY="..." python scripts/ingest_winner_leads.py --days-back 1460
```

The award view shows public evidence for named winners such as Onninen and selected competitors. Amounts are public notice/framework values where available, not realized sales. Search noise is filtered out unless the configured supplier name appears in the public `winnerOrganisations` field.

## Winner Lead Radar

Hilma award winners can also be turned into indirect B2B lead signals:

```bash
HILMA_AVP_SUBSCRIPTION_KEY="..." python scripts/ingest_winner_leads.py --days-back 1460
```

This page answers a different commercial question than open tenders: who already won public construction or technical-trade work and may now need materials, logistics, technical supply, or account support. It uses only public `winnerOrganisations`, title, CPV, buyer, date, value, and source URL fields. The ready CRM task and outreach note are deterministic drafts that explicitly ask the user to validate scope from the source notice before contacting anyone.

## Opportunity Map

The Opportunity map page plots active opportunities by city when a city name is present in public source fields and overlays public value signals where source fields actually provide them.

- Dot location uses static Nordic city centroids for matched source-field city names, not invented project coordinates.
- Dot size is fixed so the geography is not distorted by opportunity count or value.
- Active opportunity value is populated only from public amount fields in the notice payload, such as Hilma `estimatedValue`.
- Public award value is Hilma award/framework context from loaded award notices, not expected revenue.
- The table below the map shows value coverage so users can see when values are missing from source data.

## Action Packs

The notice detail page includes a deterministic action pack with:

- CRM task text.
- Sales message.
- Qualification checklist.

These are generated from public notice fields, deterministic scores and loaded award context. Optional small-LLM polishing can be enabled later through the existing `TENDERSIGNAL_ENABLE_LLM`, `TENDERSIGNAL_LLM_PROVIDER=openai` and `TENDERSIGNAL_LLM_MODEL` settings; the default path is zero-cost deterministic text.

## Buyer 360 And Ask This Tender

Buyer 360 combines loaded active opportunities and public award history for one buyer:

- Active opportunities by lane, score and source.
- Public K Group/Onninen award evidence.
- Public competitor award evidence.
- Renewal window indicators from public expiration fields where available.
- Next-best actions for the sales analyst.

The notice detail page also has `Ask this tender`, a deterministic assistant for common questions such as:

- Summarize for Onninen sales.
- Summarize for K-Rauta Pro.
- What should we check before acting?
- What product families might be relevant?
- What is uncertain?
- Draft a short buyer outreach note.

This is designed as a cheap agent layer: deterministic answers are free, and a small LLM can later polish wording while using only the supplied public notice fields.

## Optional LLM Layer

The deterministic pipeline is the default. Optional LLM enrichment is isolated behind `tendersignal.llm.base.OpportunityEnricher`. The default path uses `NullEnricher`, so no LLM is called.

To enable the optional OpenAI implementation:

```bash
pip install -e ".[llm]"
export TENDERSIGNAL_ENABLE_LLM=1
export TENDERSIGNAL_LLM_PROVIDER=openai
export OPENAI_API_KEY="..."
python scripts/ingest_ted.py --use-cache
```

Any future LLM implementation should:

- Use only the normalized notice, raw source fields, evidence, and uncertainties.
- Preserve source URLs and uncertainty statements.
- Avoid adding buyer facts, customer names, values, or requirements unless they exist in the source payload.

## Hilma Extension

Hilma AVP-Read is the official open-data API for Hankintailmoitukset.fi, but it requires self-registration and an `Ocp-Apim-Subscription-Key` header. TenderSignal includes a configured Hilma client in `src/tendersignal/sources/hilma.py`; it fails clearly until `HILMA_AVP_SUBSCRIPTION_KEY` is supplied.

Use environment variables, never hardcode the key:

```bash
export HILMA_AVP_SUBSCRIPTION_KEY="..."
python scripts/ingest_hilma.py --days-back 21 --limit 100
```

The default Hilma Search Notices endpoint is `https://api.hankintailmoitukset.fi/avp/eformnotices/docs/search`. The index definition endpoint is `GET https://api.hankintailmoitukset.fi/avp/eformnotices`.

Official references:

- [Hilma API developer portal](https://hns-hilma-prod-apim.developer.azure-api.net/)
- [Hilma API GitHub documentation](https://github.com/Hankintailmoitukset/hilma-api)

## Sales Territory Mapping

`config/sales_territory_mapping.csv` supports real K Group/Onninen routing rules. It ships empty except for headers so the demo does not invent customers, owners, or territories. See `docs/sales_territory_mapping.md`.

## Limitations

- TED may return NUTS/location codes rather than city names.
- Description language depends on the notice fields returned by TED.
- The classifier is intentionally transparent and deterministic, so it is less nuanced than a domain-tuned model.
- The MVP focuses on opportunity triage, not bid/no-bid automation.
- Notices are only as complete as the source fields returned by TED and Hilma.

## Repository Structure

```text
app/                    Streamlit app
data/cache/             cached real public API payloads after ingestion
data/exports/           CSV exports
docs/                   demo script and supporting docs
scripts/                ingestion and export commands
src/tendersignal/       source adapters, scoring, DB, export, LLM interface
tests/                  deterministic unit tests
```
