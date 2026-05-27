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

DEFAULT_SPENDING_EXCLUDED_CATEGORIES = ("Taxes",)


def _money(value: float | int | None) -> float | None:
    if value is None or pd.isna(value):
        return None
    return round(float(value), 2)


def _filter_date_range(
    df: pd.DataFrame, start: date | None, end: date | None
) -> pd.DataFrame:
    if start is not None:
        df = df[df["Date"] >= pd.Timestamp(start)]
    if end is not None:
        df = df[df["Date"] <= pd.Timestamp(end)]
    return df


def _category_metadata() -> dict[str, dict[str, str]]:
    cat_to_group, group_to_cat, cat_to_type = get_categories()
    return {
        category: {"group": cat_to_group[category], "type": cat_to_type[category]}
        for category in cat_to_group
    }


def _excluded_categories(exclude_category: list[str] | None) -> list[str]:
    if exclude_category is None:
        return list(DEFAULT_SPENDING_EXCLUDED_CATEGORIES)
    return exclude_category


def _spending_df(
    transaction_data: pd.DataFrame,
    *,
    start: date | None = None,
    end: date | None = None,
    exclude_category: list[str] | None = None,
) -> pd.DataFrame:
    df = _to_spending(transaction_data)
    df = _filter_date_range(df, start, end)
    excluded = _excluded_categories(exclude_category)
    if excluded:
        df = df[~df["Category"].isin(excluded)]
    df = df.copy()
    df["month"] = df["Date"].dt.to_period("M")
    return df


def _recent_month_filter(df: pd.DataFrame, months: int) -> pd.DataFrame:
    if df.empty:
        return df
    recent_months = sorted(df["month"].dropna().unique(), reverse=True)[:months]
    return df[df["month"].isin(recent_months)]


def _monthly_income_df(
    transaction_data: pd.DataFrame,
    *,
    months: int,
    category: str = "Paycheck",
) -> pd.DataFrame:
    df = transaction_data[transaction_data["Category"] == category].copy()
    if df.empty:
        return pd.DataFrame(columns=["month", "income"])

    df["month"] = df["Date"].dt.to_period("M")
    df = _recent_month_filter(df, months)
    monthly = (
        df.groupby("month")["Amount"]
        .sum()
        .reset_index(name="income")
        .sort_values("month")
    )
    return monthly


def _monthly_spending_df(
    spending: pd.DataFrame,
    *,
    months: int,
    moving_averages: list[int] | None = None,
    exclude_incomplete_month: bool = True,
) -> pd.DataFrame:
    if spending.empty:
        return pd.DataFrame(columns=["month", "spending"])

    monthly = (
        spending.groupby("month")["Amount"]
        .sum()
        .reset_index(name="spending")
        .sort_values("month")
    )
    monthly = _recent_month_filter(monthly, months).sort_values("month")

    if not moving_averages:
        return monthly

    average_source = monthly.copy()
    current_month = pd.Timestamp.today().to_period("M")
    if exclude_incomplete_month:
        average_source = average_source[average_source["month"] != current_month]

    for window in moving_averages:
        if window > 0:
            average_source[f"moving_average_{window}"] = (
                average_source["spending"].rolling(window=window).mean()
            )

    return monthly.merge(average_source.drop(columns=["spending"]), on="month", how="left")


def _month_record(month: pd.Period) -> str:
    return str(month)


def _transaction_records(
    df: pd.DataFrame, limit: int, *, offset: int = 0, lowercase: bool = False
) -> list[dict]:
    df = df.sort_values("Date", ascending=False).iloc[offset : offset + limit]
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


@app.get("/api")
def api_index():
    """Discover high-level API concepts."""
    return {
        "concepts": {
            "dashboard": "/api/dashboard",
            "summary": "/api/summary",
            "net_worth": ["/api/balances", "/api/networth-history"],
            "account_balances": ["/api/balances", "/api/account-balance-history"],
            "monthly_spending": "/api/monthly-spending",
            "spending_by_category": ["/api/spending", "/api/spending-by-category"],
            "comparative_spending": "/api/comparative-spending",
            "spending_composition": "/api/spending-composition",
            "category_histogram": "/api/category-histogram",
            "monthly_income": "/api/monthly-income",
            "transactions": ["/api/transactions", "/api/recent-transactions"],
            "categories": "/api/categories",
        }
    }


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


