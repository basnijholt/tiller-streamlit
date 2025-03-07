# File: app.py

import streamlit as st
from tiller_streamlit import (
    get_transaction_data_df,
    plot_categories_per_month,
    plot_total_spending_per_month,
    plot_category_histogram,
    plot_categories,
    plot_spending_per_subcategory,
    plot_single_category_by_month_plotly,
    plot_monthly_income,
    plot_comparative_spending,
    get_balance_history,
    resampled_balance_history,
    plot_net_worth_over_time,
    plot_monthly_total_and_account_balances,
)


def toc(headers):
    """
    Generates a Table of Contents in the sidebar based on the headers list.

    Args:
        headers (list): List of header titles.
    """
    st.sidebar.title("Table of Contents")
    st.sidebar.markdown(
        "\n".join(
            [f"- [{header}](#{header.lower().replace(' ', '-')})" for header in headers]
        )
    )


def main():
    """
    The main function orchestrates the layout of the Streamlit app by calling
    individual plotting functions for each section.
    """
    st.title("Tiller Money Streamlit App")

    headers = []

    def header(s):
        """
        Sets a header and appends it to the headers list for TOC.

        Args:
            s (str): The header title.
        """
        headers.append(s)
        st.header(s)

    # Fetch transaction data once to use across multiple plots
    transaction_data = get_transaction_data_df()
    categories = sorted(transaction_data["Category"].unique())

    # Plot Sections
    plot_net_worth_section(transaction_data, header)
    plot_monthly_spending_by_category_section(transaction_data, categories, header)
    plot_monthly_spending_section(transaction_data, categories, header)
    plot_monthly_comparative_spending_section(transaction_data, header)
    plot_histogram_section(transaction_data, categories, header)
    plot_spending_by_subcategory_section(transaction_data, categories, header)
    plot_monthly_income_section(transaction_data, header)
    plot_total_spending_pie_chart_section(transaction_data, header)

    # Generate Table of Contents
    toc(headers)


def plot_net_worth_section(transaction_data, header_func):
    """
    Renders the "Net worth over time" section.

    Args:
        transaction_data (pd.DataFrame): The transaction data.
        header_func (function): Function to set headers.
    """
    header_func("Net worth over time")
    df_balance_history = get_balance_history()
    df_nw = resampled_balance_history(df_balance_history)
    fig1 = plot_monthly_total_and_account_balances(df_nw)
    st.plotly_chart(fig1, use_container_width=True)

    fig2 = plot_net_worth_over_time(df_nw)
    st.plotly_chart(fig2, use_container_width=True)


def plot_monthly_comparative_spending_section(transaction_data, header_func):
    """
    Renders the "Monthly Comparative Spending" section.

    Args:
        transaction_data (pd.DataFrame): The transaction data.
        header_func (function): Function to set headers.
    """
    header_func("Monthly Comparative Spending")
    months_to_compare = st.selectbox(
        "Compare with previous n months:", [1, 2, 3, 4, 5, 6], index=2
    )
    fig = plot_comparative_spending(transaction_data, months_to_compare)
    st.altair_chart(fig, use_container_width=True)


def plot_monthly_spending_by_category_section(
    transaction_data, categories, header_func
):
    """
    Renders the "Monthly Spending by Category" section with optional moving average.
    Args:
        transaction_data (pd.DataFrame): The transaction data.
        categories (list): List of unique categories.
        header_func (function): Function to set headers.
    """
    
    header_func("Monthly Spending by Category")
    # Ensure "Rent" is in the categories list
    default_values = ["Rent"] if "Rent" in categories else []
    # Allow users to exclude certain categories
    skip_categories = st.multiselect("Exclude categories", categories, default=default_values)

    # Checkbox to enable moving average
    enable_ma = st.checkbox("Add moving average to each category")

    # Initialize moving average variable
    n_months_ma = None

    if enable_ma:
        # Number input for specifying 'N months moving average'
        n_months_ma = st.number_input(
            "Number of months for moving average",
            min_value=2,
            max_value=12,
            value=3,
            step=1,
            help="Select the number of months for calculating the moving average.",
        )

    # Pass the moving average parameter to the plotting function
    fig = plot_categories_per_month(
        transaction_data, skip_categories=skip_categories, n_months_ma=n_months_ma
    )

    st.plotly_chart(fig, use_container_width=True)


def plot_monthly_spending_section(transaction_data, categories, header_func):
    """
    Renders the "Monthly Spending" section.

    Args:
        transaction_data (pd.DataFrame): The transaction data.
        categories (list): List of unique categories.
        header_func (function): Function to set headers.
    """
    header_func("Monthly Spending")

    # Ensure "Rent" is in the categories list
    default_values = ["Rent"] if "Rent" in categories else []
    # Allow users to exclude certain categories
    skip_categories = st.multiselect(
        "Exclude categories from spending",
        categories,
        default=default_values,
        key="spending_exclude",
    )
    
    

    fig = plot_total_spending_per_month(
        transaction_data,
        skip_categories=skip_categories,
        n_months_moving_avg=[3, 6, 12],
    )
    st.plotly_chart(fig, use_container_width=True)


def plot_histogram_section(transaction_data, categories, header_func):
    """
    Renders the "Histogram of amount per category" section.

    Args:
        transaction_data (pd.DataFrame): The transaction data.
        categories (list): List of unique categories.
        header_func (function): Function to set headers.
    """
    header_func("Histogram of amount per category")
    category = st.selectbox(
        "Select a category",
        categories,
        index=categories.index("Shopping") if "Shopping" in categories else 0,
    )
    fig = plot_category_histogram(transaction_data, category)
    st.plotly_chart(fig, use_container_width=True)


def plot_spending_by_subcategory_section(transaction_data, categories, header_func):
    """
    Renders the "Spending by Subcategory" section.

    Args:
        transaction_data (pd.DataFrame): The transaction data.
        categories (list): List of unique categories.
        header_func (function): Function to set headers.
    """
    header_func("Spending by Subcategory")
    category = st.selectbox(
        "Select a category",
        categories,
        index=categories.index("Shopping") if "Shopping" in categories else 0,
        key="subcategory_select",
    )
    fig = plot_single_category_by_month_plotly(transaction_data, category)
    st.plotly_chart(fig, use_container_width=True)

    fig = plot_spending_per_subcategory(transaction_data)
    st.plotly_chart(fig, use_container_width=True)


def plot_monthly_income_section(transaction_data, header_func):
    """
    Renders the "Monthly Income" section.

    Args:
        transaction_data (pd.DataFrame): The transaction data.
        header_func (function): Function to set headers.
    """
    header_func("Monthly Income")
    fig = plot_monthly_income(transaction_data)
    st.plotly_chart(fig, use_container_width=True)


def plot_total_spending_pie_chart_section(transaction_data, header_func):
    """
    Renders the "Total Spending Pie Chart" section.

    Args:
        transaction_data (pd.DataFrame): The transaction data.
        header_func (function): Function to set headers.
    """
    header_func("Total Spending Pie Chart")
    year = st.selectbox(
        "Select a year",
        [None] + sorted(transaction_data["Date"].dt.year.unique(), reverse=True),
    )
    month = st.selectbox("Select a month", [None] + list(range(1, 13)))
    with_group = st.checkbox("Group by category", value=False, key="pie_group")
    fig = plot_categories(transaction_data, month, year, with_group=with_group)
    st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
