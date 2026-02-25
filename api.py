"""JSON API for Tiller Money data."""

from datetime import datetime

from fastapi import FastAPI, Query
from fastapi.responses import JSONResponse
from tiller_streamlit import (
    get_balance_history,
    get_categories,
    get_transaction_data_df,
    resampled_balance_history,
    _to_spending,
)

app = FastAPI(title="Tiller Money API")


@app.get("/api/summary")
def summary(months: int = Query(6, description="Number of recent months to include")):
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

    return {
        "as_of": latest_date.isoformat(),
        "net_worth": round(net_worth, 2),
        "accounts": accounts,
        "monthly_spending": spending_by_month,
        "monthly_income": income_by_month,
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
):
    """Recent transactions."""
    df = get_transaction_data_df()
    cutoff = datetime.today() - pd.DateOffset(months=months)
    df = df[df["Date"] >= cutoff]

    if category:
        df = df[df["Category"] == category]
    if min_amount is not None:
        df = df[df["Amount"].abs() >= min_amount]

    df = df.sort_values("Date", ascending=False)
    records = df[["Date", "Description", "Category", "Amount", "Account", "Group"]].copy()
    records["Date"] = records["Date"].dt.strftime("%Y-%m-%d")
    records["Amount"] = records["Amount"].round(2)

    return records.to_dict(orient="records")


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


@app.get("/api/categories")
def categories():
    """List all categories with their groups and types."""
    cat_to_group, group_to_cat, cat_to_type = get_categories()
    return {
        cat: {"group": cat_to_group[cat], "type": cat_to_type[cat]}
        for cat in cat_to_group
    }


import pandas as pd  # noqa: E402 (needed for pd.DateOffset in transactions)
