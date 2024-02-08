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
)


def main():
    st.title("Tiller Money Streamlit App")

    transaction_data = get_transaction_data_df()
    categories = sorted(transaction_data["Category"].unique())

    st.header("Monthly Spending by Category")
    skip_categories = st.multiselect("Exclude categories", categories, default=["Rent"])
    fig = plot_categories_per_month(transaction_data, skip_categories=skip_categories)
    st.plotly_chart(fig)

    st.header("Monthly Spending")
    skip_categories = st.multiselect(
        "Exclude categories from spending", categories, default=["Rent"]
    )
    fig = plot_total_spending_per_month(
        transaction_data, skip_categories=skip_categories
    )
    st.plotly_chart(fig)

    category = st.selectbox(
        "Select a category", categories, index=categories.index("Shopping")
    )
    st.header(f"Spending in category: {category}")
    fig = plot_category_histogram(transaction_data, category)
    st.plotly_chart(fig)

    st.header("Spending by Subcategory")
    category = st.selectbox(
        "Select a category", categories, index=categories.index("Shopping"), key=0
    )
    fig = plot_single_category_by_month_plotly(transaction_data, category)
    st.plotly_chart(fig)
    fig = plot_spending_per_subcategory(transaction_data)
    st.plotly_chart(fig)

    st.header("Monthly Income")
    fig = plot_monthly_income(transaction_data)
    st.plotly_chart(fig)

    st.header("Total Spending by Category")
    fig = plot_categories(transaction_data)
    st.plotly_chart(fig)


if __name__ == "__main__":
    main()