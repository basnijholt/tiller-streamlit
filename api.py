"""JSON API for Tiller Money data."""

from datetime import date, datetime

import pandas as pd
from fastapi import FastAPI, Query
from tiller_streamlit import (
    _to_spending,
    get_balance_history,
    get_categories,
    get_transaction_data_df,
    resampled_balance_history,
)

app = FastAPI(title="Tiller Money API")


def _filter_date_range(
    df: pd.DataFrame, start: date | None, end: date | None
) -> pd.DataFrame:
    if start is not None:
        df = df[df["Date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["Date"] <= pd.Timestamp(end)]
    return df


def _transaction_records(
    df: pd.DataFrame, limit: int, *, lowercase: bool = False
) -> list[dict]:
    df = df.sort_values("Date", ascending=False).head(limit)
    records = df[["Date", "Description", "Category", "Amount", "Account", "Group"]].copy()
    records["Date"] = records["Date"].dt.strftime("%Y-%m-%d")
    records["Amount"] = records["Amount"].round(2)
    if lowercase:
        records = records.rename(
            columns={
                "Date": "date",
                "Description": "description",
                "Category": "category",
                "Amount": "amount",
                "Account": "account",
                "Group": "group",
            }
        )
    return records.to_dict(orient="records")


def _balance_history_records(df: pd.DataFrame) -> list[dict]:
    df = df.sort_values(["Date", "Account"])
    records = df[["Date", "Account", "Balance", "Class"]].copy()
    records["Date"] = records["Date"].dt.strftime("%Y-%m-%d")
    records["Balance"] = records["Balance"].round(2)
    records = records.rename(
        columns={
            "Date": "date",
            "Account": "account",
            "Balance": "balance",
            "Class": "class",
        }
    )
    return records.to_dict(orient="records")


@app.get("/api/summary")
def summary(
    months: int = Query(6, description="Number of recent months to include"),
    transaction_limit: int = Query(
        10, ge=1, le=100, description="Number of recent transactions to include"
    ),
):
    """High-level financial summary: net worth, recent monthly spending, income."""
    df = get_transaction_data_df()
    bal = resampled_balance_history(get_balance_history())

    # Net worth (latest total balance)
    latest_date = bal["Date"].max()
    net_worth = bal[bal["Date"] == latest_date]["Balance"].sum()

    # Account balances
    latest_bal = bal[bal["Date"] == latest_date][["Account", "Balance"]]
    accounts = {
        row["Account"]: round(row["Balance"], 2) for _, row in latest_bal.iterrows()
    }

    # Monthly spending (excluding transfers, investments, taxes)
    spending = _to_spending(df)
    spending["month"] = spending["Date"].dt.to_period("M")
    monthly = spending.groupby("month")["Amount"].sum()
    monthly = monthly.sort_index(ascending=False).head(months)
    spending_by_month = {str(k): round(v, 2) for k, v in monthly.items()}

    # Monthly income
    paycheck = df[df["Category"] == "Paycheck"].copy()
    paycheck["month"] = paycheck["Date"].dt.to_period("M")
    income_monthly = paycheck.groupby("month")["Amount"].sum()
    income_monthly = income_monthly.sort_index(ascending=False).head(months)
    income_by_month = {str(k): round(v, 2) for k, v in income_monthly.items()}

    networth = (
        bal.groupby("Date")["Balance"]
        .sum()
        .reset_index()
        .sort_values("Date", ascending=False)
        .head(months)
        .sort_values("Date")
    )
    networth_history = [
        {"date": row["Date"].strftime("%Y-%m-%d"), "net_worth": round(row["Balance"], 2)}
        for _, row in networth.iterrows()
    ]

    return {
        "as_of": latest_date.isoformat(),
        "net_worth": round(net_worth, 2),
        "accounts": accounts,
        "monthly_spending": spending_by_month,
        "monthly_income": income_by_month,
        "balance_history": networth_history,
        "recent_transactions": _transaction_records(
            df, transaction_limit, lowercase=True
        ),
    }


@app.get("/api/spending")
def spending(
    months: int = Query(12, description="Number of recent months"),
    category: str | None = Query(None, description="Filter by category"),
):
    """Monthly spending breakdown by category."""
    df = get_transaction_data_df()
    sp = _to_spending(df)
    sp["month"] = sp["Date"].dt.to_period("M")

    if category:
        sp = sp[sp["Category"] == category]

    grouped = sp.groupby(["month", "Category"])["Amount"].sum().reset_index()
    grouped = grouped.sort_values("month", ascending=False)

    cutoff = grouped["month"].unique()[:months]
    grouped = grouped[grouped["month"].isin(cutoff)]

    result = {}
    for _, row in grouped.iterrows():
        m = str(row["month"])
        result.setdefault(m, {})[row["Category"]] = round(row["Amount"], 2)

    return result


@app.get("/api/transactions")
def transactions(
    months: int = Query(1, description="Number of recent months"),
    category: str | None = Query(None, description="Filter by category"),
    min_amount: float | None = Query(None, description="Minimum absolute amount"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum records to return"),
):
    """Recent transactions."""
    df = get_transaction_data_df()
    cutoff = datetime.today() - pd.DateOffset(months=months)
    df = df[df["Date"] >= cutoff]

    if category:
        df = df[df["Category"] == category]
    if min_amount is not None:
        df = df[df["Amount"].abs() >= min_amount]

    return _transaction_records(df, limit)


@app.get("/api/recent-transactions")
def recent_transactions(
    limit: int = Query(25, ge=1, le=500, description="Maximum records to return"),
    start: date | None = Query(None, description="Start date, inclusive"),
    end: date | None = Query(None, description="End date, inclusive"),
    category: str | None = Query(None, description="Filter by category"),
    min_amount: float | None = Query(None, description="Minimum absolute amount"),
):
    """Most recent transactions with optional date and category filters."""
    df = get_transaction_data_df()
    df = _filter_date_range(df, start, end)

    if category:
        df = df[df["Category"] == category]
    if min_amount is not None:
        df = df[df["Amount"].abs() >= min_amount]

    return _transaction_records(df, limit, lowercase=True)


@app.get("/api/balances")
def balances():
    """Current account balances and net worth."""
    bal = resampled_balance_history(get_balance_history())
    latest_date = bal["Date"].max()
    latest = bal[bal["Date"] == latest_date][["Account", "Balance", "Class"]]

    accounts = []
    for _, row in latest.iterrows():
        accounts.append(
            {
                "account": row["Account"],
                "balance": round(row["Balance"], 2),
                "class": row["Class"],
            }
        )

    net_worth = sum(a["balance"] for a in accounts)

    return {
        "as_of": latest_date.isoformat(),
        "net_worth": round(net_worth, 2),
        "accounts": accounts,
    }


@app.get("/api/balance-history")
def balance_history(
    account: str | None = Query(None, description="Filter by account name"),
    start: date | None = Query(None, description="Start date, inclusive"),
    end: date | None = Query(None, description="End date, inclusive"),
):
    """Raw balance history snapshots from the Tiller Balance History sheet."""
    bal = get_balance_history()
    bal = _filter_date_range(bal, start, end)

    if account:
        bal = bal[bal["Account"] == account]

    return _balance_history_records(bal)


@app.get("/api/networth-history")
def networth_history(
    freq: str = Query(
        "daily", pattern="^(daily|weekly|monthly)$", description="Aggregation cadence"
    ),
    start: date | None = Query(None, description="Start date, inclusive"),
    end: date | None = Query(None, description="End date, inclusive"),
):
    """Net worth history aggregated server-side as assets minus liabilities."""
    bal = resampled_balance_history(get_balance_history())
    bal = _filter_date_range(bal, start, end)

    networth = bal.groupby("Date")["Balance"].sum().reset_index(name="Net Worth")
    networth = networth.sort_values("Date").set_index("Date")

    if freq == "weekly":
        networth = networth.resample("W-SUN").last().dropna()
    elif freq == "monthly":
        networth = networth.resample("ME").last().dropna()

    networth = networth.reset_index()
    networth["date"] = networth["Date"].dt.strftime("%Y-%m-%d")
    networth["net_worth"] = networth["Net Worth"].round(2)
    return networth[["date", "net_worth"]].to_dict(orient="records")


@app.get("/api/categories")
def categories():
    """List all categories with their groups and types."""
    cat_to_group, group_to_cat, cat_to_type = get_categories()
    return {
        cat: {"group": cat_to_group[cat], "type": cat_to_type[cat]}
        for cat in cat_to_group
    }
