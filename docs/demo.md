# TenderSignal Demo Script

## 1. Open With The Business Problem

"TenderSignal helps a building and house technic sales organization spot relevant public procurement opportunities early, explain why they matter, and route them to the right commercial team."

Emphasize the two target lanes:

- Onninen-like technical wholesale: electrical, telecom, HVAC, plumbing, water systems.
- K-Rauta Pro-like professional builder retail: construction materials, renovation, civil/site works, tools, and site equipment.

## 2. Show Data Reliability First

Open the Data reliability page.

Say:

"This MVP uses real TED and Hankintailmoitus/Hilma public procurement notices. The raw source payload is stored with every normalized opportunity. If an API fails, the run is logged as failed; the system does not create synthetic tenders."

Point out:

- Ingestion run status.
- Completeness of deadline, location, CPV, and descriptions.
- Known limitation that locations can be NUTS codes rather than cities.

## 3. Run Or Load Ingestion

For a live operating refresh, use the sidebar:

- Check that `Hilma live API` says configured.
- Click `Refresh 2026 YTD` to refresh TED notices, Hilma notices, and Hilma award intelligence.

For a smaller live demo refresh, use the sidebar:

- Publication window: 21 days.
- Max notices: 100.
- Use cached sample: off if network is available, on if offline.
- Click Ingest notices.

If asked about the source:

"The TED request is an expert query combining publication date, competition notice types, buyer countries, and construction/technical CPV prefixes. The Hilma request uses the official AVP-Read search endpoint and the same deterministic classification layer after normalization."

## 4. K Business Radar

Open K business radar.

Say:

"This is the senior analyst view. It translates public notices into K Group business lanes: Onninen technical trade, K-Rauta Pro builder retail, or a joint B2B opportunity. The source filter lets us look separately at Hankintailmoitus or TED."

Point to:

- Sales action queue.
- Demand signals.
- Business lanes.
- Buyer intelligence.

## 5. Opportunity Map

Open Opportunity map.

Say:

"This is the wow view, but it stays honest. The dots are city-level only when a city name is present in the public source fields. Dot size is fixed so geography is not distorted. Values are shown only where the public source returns a value field; otherwise the app shows value coverage instead of inventing euro amounts."

Point to:

- mapped opportunity count
- Act now count
- active public value coverage
- Hilma public award value context
- city table under the map

## 6. Award & Competitor Intelligence

Open Award & competitor intelligence.

Say:

"This is the market-position view. It reads public Hilma award notices and separates direct K Group/Onninen evidence from named competitor evidence. The amounts are public notice or framework values where available, not realized sales."

Point to:

- Supplier benchmark.
- K Group / Onninen public awards.
- Competitor watch.
- Renewal watch based on public expiration fields when available.

## 7. Buyer 360

Open Buyer 360.

Say:

"This is the account-intelligence view. It combines active opportunities and public award history for a selected buyer, then proposes next-best analyst actions."

Point to:

- active opportunities
- K Group and competitor award rows
- public value where available
- renewal window
- next best actions

## 8. Today's Opportunities

Open Today's opportunities.

Explain:

"This is a triage queue. The best opportunities rise because they have matching CPV codes, matching terms in title or description, usable deadlines, source location, and enough text to brief a salesperson."

Point to:

- Technical trade score.
- Pro builder score.
- Recommended sales action.
- TED/Hankintailmoitus source link.

## 9. Category Pipeline

Open Category pipeline.

Say:

"This view is for sales management. It shows where the current public procurement pipeline clusters: electrical, HVAC, building materials, civil works, or tools and equipment."

Mention:

"The model is explainable enough for a senior data analyst demo: the score is not a black box, and each opportunity includes evidence and uncertainty."

## 10. Notice Detail / Sales Brief

Open a high-scoring notice.

Read the brief structure:

- Buyer and location from TED fields.
- Deadline from TED deadline field.
- Source description excerpt.
- CPV codes.
- Recommended sales action.
- Evidence and uncertainties.

Say:

"The briefing deliberately avoids hallucinated facts. It does not invent customer history, contract value, or requirements."

In the action pack expander, show:

- CRM task text.
- Sales message.
- Qualification checklist.

Say:

"This is where a cheap LLM could help: not by inventing tender facts, but by polishing these deterministic action outputs into CRM-ready or email-ready language."

In Ask this tender, show:

- Summarize for Onninen sales.
- What should we check before acting?
- Draft a short buyer outreach note.

Say:

"This is the assistant pattern I would use: deterministic first, optional cheap LLM only for wording."

## 11. Export

Open Export and create/download CSV.

Say:

"This makes the MVP immediately useful for sales operations: scored opportunities can be handed to account managers, imported into CRM, or reviewed in Excel."

## 12. Close With Next Steps

Implemented extension hooks:

- Hilma-specific ingestion uses official AVP-Read and requires the API key in `HILMA_AVP_SUBSCRIPTION_KEY`.
- Named account mapping is config-driven via `config/sales_territory_mapping.csv`; the file is intentionally blank until real internal rules are added.
- Tender document links are harvested only from source fields and TED links.
- Optional LLM enrichment is behind the existing interface and disabled unless explicitly configured.

Future extensions:

- Track outcomes to calibrate score weights from real bid/no-bid and win/loss decisions.
- Add procurement portal document downloads only where the portal permits automated access.
