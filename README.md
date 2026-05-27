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

### API Index

```http
GET /api
```

Returns a compact map of the high-level concepts exposed by the API.

### Dashboard

```http
GET /api/dashboard?months=6&top_categories=8&transaction_limit=10
```

Returns the main dashboard concepts in one response: current net worth, account balances, monthly spending with 3/6/12-month moving averages, monthly income, top spending categories, compact net worth history, and recent transactions.

### Summary

```http
GET /api/summary?months=6&transaction_limit=10
```

Returns current net worth, current account balances, recent monthly spending, recent monthly income, compact net worth history, and recent transactions.

### Monthly Spending

```http
GET /api/monthly-spending?months=24
GET /api/monthly-spending?months=24&moving_average=3&moving_average=6
GET /api/monthly-spending?months=24&exclude_category=Taxes&exclude_category=Shopping
```

Returns monthly total spending with optional moving averages. By default this excludes `Taxes`, matching the Streamlit monthly spending charts.

### Spending By Category

```http
GET /api/spending?months=12
GET /api/spending?months=12&category=Groceries
GET /api/spending-by-category?months=12&moving_average_months=3
```

Returns monthly spending grouped by category. `/api/spending` is the older compact map response. `/api/spending-by-category` returns a richer month list with totals, category groups, and optional per-category moving averages.

Spending excludes transfers, investment categories, and credit card payments. The newer high-level spending endpoints also exclude `Taxes` by default unless you pass an explicit `exclude_category` list.

### Comparative Spending

```http
GET /api/comparative-spending?previous_months=3
```

Returns cumulative day-by-day spending series for the current month and previous months, matching the comparative spending chart concept.

### Spending Composition

```http
GET /api/spending-composition
GET /api/spending-composition?year=2026&month=5
GET /api/spending-composition?year=2026&month=5&group_by=group
```

Returns category or group spending shares for a selected month/year. This is the data equivalent of the total spending pie/sunburst section.

### Category Histogram

```http
GET /api/category-histogram?category=Shopping&bins=30
GET /api/category-histogram?category=Groceries&start=2026-01-01&end=2026-05-24
```

Returns transaction amount summary statistics and histogram bins for one category.

### Monthly Income

```http
GET /api/monthly-income?months=24
GET /api/monthly-income?months=24&category=Paycheck
```

Returns monthly income totals for the selected income category.

### Transactions

```http
GET /api/transactions?months=1&limit=100
GET /api/transactions?months=1&account=Checking&limit=100&offset=100
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

### Account Balance History

```http
GET /api/account-balance-history?months=24
GET /api/account-balance-history?months=24&exclude_account=Checking
```

Returns monthly total and per-account balances for the monthly account balance chart.

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
