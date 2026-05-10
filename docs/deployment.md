# TenderSignal Deployment

## Recommended Path: Streamlit Community Cloud

1. Push this repository to GitHub.
2. Create a new Streamlit app from the repository.
3. Set the main file path to:

```text
app/streamlit_app.py
```

4. Deploy without secrets for recruiter demo mode.

The app will create `data/tendersignal.sqlite` on first start from the bundled real public cache files in `data/cache/`. No synthetic notices are generated.

## Optional Live Hilma Refresh

If you want the deployed app to refresh live Hilma data, add this in Streamlit Cloud secrets:

```toml
HILMA_AVP_SUBSCRIPTION_KEY = "..."
```

Do not commit a real key to GitHub.

## What Is Included In The Hosted Demo

- Real cached TED notices from successful API ingestion.
- Real cached Hilma notices from successful API ingestion.
- Real cached Hilma award-search payloads.
- Real cached Hilma winner-lead award payloads.
- Deterministic scoring and sales briefings.
- No LLM calls by default.
- No invented tenders, customers, values, or cities.

## Deployment Checks

Run locally before pushing:

```bash
python -m pytest -q
PYTHONPYCACHEPREFIX=/tmp/tendersignal_pycache python -m compileall -q app src scripts
python -m streamlit run app/streamlit_app.py
```

## Known Hosted Limitations

- Live Hilma refresh is disabled unless a Hilma AVP key is configured in deployment secrets.
- The bundled cache is a point-in-time public-data snapshot, including winner leads from real Hilma award notices. Use live refresh for current operations.
- The city map only plots cities matched from public source fields and a static Nordic city list.
- Map dots are fixed-size markers; opportunity counts and values are shown in tooltips and tables.
