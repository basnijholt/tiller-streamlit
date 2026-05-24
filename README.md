# Tiller Streamlit

Streamlit dashboard and JSON API for a Tiller Money spreadsheet.

The stack serves two containers:

- `tiller-streamlit`: Streamlit UI on port `8501`
- `tiller-api`: FastAPI JSON API on port `8502`

Traefik routes both through the same hostname:

- UI: `http://money.local` or `https://money.lab.nijho.lt`
- API: `http://money.local/api/...` or `https://money.lab.nijho.lt/api/...`

## Configuration

The app reads Tiller data live from Google Sheets. It does not use a local CSV or database cache.

Required environment variables:

```bash
SERVICE_ACCOUNT_FILE=/app/path/to/service-account.json
SCOPES=https://www.googleapis.com/auth/spreadsheets.readonly
SPREADSHEET_ID=...
DOMAIN=lab.nijho.lt
```

Create a Google Cloud service account, download its JSON key, and share the Tiller spreadsheet with the service account email. The compose stack passes these values from `.env` into both containers.

Expected Tiller tabs:

- `Transactions`
- `Categories`
- `Balance History`

The Balance History reader expects the standard Tiller shape, including `Date`, `Account`, `Account ID`, `Class`, and `Balance`. Extra columns are preserved by the dataframe loader but not all are returned by the API.

## API

### Summary

```http
GET /api/summary?months=6&transaction_limit=10
```

Returns current net worth, current account balances, recent monthly spending, recent monthly income, compact net worth history, and recent transactions.

### Spending

```http
GET /api/spending?months=12
GET /api/spending?months=12&category=Groceries
```

Returns monthly spending grouped by category. Spending excludes transfers, investment categories, and credit card payments.

### Transactions

```http
GET /api/transactions?months=1&limit=100
GET /api/recent-transactions?limit=25&start=2026-01-01&end=2026-05-24
```

`/api/transactions` is the older endpoint and keeps its original capitalized field names for compatibility.

`/api/recent-transactions` is the newer endpoint and returns lowercase fields:

```json
[
  {
    "date": "2026-05-12",
    "description": "Example",
    "category": "Groceries",
    "amount": -42.5,
    "account": "Checking",
    "group": "Living"
  }
]
```

### Current Balances

```http
GET /api/balances
```

Returns latest account balances and total net worth.

### Balance History

```http
GET /api/balance-history
GET /api/balance-history?account=Checking&start=2026-01-01&end=2026-05-24
```

Returns raw cleaned Balance History rows:

```json
[
  {
    "date": "2026-05-24",
    "account": "Checking",
    "balance": 1234.56,
    "class": "Asset"
  }
]
```

### Net Worth History

```http
GET /api/networth-history?freq=daily
GET /api/networth-history?freq=weekly&start=2026-01-01
GET /api/networth-history?freq=monthly&start=2026-01-01&end=2026-05-24
```

Returns server-side net worth history as assets minus liabilities:

```json
[
  {
    "date": "2026-05-24",
    "net_worth": 1234567.89
  }
]
```

Allowed `freq` values:

- `daily`
- `weekly`
- `monthly`

### Categories

```http
GET /api/categories
```

Returns category metadata from the Tiller Categories tab.

## Operations

This stack is managed by compose-farm from `/opt/stacks`. Do not run `docker compose` directly.

Restart after source-only changes:

```bash
cf restart tiller-streamlit
```

Rebuild and recreate the API image:

```bash
cf compose tiller-streamlit up -d --build api
```

Check status:

```bash
cf compose tiller-streamlit ps
```

View logs:

```bash
cf logs tiller-streamlit
```

Quick API checks:

```bash
curl -s 'http://money.local/api/networth-history?freq=monthly&start=2026-01-01'
curl -s 'http://money.local/api/recent-transactions?limit=5'
```

## Development Notes

The compose file bind-mounts this directory into `/app`, so Python source edits are visible inside the running containers after a restart. Rebuild when you want the image itself to include the current source, or after dependency and Dockerfile changes.