@app.get("/api/dashboard")
def dashboard(
    months: int = Query(6, ge=1, le=60, description="Recent months to include"),
    top_categories: int = Query(
        8, ge=1, le=50, description="Number of top spending categories"
    ),
    transaction_limit: int = Query(
        10, ge=1, le=100, description="Number of recent transactions"
    ),
):
    """One response for the main dashboard concepts."""
    transaction_data = get_transaction_data_df()
    spending = _spending_df(transaction_data)
    balance_data = resampled_balance_history(get_balance_history())

    latest_date = balance_data["Date"].max()
    latest_balances = balance_data[balance_data["Date"] == latest_date].copy()

    accounts = [
        {
            "account": row["Account"],
            "balance": _money(row["Balance"]),
            "class": row["Class"],
        }
        for _, row in latest_balances.sort_values("Balance", ascending=False).iterrows()
    ]
    net_worth = _money(latest_balances["Balance"].sum())

    monthly_spending = _monthly_spending_df(
        spending, months=months, moving_averages=[3, 6, 12]
    )
    monthly_income = _monthly_income_df(transaction_data, months=months)

    recent_spending = _recent_month_filter(spending, months)
    categories = (
        recent_spending.groupby(["Category", "Group"])["Amount"]
        .sum()
        .reset_index(name="spending")
        .sort_values("spending", ascending=False)
        .head(top_categories)
    )
    total_spending = recent_spending["Amount"].sum()

    net_worth_history = (
        balance_data.groupby("Date")["Balance"]
        .sum()
        .reset_index(name="net_worth")
        .sort_values("Date")
        .set_index("Date")
        .resample("ME")
        .last()
        .dropna()
        .reset_index()
        .tail(months)
    )

    return {
        "as_of": latest_date.strftime("%Y-%m-%d"),
        "net_worth": net_worth,
        "accounts": accounts,
        "monthly_spending": [
            {
                "month": _month_record(row["month"]),
                "spending": _money(row["spending"]),
                "moving_averages": {
                    col.removeprefix("moving_average_"): _money(row[col])
                    for col in monthly_spending.columns
                    if col.startswith("moving_average_")
                },
            }
            for _, row in monthly_spending.iterrows()
        ],
        "monthly_income": [
            {"month": _month_record(row["month"]), "income": _money(row["income"])}
            for _, row in monthly_income.iterrows()
        ],
        "top_spending_categories": [
            {
                "category": row["Category"],
                "group": row["Group"],
                "spending": _money(row["spending"]),
                "percent": _money(row["spending"] / total_spending * 100)
                if total_spending
                else None,
            }
            for _, row in categories.iterrows()
        ],
        "net_worth_history": [
            {
                "date": row["Date"].strftime("%Y-%m-%d"),
                "net_worth": _money(row["net_worth"]),
            }
            for _, row in net_worth_history.iterrows()
        ],
        "recent_transactions": _transaction_records(
            transaction_data, transaction_limit, lowercase=True
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


@app.get("/api/monthly-spending")
def monthly_spending(
    months: int = Query(24, ge=1, le=240, description="Recent months to include"),
    moving_average: list[int] | None = Query(
        None,
        description="Repeatable moving-average windows, e.g. moving_average=3&moving_average=6",
    ),
    exclude_category: list[str] | None = Query(
        None,
        description="Repeatable categories to exclude. Defaults to Taxes.",
    ),
):
    """Monthly total spending with optional moving averages."""
    transaction_data = get_transaction_data_df()
    spending = _spending_df(
        transaction_data, exclude_category=_excluded_categories(exclude_category)
    )
    monthly = _monthly_spending_df(
        spending,
        months=months,
        moving_averages=moving_average,
        exclude_incomplete_month=True,
    )

    moving_average_columns = [
        column for column in monthly.columns if column.startswith("moving_average_")
    ]
    return {
        "excluded_categories": _excluded_categories(exclude_category),
        "months": [
            {
                "month": _month_record(row["month"]),
                "spending": _money(row["spending"]),
                "moving_averages": {
                    column.removeprefix("moving_average_"): _money(row[column])
                    for column in moving_average_columns
                },
            }
            for _, row in monthly.iterrows()
        ],
    }


@app.get("/api/spending-by-category")
def spending_by_category(
    months: int = Query(12, ge=1, le=120, description="Recent months to include"),
    moving_average_months: int | None = Query(
        None, ge=2, le=24, description="Optional moving-average window per category"
    ),
    exclude_category: list[str] | None = Query(
        None,
        description="Repeatable categories to exclude. Defaults to Taxes.",
    ),
):
    """Monthly spending by category, matching the Streamlit category chart concept."""
    transaction_data = get_transaction_data_df()
    spending = _spending_df(
        transaction_data, exclude_category=_excluded_categories(exclude_category)
    )
    spending = _recent_month_filter(spending, months)

    if spending.empty:
        return {"excluded_categories": _excluded_categories(exclude_category), "months": []}

    grouped = (
        spending.groupby(["month", "Category", "Group"])["Amount"]
        .sum()
        .reset_index(name="spending")
        .sort_values(["Category", "month"])
    )
    if moving_average_months:
        grouped["moving_average"] = grouped.groupby("Category")["spending"].transform(
            lambda values: values.rolling(window=moving_average_months, min_periods=1).mean()
        )

    grouped = grouped.sort_values(["month", "spending"], ascending=[True, False])
    response_months = []
    for month, month_rows in grouped.groupby("month", sort=True):
        response_months.append(
            {
                "month": _month_record(month),
                "total_spending": _money(month_rows["spending"].sum()),
                "categories": [
                    {
                        "category": row["Category"],
                        "group": row["Group"],
                        "spending": _money(row["spending"]),
                        **(
                            {"moving_average": _money(row["moving_average"])}
                            if moving_average_months
                            else {}
                        ),
                    }
                    for _, row in month_rows.iterrows()
                ],
            }
        )

    return {
        "excluded_categories": _excluded_categories(exclude_category),
        "moving_average_months": moving_average_months,
        "months": response_months,
    }


@app.get("/api/spending-composition")
def spending_composition(
    months: int | None = Query(
        None,
        ge=1,
        le=240,
        description="Recent months to include before optional calendar filters",
    ),
    year: int | None = Query(None, ge=1900, le=3000, description="Calendar year"),
    month: int | None = Query(None, ge=1, le=12, description="Calendar month"),
    group_by: str = Query(
        "category",
        pattern="^(category|group)$",
        description="Composition level",
    ),
    exclude_category: list[str] | None = Query(
        None,
        description="Repeatable categories to exclude. Defaults to Taxes.",
    ),
):
    """Spending composition for a month/year as category or group shares."""
    transaction_data = get_transaction_data_df()
    spending = _spending_df(
        transaction_data, exclude_category=_excluded_categories(exclude_category)
    )
    if months is not None:
        spending = _recent_month_filter(spending, months)
    if year is not None:
        spending = spending[spending["Date"].dt.year == year]
    if month is not None:
        spending = spending[spending["Date"].dt.month == month]

    column = "Category" if group_by == "category" else "Group"
    grouped = (
        spending.groupby(column)["Amount"]
        .sum()
        .reset_index(name="spending")
        .sort_values("spending", ascending=False)
    )
    total = grouped["spending"].sum()

    return {
        "months": months,
        "year": year,
        "month": month,
        "group_by": group_by,
        "excluded_categories": _excluded_categories(exclude_category),
        "total_spending": _money(total),
        "items": [
            {
                group_by: row[column],
                "spending": _money(row["spending"]),
                "percent": _money(row["spending"] / total * 100) if total else None,
            }
            for _, row in grouped.iterrows()
        ],
    }


@app.get("/api/comparative-spending")
def comparative_spending(
    previous_months: int = Query(
        3, ge=1, le=24, description="Previous months to compare with current month"
    ),
    exclude_category: list[str] | None = Query(
        None,
        description="Repeatable categories to exclude. Defaults to Taxes.",
    ),
):
    """Cumulative day-by-day spending comparison across recent months."""
    transaction_data = get_transaction_data_df()
    spending = _spending_df(
        transaction_data, exclude_category=_excluded_categories(exclude_category)
    )
    if spending.empty:
        return {
            "anchor_month": None,
            "previous_months": previous_months,
            "series": [],
        }

    anchor_month = spending["month"].max()
    months = [anchor_month - offset for offset in range(previous_months, -1, -1)]
    spending = spending[spending["month"].isin(months)].copy()
    spending["day"] = spending["Date"].dt.day
    daily = (
        spending.groupby(["month", "day"])["Amount"]
        .sum()
        .reset_index(name="spending")
        .sort_values(["month", "day"])
    )
    daily["cumulative_spending"] = daily.groupby("month")["spending"].cumsum()

    series = []
    for month, month_rows in daily.groupby("month", sort=True):
        months_ago = (anchor_month - month).n
        label = (
            f"This Month, {month}"
            if months_ago == 0
            else f"{months_ago} months ago, {month}"
        )
        series.append(
            {
                "month": _month_record(month),
                "label": label,
                "months_ago": months_ago,
                "points": [
                    {
                        "day": int(row["day"]),
                        "spending": _money(row["spending"]),
                        "cumulative_spending": _money(row["cumulative_spending"]),
                    }
                    for _, row in month_rows.iterrows()
                ],
            }
        )

    return {
        "anchor_month": _month_record(anchor_month),
        "previous_months": previous_months,
        "excluded_categories": _excluded_categories(exclude_category),
        "series": series,
    }


@app.get("/api/monthly-income")
def monthly_income(
    months: int = Query(24, ge=1, le=240, description="Recent months to include"),
    category: str = Query("Paycheck", description="Income category to aggregate"),
):
    """Monthly income totals for an income category."""
    transaction_data = get_transaction_data_df()
    monthly = _monthly_income_df(transaction_data, months=months, category=category)
    return {
        "category": category,
        "months": [
            {"month": _month_record(row["month"]), "income": _money(row["income"])}
            for _, row in monthly.iterrows()
        ],
    }


@app.get("/api/category-histogram")
def category_histogram(
    category: str = Query(..., description="Category to inspect"),
    bins: int = Query(30, ge=1, le=200, description="Number of histogram bins"),
    start: date | None = Query(None, description="Start date, inclusive"),
    end: date | None = Query(None, description="End date, inclusive"),
):
    """Transaction amount histogram and summary statistics for one category."""
    transaction_data = get_transaction_data_df()
    df = _filter_date_range(transaction_data, start, end)
    df = df[df["Category"] == category].copy()
    amounts = df["Amount"].dropna()

    if amounts.empty:
        return {
            "category": category,
            "count": 0,
            "summary": {},
            "bins": [],
        }

    values = [float(value) for value in amounts]
    min_amount = min(values)
    max_amount = max(values)

    if min_amount == max_amount:
        histogram_bins = [
            {
                "min": _money(min_amount),
                "max": _money(max_amount),
                "count": len(values),
            }
        ]
    else:
        width = (max_amount - min_amount) / bins
        counts = [0] * bins
        for value in values:
            index = min(int((value - min_amount) / width), bins - 1)
            counts[index] += 1
        histogram_bins = [
            {
                "min": _money(min_amount + width * i),
                "max": _money(min_amount + width * (i + 1)),
                "count": counts[i],
            }
            for i in range(bins)
        ]

    return {
        "category": category,
        "count": int(amounts.count()),
        "summary": {
            "total": _money(amounts.sum()),
            "average": _money(amounts.mean()),
            "median": _money(amounts.median()),
            "min": _money(amounts.min()),
            "max": _money(amounts.max()),
        },
        "bins": histogram_bins,
    }


@app.get("/api/account-balance-history")
def account_balance_history(
    months: int = Query(24, ge=1, le=240, description="Recent months to include"),
    exclude_account: list[str] | None = Query(
        None, description="Repeatable account names to exclude"
    ),
):
    """Monthly total and per-account balances for the account balance chart."""
    balance_data = resampled_balance_history(get_balance_history())
    balance_data = balance_data[balance_data["Balance"] >= 0].copy()
    if exclude_account:
        balance_data = balance_data[~balance_data["Account"].isin(exclude_account)]

    balance_data["month"] = balance_data["Date"].dt.to_period("M")
    balance_data = _recent_month_filter(balance_data, months)

    monthly_accounts = (
        balance_data.sort_values("Date")
        .groupby(["month", "Account", "Class"])["Balance"]
        .first()
        .reset_index(name="balance")
        .sort_values(["month", "balance"], ascending=[True, False])
    )

    response_months = []
    for month, month_rows in monthly_accounts.groupby("month", sort=True):
        response_months.append(
            {
                "month": _month_record(month),
                "total_balance": _money(month_rows["balance"].sum()),
                "accounts": [
                    {
                        "account": row["Account"],
                        "class": row["Class"],
                        "balance": _money(row["balance"]),
                    }
                    for _, row in month_rows.iterrows()
                ],
            }
        )

    return {
        "excluded_accounts": exclude_account or [],
        "months": response_months,
    }


@app.get("/api/transactions")
def transactions(
    months: int = Query(1, description="Number of recent months"),
    category: str | None = Query(None, description="Filter by category"),
    account: str | None = Query(None, description="Filter by account name (exact match)"),
    min_amount: float | None = Query(None, description="Minimum absolute amount"),
    limit: int = Query(100, ge=1, le=100000, description="Maximum records to return"),
    offset: int = Query(0, ge=0, description="Pagination offset"),
):
    """Recent transactions."""
    df = get_transaction_data_df()
    cutoff = datetime.today() - pd.DateOffset(months=months)
    df = df[df["Date"] >= cutoff]

    if category:
        df = df[df["Category"] == category]
    if account:
        df = df[df["Account"] == account]
    if min_amount is not None:
        df = df[df["Amount"].abs() >= min_amount]

    return _transaction_records(df, limit, offset=offset)


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
    return _category_metadata()
