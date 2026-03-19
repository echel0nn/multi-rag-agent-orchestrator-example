import pandas as pd
import numpy as np
import os
import time
import dotenv
import ast
import json
import re
import difflib
import contextlib
import io
import textwrap
from sqlalchemy.sql import text
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple, Type, Union
from pydantic import BaseModel, Field, ValidationError
from openai import OpenAI
from sqlalchemy import create_engine, Engine
from smolagents import (
    ToolCallingAgent,
    OpenAIServerModel,
    tool,
)

try:
    from rich import box
    from rich.align import Align
    from rich.console import Console, Group
    from rich.live import Live
    from rich.panel import Panel
    from rich.spinner import Spinner
    from rich.table import Table
    from rich.text import Text
except ImportError:
    box = None
    Align = None
    Console = None
    Group = None
    Live = None
    Panel = None
    Spinner = None
    Table = None
    Text = None

# Create an SQLite database
db_engine = create_engine("sqlite:///munder_difflin.db")

# List containing the different kinds of papers 
paper_supplies = [
    # Paper Types (priced per sheet unless specified)
    {"item_name": "A4 paper",                         "category": "paper",        "unit_price": 0.05},
    {"item_name": "Letter-sized paper",              "category": "paper",        "unit_price": 0.06},
    {"item_name": "Cardstock",                        "category": "paper",        "unit_price": 0.15},
    {"item_name": "Colored paper",                    "category": "paper",        "unit_price": 0.10},
    {"item_name": "Glossy paper",                     "category": "paper",        "unit_price": 0.20},
    {"item_name": "Matte paper",                      "category": "paper",        "unit_price": 0.18},
    {"item_name": "Recycled paper",                   "category": "paper",        "unit_price": 0.08},
    {"item_name": "Eco-friendly paper",               "category": "paper",        "unit_price": 0.12},
    {"item_name": "Poster paper",                     "category": "paper",        "unit_price": 0.25},
    {"item_name": "Banner paper",                     "category": "paper",        "unit_price": 0.30},
    {"item_name": "Kraft paper",                      "category": "paper",        "unit_price": 0.10},
    {"item_name": "Construction paper",               "category": "paper",        "unit_price": 0.07},
    {"item_name": "Wrapping paper",                   "category": "paper",        "unit_price": 0.15},
    {"item_name": "Glitter paper",                    "category": "paper",        "unit_price": 0.22},
    {"item_name": "Decorative paper",                 "category": "paper",        "unit_price": 0.18},
    {"item_name": "Letterhead paper",                 "category": "paper",        "unit_price": 0.12},
    {"item_name": "Legal-size paper",                 "category": "paper",        "unit_price": 0.08},
    {"item_name": "Crepe paper",                      "category": "paper",        "unit_price": 0.05},
    {"item_name": "Photo paper",                      "category": "paper",        "unit_price": 0.25},
    {"item_name": "Uncoated paper",                   "category": "paper",        "unit_price": 0.06},
    {"item_name": "Butcher paper",                    "category": "paper",        "unit_price": 0.10},
    {"item_name": "Heavyweight paper",                "category": "paper",        "unit_price": 0.20},
    {"item_name": "Standard copy paper",              "category": "paper",        "unit_price": 0.04},
    {"item_name": "Bright-colored paper",             "category": "paper",        "unit_price": 0.12},
    {"item_name": "Patterned paper",                  "category": "paper",        "unit_price": 0.15},

    # Product Types (priced per unit)
    {"item_name": "Paper plates",                     "category": "product",      "unit_price": 0.10},  # per plate
    {"item_name": "Paper cups",                       "category": "product",      "unit_price": 0.08},  # per cup
    {"item_name": "Paper napkins",                    "category": "product",      "unit_price": 0.02},  # per napkin
    {"item_name": "Disposable cups",                  "category": "product",      "unit_price": 0.10},  # per cup
    {"item_name": "Table covers",                     "category": "product",      "unit_price": 1.50},  # per cover
    {"item_name": "Envelopes",                        "category": "product",      "unit_price": 0.05},  # per envelope
    {"item_name": "Sticky notes",                     "category": "product",      "unit_price": 0.03},  # per sheet
    {"item_name": "Notepads",                         "category": "product",      "unit_price": 2.00},  # per pad
    {"item_name": "Invitation cards",                 "category": "product",      "unit_price": 0.50},  # per card
    {"item_name": "Flyers",                           "category": "product",      "unit_price": 0.15},  # per flyer
    {"item_name": "Party streamers",                  "category": "product",      "unit_price": 0.05},  # per roll
    {"item_name": "Decorative adhesive tape (washi tape)", "category": "product", "unit_price": 0.20},  # per roll
    {"item_name": "Paper party bags",                 "category": "product",      "unit_price": 0.25},  # per bag
    {"item_name": "Name tags with lanyards",          "category": "product",      "unit_price": 0.75},  # per tag
    {"item_name": "Presentation folders",             "category": "product",      "unit_price": 0.50},  # per folder

    # Large-format items (priced per unit)
    {"item_name": "Large poster paper (24x36 inches)", "category": "large_format", "unit_price": 1.00},
    {"item_name": "Rolls of banner paper (36-inch width)", "category": "large_format", "unit_price": 2.50},

    # Specialty papers
    {"item_name": "100 lb cover stock",               "category": "specialty",    "unit_price": 0.50},
    {"item_name": "80 lb text paper",                 "category": "specialty",    "unit_price": 0.40},
    {"item_name": "250 gsm cardstock",                "category": "specialty",    "unit_price": 0.30},
    {"item_name": "220 gsm poster paper",             "category": "specialty",    "unit_price": 0.35},
]

CATALOG_BY_NAME = {item["item_name"]: item for item in paper_supplies}
CATALOG_NAMES = list(CATALOG_BY_NAME)
CATALOG_NAME_NORMALIZED = {
    item_name: re.sub(r"[^a-z0-9]+", " ", item_name.lower()).strip()
    for item_name in CATALOG_NAMES
}
COMMON_UNIT_WORDS = {
    "sheet",
    "sheets",
    "ream",
    "reams",
    "roll",
    "rolls",
    "box",
    "boxes",
    "packet",
    "packets",
    "pack",
    "packs",
    "unit",
    "units",
}
UNIT_NORMALIZATION = {
    "sheet": ("sheets", 1),
    "sheets": ("sheets", 1),
    "ream": ("sheets", 500),
    "reams": ("sheets", 500),
    "roll": ("rolls", 1),
    "rolls": ("rolls", 1),
    "unit": ("units", 1),
    "units": ("units", 1),
}
SPECIAL_KEYWORD_CANDIDATES = {
    "washi tape": "Decorative adhesive tape (washi tape)",
    "streamers": "Party streamers",
    "streamer": "Party streamers",
    "dinner napkins": "Paper napkins",
    "napkins": "Paper napkins",
    "napkin": "Paper napkins",
    "paper plates": "Paper plates",
    "plates": "Paper plates",
    "plate": "Paper plates",
    "disposable cups": "Disposable cups",
    "paper cups": "Paper cups",
    "cups": "Paper cups",
    "cup": "Paper cups",
    "envelopes": "Envelopes",
    "envelope": "Envelopes",
    "flyers": "Flyers",
    "flyer": "Flyers",
    "notepads": "Notepads",
    "notepad": "Notepads",
    "sticky notes": "Sticky notes",
    "sticky note": "Sticky notes",
    "invitation cards": "Invitation cards",
    "invitation card": "Invitation cards",
    "presentation folders": "Presentation folders",
    "folder": "Presentation folders",
    "folders": "Presentation folders",
    "name tags": "Name tags with lanyards",
    "name tag": "Name tags with lanyards",
    "party bags": "Paper party bags",
    "paper party bags": "Paper party bags",
    "poster boards": "Large poster paper (24x36 inches)",
    "poster board": "Large poster paper (24x36 inches)",
    "banner paper": "Banner paper",
    "banner": "Banner paper",
    "a4 paper": "A4 paper",
    "letter sized paper": "Letter-sized paper",
    "letter paper": "Letter-sized paper",
    "legal paper": "Legal-size paper",
    "copy paper": "Standard copy paper",
    "printer paper": "Standard copy paper",
    "white printer paper": "Standard copy paper",
    "construction paper": "Construction paper",
    "kraft paper": "Kraft paper",
    "recycled paper": "Recycled paper",
    "eco friendly paper": "Eco-friendly paper",
    "glossy paper": "Glossy paper",
    "matte paper": "Matte paper",
    "colored paper": "Colored paper",
    "cardstock": "Cardstock",
}
WORKFLOW_CONTEXT: Dict[str, Any] = {}
OPENAI_API_BASE = "https://openai.vocareum.com/v1"
EMBEDDING_MODEL_ID = "text-embedding-3-small"
EMBEDDING_CACHE: Dict[str, Optional[np.ndarray]] = {}
EMBEDDING_CLIENT: Optional[OpenAI] = None
CATALOG_EMBEDDING_TEXT = {
    item_name: (
        f"supported catalog item: {item_name}. "
        f"category: {CATALOG_BY_NAME[item_name]['category']}. "
        f"normalized tokens: {CATALOG_NAME_NORMALIZED[item_name]}"
    )
    for item_name in CATALOG_NAMES
}

# Given below are some utility functions you can use to implement your multi-agent system

def generate_sample_inventory(paper_supplies: list, coverage: float = 0.4, seed: int = 137) -> pd.DataFrame:
    """
    Generate inventory for exactly a specified percentage of items from the full paper supply list.

    This function randomly selects exactly `coverage` × N items from the `paper_supplies` list,
    and assigns each selected item:
    - a random stock quantity between 200 and 800,
    - a minimum stock level between 50 and 150.

    The random seed ensures reproducibility of selection and stock levels.

    Args:
        paper_supplies (list): A list of dictionaries, each representing a paper item with
                               keys 'item_name', 'category', and 'unit_price'.
        coverage (float, optional): Fraction of items to include in the inventory (default is 0.4, or 40%).
        seed (int, optional): Random seed for reproducibility (default is 137).

    Returns:
        pd.DataFrame: A DataFrame with the selected items and assigned inventory values, including:
                      - item_name
                      - category
                      - unit_price
                      - current_stock
                      - min_stock_level
    """
    # Ensure reproducible random output
    np.random.seed(seed)

    # Calculate number of items to include based on coverage
    num_items = int(len(paper_supplies) * coverage)

    # Randomly select item indices without replacement
    selected_indices = np.random.choice(
        range(len(paper_supplies)),
        size=num_items,
        replace=False
    )

    # Extract selected items from paper_supplies list
    selected_items = [paper_supplies[i] for i in selected_indices]

    # Construct inventory records
    inventory = []
    for item in selected_items:
        inventory.append({
            "item_name": item["item_name"],
            "category": item["category"],
            "unit_price": item["unit_price"],
            "current_stock": np.random.randint(200, 800),  # Realistic stock range
            "min_stock_level": np.random.randint(50, 150)  # Reasonable threshold for reordering
        })

    # Return inventory as a pandas DataFrame
    return pd.DataFrame(inventory)

def init_database(db_engine: Engine, seed: int = 137) -> Engine:    
    """
    Set up the Munder Difflin database with all required tables and initial records.

    This function performs the following tasks:
    - Creates the 'transactions' table for logging stock orders and sales
    - Loads customer inquiries from 'quote_requests.csv' into a 'quote_requests' table
    - Loads previous quotes from 'quotes.csv' into a 'quotes' table, extracting useful metadata
    - Generates a random subset of paper inventory using `generate_sample_inventory`
    - Inserts initial financial records including available cash and starting stock levels

    Args:
        db_engine (Engine): A SQLAlchemy engine connected to the SQLite database.
        seed (int, optional): A random seed used to control reproducibility of inventory stock levels.
                              Default is 137.

    Returns:
        Engine: The same SQLAlchemy engine, after initializing all necessary tables and records.

    Raises:
        Exception: If an error occurs during setup, the exception is printed and raised.
    """
    try:
        # ----------------------------
        # 1. Create an empty 'transactions' table schema
        # ----------------------------
        transactions_schema = pd.DataFrame({
            "id": [],
            "item_name": [],
            "transaction_type": [],  # 'stock_orders' or 'sales'
            "units": [],             # Quantity involved
            "price": [],             # Total price for the transaction
            "transaction_date": [],  # ISO-formatted date
        })
        transactions_schema.to_sql("transactions", db_engine, if_exists="replace", index=False)

        # Set a consistent starting date
        initial_date = datetime(2025, 1, 1).isoformat()

        # ----------------------------
        # 2. Load and initialize 'quote_requests' table
        # ----------------------------
        quote_requests_df = pd.read_csv("quote_requests.csv")
        quote_requests_df["id"] = range(1, len(quote_requests_df) + 1)
        quote_requests_df.to_sql("quote_requests", db_engine, if_exists="replace", index=False)

        # ----------------------------
        # 3. Load and transform 'quotes' table
        # ----------------------------
        quotes_df = pd.read_csv("quotes.csv")
        quotes_df["request_id"] = range(1, len(quotes_df) + 1)
        quotes_df["order_date"] = initial_date

        # Unpack metadata fields (job_type, order_size, event_type) if present
        if "request_metadata" in quotes_df.columns:
            quotes_df.loc[:, "request_metadata"] = quotes_df["request_metadata"].apply(
                lambda x: ast.literal_eval(x) if isinstance(x, str) else x
            )
            quotes_df.loc[:, "job_type"] = quotes_df["request_metadata"].apply(
                lambda x: x.get("job_type", "")
            )
            quotes_df.loc[:, "order_size"] = quotes_df["request_metadata"].apply(
                lambda x: x.get("order_size", "")
            )
            quotes_df.loc[:, "event_type"] = quotes_df["request_metadata"].apply(
                lambda x: x.get("event_type", "")
            )

        # Retain only relevant columns
        quotes_df = quotes_df[[
            "request_id",
            "total_amount",
            "quote_explanation",
            "order_date",
            "job_type",
            "order_size",
            "event_type"
        ]]
        quotes_df.to_sql("quotes", db_engine, if_exists="replace", index=False)

        # ----------------------------
        # 4. Generate inventory and seed stock
        # ----------------------------
        inventory_df = generate_sample_inventory(paper_supplies, seed=seed)

        # Seed initial transactions
        initial_transactions = []

        # Add a starting cash balance via a dummy sales transaction
        initial_transactions.append({
            "item_name": None,
            "transaction_type": "sales",
            "units": None,
            "price": 50000.0,
            "transaction_date": initial_date,
        })

        # Add one stock order transaction per inventory item
        for _, item in inventory_df.iterrows():
            initial_transactions.append({
                "item_name": item["item_name"],
                "transaction_type": "stock_orders",
                "units": item["current_stock"],
                "price": item["current_stock"] * item["unit_price"],
                "transaction_date": initial_date,
            })

        # Commit transactions to database
        pd.DataFrame(initial_transactions).to_sql("transactions", db_engine, if_exists="append", index=False)

        # Save the inventory reference table
        inventory_df.to_sql("inventory", db_engine, if_exists="replace", index=False)

        return db_engine

    except Exception as e:
        print(f"Error initializing database: {e}")
        raise

def create_transaction(
    item_name: str,
    transaction_type: str,
    quantity: int,
    price: float,
    date: Union[str, datetime],
) -> int:
    """
    This function records a transaction of type 'stock_orders' or 'sales' with a specified
    item name, quantity, total price, and transaction date into the 'transactions' table of the database.

    Args:
        item_name (str): The name of the item involved in the transaction.
        transaction_type (str): Either 'stock_orders' or 'sales'.
        quantity (int): Number of units involved in the transaction.
        price (float): Total price of the transaction.
        date (str or datetime): Date of the transaction in ISO 8601 format.

    Returns:
        int: The ID of the newly inserted transaction.

    Raises:
        ValueError: If `transaction_type` is not 'stock_orders' or 'sales'.
        Exception: For other database or execution errors.
    """
    try:
        # Convert datetime to ISO string if necessary
        date_str = date.isoformat() if isinstance(date, datetime) else date

        # Validate transaction type
        if transaction_type not in {"stock_orders", "sales"}:
            raise ValueError("Transaction type must be 'stock_orders' or 'sales'")

        # Prepare transaction record as a single-row DataFrame
        transaction = pd.DataFrame([{
            "item_name": item_name,
            "transaction_type": transaction_type,
            "units": quantity,
            "price": price,
            "transaction_date": date_str,
        }])

        # Insert the record into the database
        transaction.to_sql("transactions", db_engine, if_exists="append", index=False)

        # Fetch and return the ID of the inserted row
        result = pd.read_sql("SELECT last_insert_rowid() as id", db_engine)
        return int(result.iloc[0]["id"])

    except Exception as e:
        print(f"Error creating transaction: {e}")
        raise

def get_all_inventory(as_of_date: str) -> Dict[str, int]:
    """
    Retrieve a snapshot of available inventory as of a specific date.

    This function calculates the net quantity of each item by summing 
    all stock orders and subtracting all sales up to and including the given date.

    Only items with positive stock are included in the result.

    Args:
        as_of_date (str): ISO-formatted date string (YYYY-MM-DD) representing the inventory cutoff.

    Returns:
        Dict[str, int]: A dictionary mapping item names to their current stock levels.
    """
    # SQL query to compute stock levels per item as of the given date
    query = """
        SELECT
            item_name,
            SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END) as stock
        FROM transactions
        WHERE item_name IS NOT NULL
        AND transaction_date <= :as_of_date
        GROUP BY item_name
        HAVING stock > 0
    """

    # Execute the query with the date parameter
    result = pd.read_sql(query, db_engine, params={"as_of_date": as_of_date})

    # Convert the result into a dictionary {item_name: stock}
    return dict(zip(result["item_name"], result["stock"]))

def get_stock_level(item_name: str, as_of_date: Union[str, datetime]) -> pd.DataFrame:
    """
    Retrieve the fulfillable stock level of a specific item as of a given date.

    This function calculates the net stock by summing all `stock_orders` and
    subtracting all `sales` transactions for the specified item up to the given
    date. Historical data can temporarily drive the net ledger below zero during
    backorder scenarios or after earlier buggy runs. For fulfillment decisions,
    negative stock is treated as zero available units because the company cannot
    ship a negative quantity.

    Args:
        item_name (str): The name of the item to look up.
        as_of_date (str or datetime): The cutoff date (inclusive) for calculating stock.

    Returns:
        pd.DataFrame: A single-row DataFrame with columns `item_name` and
            `current_stock`, where `current_stock` is clamped to zero or higher.
    """
    # Convert date to ISO string format if it's a datetime object
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()

    # SQL query to compute net stock level for the item
    stock_query = """
        SELECT
            item_name,
            COALESCE(SUM(CASE
                WHEN transaction_type = 'stock_orders' THEN units
                WHEN transaction_type = 'sales' THEN -units
                ELSE 0
            END), 0) AS current_stock
        FROM transactions
        WHERE item_name = :item_name
        AND transaction_date <= :as_of_date
    """

    # Compute the raw ledger balance, then clamp negative balances to zero so
    # downstream availability checks reflect shippable inventory rather than
    # historical oversell artifacts.
    stock_df = pd.read_sql(
        stock_query,
        db_engine,
        params={"item_name": item_name, "as_of_date": as_of_date},
    )
    if stock_df.empty:
        return pd.DataFrame(
            [{"item_name": item_name, "current_stock": 0}]
        )

    stock_df.loc[:, "item_name"] = stock_df["item_name"].fillna(item_name)
    stock_df.loc[:, "current_stock"] = stock_df["current_stock"].fillna(0).clip(lower=0)
    return stock_df

def get_supplier_delivery_date(input_date_str: str, quantity: int) -> str:
    """
    Estimate the supplier delivery date based on the requested order quantity and a starting date.

    Delivery lead time increases with order size:
        - ≤10 units: same day
        - 11–100 units: 1 day
        - 101–1000 units: 4 days
        - >1000 units: 7 days

    Args:
        input_date_str (str): The starting date in ISO format (YYYY-MM-DD).
        quantity (int): The number of units in the order.

    Returns:
        str: Estimated delivery date in ISO format (YYYY-MM-DD).
    """
    # Attempt to parse the input date
    try:
        input_date_dt = datetime.fromisoformat(input_date_str.split("T")[0])
    except (ValueError, TypeError):
        # Fallback to current date on format error
        input_date_dt = datetime.now()

    # Determine delivery delay based on quantity
    if quantity <= 10:
        days = 0
    elif quantity <= 100:
        days = 1
    elif quantity <= 1000:
        days = 4
    else:
        days = 7

    # Add delivery days to the starting date
    delivery_date_dt = input_date_dt + timedelta(days=days)

    # Return formatted delivery date
    return delivery_date_dt.strftime("%Y-%m-%d")

def get_cash_balance(as_of_date: Union[str, datetime]) -> float:
    """
    Calculate the current cash balance as of a specified date.

    The balance is computed by subtracting total stock purchase costs ('stock_orders')
    from total revenue ('sales') recorded in the transactions table up to the given date.

    Args:
        as_of_date (str or datetime): The cutoff date (inclusive) in ISO format or as a datetime object.

    Returns:
        float: Net cash balance as of the given date. Returns 0.0 if no transactions exist or an error occurs.
    """
    try:
        # Convert date to ISO format if it's a datetime object
        if isinstance(as_of_date, datetime):
            as_of_date = as_of_date.isoformat()

        # Query all transactions on or before the specified date
        transactions = pd.read_sql(
            "SELECT * FROM transactions WHERE transaction_date <= :as_of_date",
            db_engine,
            params={"as_of_date": as_of_date},
        )

        # Compute the difference between sales and stock purchases
        if not transactions.empty:
            total_sales = transactions.loc[transactions["transaction_type"] == "sales", "price"].sum()
            total_purchases = transactions.loc[transactions["transaction_type"] == "stock_orders", "price"].sum()
            return float(total_sales - total_purchases)

        return 0.0

    except Exception as e:
        print(f"Error getting cash balance: {e}")
        return 0.0


def generate_financial_report(as_of_date: Union[str, datetime]) -> Dict:
    """
    Generate a complete financial report for the company as of a specific date.

    This includes:
    - Cash balance
    - Inventory valuation
    - Combined asset total
    - Itemized inventory breakdown
    - Top 5 best-selling products

    Args:
        as_of_date (str or datetime): The date (inclusive) for which to generate the report.

    Returns:
        Dict: A dictionary containing the financial report fields:
            - 'as_of_date': The date of the report
            - 'cash_balance': Total cash available
            - 'inventory_value': Total value of inventory
            - 'total_assets': Combined cash and inventory value
            - 'inventory_summary': List of items with stock and valuation details
            - 'top_selling_products': List of top 5 products by revenue
    """
    # Normalize date input
    if isinstance(as_of_date, datetime):
        as_of_date = as_of_date.isoformat()

    # Get current cash balance
    cash = get_cash_balance(as_of_date)

    # Get current inventory snapshot
    inventory_df = pd.read_sql("SELECT * FROM inventory", db_engine)
    inventory_value = 0.0
    inventory_summary = []

    # Compute total inventory value and summary by item
    for _, item in inventory_df.iterrows():
        stock_info = get_stock_level(item["item_name"], as_of_date)
        stock = stock_info["current_stock"].iloc[0]
        item_value = stock * item["unit_price"]
        inventory_value += item_value

        inventory_summary.append({
            "item_name": item["item_name"],
            "stock": stock,
            "unit_price": item["unit_price"],
            "value": item_value,
        })

    # Identify top-selling products by revenue
    top_sales_query = """
        SELECT item_name, SUM(units) as total_units, SUM(price) as total_revenue
        FROM transactions
        WHERE transaction_type = 'sales' AND transaction_date <= :date
        GROUP BY item_name
        ORDER BY total_revenue DESC
        LIMIT 5
    """
    top_sales = pd.read_sql(top_sales_query, db_engine, params={"date": as_of_date})
    top_selling_products = top_sales.to_dict(orient="records")

    return {
        "as_of_date": as_of_date,
        "cash_balance": cash,
        "inventory_value": inventory_value,
        "total_assets": cash + inventory_value,
        "inventory_summary": inventory_summary,
        "top_selling_products": top_selling_products,
    }


def search_quote_history(search_terms: List[str], limit: int = 5) -> List[Dict]:
    """
    Retrieve a list of historical quotes that match any of the provided search terms.

    The function searches both the original customer request (from `quote_requests`) and
    the explanation for the quote (from `quotes`) for each keyword. Results are sorted by
    most recent order date and limited by the `limit` parameter.

    Args:
        search_terms (List[str]): List of terms to match against customer requests and explanations.
        limit (int, optional): Maximum number of quote records to return. Default is 5.

    Returns:
        List[Dict]: A list of matching quotes, each represented as a dictionary with fields:
            - original_request
            - total_amount
            - quote_explanation
            - job_type
            - order_size
            - event_type
            - order_date
    """
    conditions = []
    params = {}

    # Build SQL WHERE clause using LIKE filters for each search term
    for i, term in enumerate(search_terms):
        param_name = f"term_{i}"
        conditions.append(
            f"(LOWER(qr.response) LIKE :{param_name} OR "
            f"LOWER(q.quote_explanation) LIKE :{param_name})"
        )
        params[param_name] = f"%{term.lower()}%"

    # Combine conditions; fallback to always-true if no terms provided
    where_clause = " AND ".join(conditions) if conditions else "1=1"

    # Final SQL query to join quotes with quote_requests
    query = f"""
        SELECT
            qr.response AS original_request,
            q.total_amount,
            q.quote_explanation,
            q.job_type,
            q.order_size,
            q.event_type,
            q.order_date
        FROM quotes q
        JOIN quote_requests qr ON q.request_id = qr.id
        WHERE {where_clause}
        ORDER BY q.order_date DESC
        LIMIT {limit}
    """

    # Execute parameterized query
    with db_engine.connect() as conn:
        result = conn.execute(text(query), params)
        return [dict(row._mapping) for row in result]

########################
########################
########################
# YOUR MULTI AGENT STARTS HERE
########################
########################
########################

class WorkflowValidationError(Exception):
    """
    Raised when a specialist agent returns invalid structured output that
    cannot be safely admitted into the orchestration workflow.
    """
    pass

class CatalogMatchResult(BaseModel):
    """
    Structured result for resolving a customer phrase to a supported catalog item.
    """
    match_type: str = Field(
        description="One of: SUPPORTED, AMBIGUOUS, UNSUPPORTED"
    )
    normalized_name: Optional[str] = Field(
        default=None,
        description="Exact supported catalog item name if supported, else None"
    )
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score between 0 and 1"
    )
    reason: str = Field(
        description="Short explanation for the resolution result"
    )

class ParsedRequestItem(BaseModel):
    """
    Structured representation of one item mentioned in a customer request.
    """
    raw_name: str = Field(description="Original item phrase extracted from the request")
    quantity: int = Field(ge=1, description="Requested quantity")
    unit: str = Field(description="Unit mentioned in the request, e.g. sheets, reams, rolls")


class NormalizedRequestItem(BaseModel):
    """
    Structured representation of a request item after catalog normalization.
    """
    raw_name: str = Field(description="Original item phrase extracted from the request")
    normalized_name: Optional[str] = Field(
        default=None,
        description="Exact supported catalog item name if resolved"
    )
    quantity: int = Field(ge=1, description="Original quantity from the request")
    unit: str = Field(description="Original unit from the request")
    normalized_quantity: int = Field(
        ge=0,
        description="Quantity after unit conversion into the workflow's normalized counting scheme"
    )
    normalized_unit: str = Field(description="Normalized unit label used internally")
    supported: bool = Field(description="Whether the item could be safely mapped to the supported catalog")
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="Confidence score for the normalization result"
    )
    unit_price: float = Field(
        ge=0.0,
        description="Catalog unit price for the resolved supported item"
    )



class RequestProfile(BaseModel):
    """
    Structured metadata profile aligned with the historical quote request dataset.
    """
    job_type: str = Field(default="unknown", description="Inferred job type")
    order_size: str = Field(default="unknown", description="Inferred order size")
    event_type: str = Field(default="unknown", description="Inferred event type")
    mood: str = Field(default="unknown", description="Inferred mood")


class QuoteResult(BaseModel):
    """
    Structured quote output produced during the quoting stage.
    """
    base_total: float = Field(ge=0.0, default=0.0)
    discount_rate: float = Field(ge=0.0, le=1.0, default=0.0)
    discount_amount: float = Field(ge=0.0, default=0.0)
    final_total: float = Field(ge=0.0, default=0.0)
    similar_quotes_used: int = Field(ge=0, default=0)
    pricing_notes: List[str] = Field(default_factory=list)
    explanation: str = Field(default="")


class InventoryAssessmentItem(BaseModel):
    """
    Structured inventory assessment for one normalized catalog item.
    """
    item_name: str = Field(description="Exact supported catalog item name")
    requested: int = Field(ge=0, description="Requested normalized quantity")
    available: int = Field(ge=0, description="Available quantity as of the request date")
    shortage: int = Field(ge=0, description="Missing quantity that would require reorder")
    needs_reorder: bool = Field(description="Whether reorder is needed to satisfy the request")
    estimated_delivery: Optional[str] = Field(
        default=None,
        description="Estimated supplier delivery date if reorder is needed"
    )
    feasible: bool = Field(
        description="Whether this item can be fulfilled by the required deadline"
    )


class InventoryResult(BaseModel):
    """
    Structured result of the inventory assessment stage for the full request.
    """
    items: List[InventoryAssessmentItem] = Field(default_factory=list)
    delivery_feasible: Optional[bool] = Field(
        default=None,
        description="Whether the full supported portion of the request is deliverable by deadline"
    )
    overall_shortage: bool = Field(
        default=False,
        description="Whether any item in the request has a shortage"
    )


class ReorderPlanItem(BaseModel):
    """
    Structured reorder action for one catalog item that needs replenishment.
    """
    item_name: str = Field(description="Exact supported catalog item name")
    quantity_to_order: int = Field(ge=1, description="Quantity that should be reordered")
    estimated_delivery: Optional[str] = Field(
        default=None,
        description="Estimated supplier delivery date for the reorder"
    )
    approved: bool = Field(
        default=False,
        description="Whether the reorder is part of an approved fulfillment path"
    )


class RequestMetadataResult(BaseModel):
    """
    Structured metadata captured for a single customer request.

    Attributes:
        raw_request: Original customer request text.
        intent: Workflow intent classification.
        urgency: Request urgency classification.
        request_date: Request creation date in ISO format when known.
        delivery_deadline: Requested delivery deadline in ISO format when known.
        request_profile: Historical-quote-aligned metadata for the request.
    """

    raw_request: str
    intent: str
    urgency: str
    request_date: Optional[str] = None
    delivery_deadline: Optional[str] = None
    request_profile: RequestProfile


class UnsupportedRequestItem(BaseModel):
    """
    Unsupported request item that could not be mapped into the catalog.

    Attributes:
        raw_name: Original extracted item phrase.
        quantity: Requested quantity.
        unit: Requested unit text.
        reason: Explanation for why the item is unsupported.
    """

    raw_name: str
    quantity: int = Field(ge=1)
    unit: str
    reason: str


class AmbiguousRequestItem(BaseModel):
    """
    Ambiguous request item that needs clarification before fulfillment.

    Attributes:
        raw_name: Original extracted item phrase.
        quantity: Requested quantity.
        unit: Requested unit text.
        candidate_names: Supported catalog candidates that were plausible.
        reason: Explanation for why the item remains ambiguous.
    """

    raw_name: str
    quantity: int = Field(ge=1)
    unit: str
    candidate_names: List[str] = Field(default_factory=list)
    reason: str


class NormalizationResult(BaseModel):
    """
    Structured request-item normalization result.

    Attributes:
        normalized_items: Supported items that were normalized successfully.
        unsupported_items: Items that cannot be fulfilled from the catalog.
        ambiguous_items: Items that need clarification before proceeding.
    """

    normalized_items: List[NormalizedRequestItem] = Field(default_factory=list)
    unsupported_items: List[UnsupportedRequestItem] = Field(default_factory=list)
    ambiguous_items: List[AmbiguousRequestItem] = Field(default_factory=list)


class HistoricalQuoteRecord(BaseModel):
    """
    Historical quote record used as pricing context.

    Attributes:
        original_request: Historical customer request text.
        total_amount: Historical quoted amount.
        quote_explanation: Stored explanation for the historical quote.
        job_type: Historical job type label.
        order_size: Historical order size label.
        event_type: Historical event type label.
        order_date: Historical quote date in ISO format when known.
    """

    original_request: str = ""
    total_amount: float = Field(ge=0.0, default=0.0)
    quote_explanation: str = ""
    job_type: str = "unknown"
    order_size: str = "unknown"
    event_type: str = "unknown"
    order_date: Optional[str] = None


class FinalDecisionResult(BaseModel):
    """
    Final business decision returned by the synthesis stage.

    Attributes:
        decision: Final workflow outcome.
        delivery_feasible: Whether the approved portion can meet the deadline.
        quote_total: Approved quote total.
        notes: Decision notes for the orchestrator and user response.
    """

    decision: str
    delivery_feasible: Optional[bool] = None
    quote_total: float = Field(ge=0.0, default=0.0)
    notes: List[str] = Field(default_factory=list)


class TransactionWriteResult(BaseModel):
    """
    Summary of transaction writes performed during fulfillment.

    Attributes:
        sales_written: Number of sale transactions created.
        stock_orders_written: Number of stock-order transactions created.
        message: Human-readable execution summary.
    """

    sales_written: int = Field(ge=0, default=0)
    stock_orders_written: int = Field(ge=0, default=0)
    message: str = ""


class RequestMemoryLogResult(BaseModel):
    """
    Summary of the long-memory logging action.

    Attributes:
        logged: Whether the request was persisted successfully.
        decision: Final business decision.
        quote_total: Logged quote total.
        message: Human-readable execution summary.
    """

    logged: bool = False
    decision: str = "declined"
    quote_total: float = Field(ge=0.0, default=0.0)
    message: str = ""


def render_pydantic_contracts(model_classes: List[Type[BaseModel]]) -> str:
    """
    Render exact Pydantic model schema dumps for use inside LLM prompts.

    Args:
        model_classes: Ordered list of model classes to render.

    Returns:
        Multi-model schema dump string.
    """
    rendered_blocks: List[str] = []
    for model_class in model_classes:
        rendered_blocks.append(
            f"{model_class.__name__}.model_json_schema() = "
            f"{json.dumps(model_class.model_json_schema(), indent=2, ensure_ascii=True)}"
        )
    return "\n\n".join(rendered_blocks)


def reset_workflow_context(**values: Any) -> None:
    """
    Replace the shared workflow context used for tool fallbacks.

    Args:
        **values: Context values to seed for the current stage.
    """
    WORKFLOW_CONTEXT.clear()
    WORKFLOW_CONTEXT.update(values)


def update_workflow_context(**values: Any) -> None:
    """
    Merge new values into the shared workflow context used for tool fallbacks.

    Args:
        **values: Context values to merge into the current stage state.
    """
    WORKFLOW_CONTEXT.update(values)


def get_workflow_context(key: str, default: Any = None) -> Any:
    """
    Read a value from the shared workflow context.

    Args:
        key: Context key to read.
        default: Value to return if the key is missing.

    Returns:
        Stored context value or `default`.
    """
    return WORKFLOW_CONTEXT.get(key, default)


def _get_embedding_client() -> Optional[OpenAI]:
    """
    Create and cache an embeddings client when API credentials are available.

    Returns:
        Reusable OpenAI client configured for the Vocareum endpoint, or None
        when the embedding service is unavailable in the current environment.
    """
    global EMBEDDING_CLIENT

    if EMBEDDING_CLIENT is not None:
        return EMBEDDING_CLIENT

    api_key = os.getenv("UDACITY_OPENAI_API_KEY")
    if not api_key:
        return None

    EMBEDDING_CLIENT = OpenAI(
        base_url=OPENAI_API_BASE,
        api_key=api_key,
    )
    return EMBEDDING_CLIENT


def _normalize_embedding(vector: List[float]) -> Optional[np.ndarray]:
    """
    Normalize an embedding vector for cosine-similarity scoring.

    Args:
        vector: Raw embedding vector returned by the embeddings API.

    Returns:
        Unit-normalized embedding array, or None when the vector norm is zero.
    """
    array = np.asarray(vector, dtype=float)
    norm = float(np.linalg.norm(array))
    if norm == 0.0:
        return None
    return array / norm


def _get_text_embeddings(texts: List[str]) -> Dict[str, Optional[np.ndarray]]:
    """
    Fetch and cache embeddings for arbitrary texts used in semantic matching.

    Args:
        texts: Ordered text inputs that need embedding vectors.

    Returns:
        Mapping from input text to a cached normalized embedding vector, or
        None when the embedding service could not supply a vector.
    """
    requested_texts = [text for text in texts if text]
    if not requested_texts:
        return {}

    client = _get_embedding_client()
    if client is None:
        return {text: None for text in requested_texts}

    missing_texts = [text for text in requested_texts if text not in EMBEDDING_CACHE]
    if missing_texts:
        try:
            response = client.embeddings.create(
                model=EMBEDDING_MODEL_ID,
                input=missing_texts,
            )
            for text_value, embedding_row in zip(missing_texts, response.data):
                EMBEDDING_CACHE[text_value] = _normalize_embedding(embedding_row.embedding)
        except Exception:
            for text_value in missing_texts:
                EMBEDDING_CACHE[text_value] = None

    return {text: EMBEDDING_CACHE.get(text) for text in requested_texts}


def _normalize_free_text(value: str) -> str:
    """
    Normalize free text for fuzzy matching and alias lookup.

    Args:
        value: Raw text to normalize.

    Returns:
        Lowercased text containing only alphanumeric tokens separated by spaces.
    """
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _get_catalog_embedding_candidates(
    raw_name: str,
    limit: int = 8,
) -> List[Tuple[str, float]]:
    """
    Rank catalog items by semantic similarity to a raw request phrase.

    Args:
        raw_name: Raw item phrase from the request.
        limit: Maximum number of ranked catalog candidates to return.

    Returns:
        Ranked list of `(catalog_name, similarity_score)` tuples where the
        similarity score is scaled to the 0-1 range.
    """
    query_text = f"customer requested item: {raw_name.strip()}"
    if not raw_name.strip():
        return []

    embedding_inputs = [query_text] + list(CATALOG_EMBEDDING_TEXT.values())
    embeddings = _get_text_embeddings(embedding_inputs)
    query_embedding = embeddings.get(query_text)
    if query_embedding is None:
        return []

    scored_candidates: List[Tuple[str, float]] = []
    for catalog_name, catalog_text in CATALOG_EMBEDDING_TEXT.items():
        catalog_embedding = embeddings.get(catalog_text)
        if catalog_embedding is None:
            continue

        cosine_similarity = float(np.dot(query_embedding, catalog_embedding))
        scaled_similarity = max(0.0, min(1.0, (cosine_similarity + 1.0) / 2.0))
        scored_candidates.append((catalog_name, scaled_similarity))

    scored_candidates.sort(key=lambda entry: entry[1], reverse=True)
    return scored_candidates[:limit]


def _table_exists(table_name: str) -> bool:
    """
    Check whether a SQLite table exists in the current database.

    Args:
        table_name: Name of the table to look up.

    Returns:
        True if the table exists, otherwise False.
    """
    query = text(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name = :table_name
        """
    )
    with db_engine.connect() as conn:
        return conn.execute(query, {"table_name": table_name}).first() is not None


def _find_alias_match(raw_name: str) -> Optional[CatalogMatchResult]:
    """
    Look up a previously confirmed alias match from long memory.

    Args:
        raw_name: Raw request phrase to resolve.

    Returns:
        A stored catalog match when available, otherwise None.
    """
    if not _table_exists("alias_memory"):
        return None

    normalized_phrase = _normalize_free_text(raw_name)
    alias_df = pd.read_sql(
        """
        SELECT raw_phrase, normalized_item_name, confidence
        FROM alias_memory
        WHERE LOWER(raw_phrase) = :raw_phrase
        ORDER BY confidence DESC, times_seen DESC
        LIMIT 1
        """,
        db_engine,
        params={"raw_phrase": normalized_phrase},
    )

    if alias_df.empty:
        return None

    alias_row = alias_df.iloc[0]
    return CatalogMatchResult(
        match_type="SUPPORTED",
        normalized_name=alias_row["normalized_item_name"],
        confidence=float(alias_row["confidence"]),
        reason="Matched previously confirmed alias from long memory.",
    )


def _remember_alias_match(raw_name: str, normalized_name: str, confidence: float) -> None:
    """
    Persist a successful alias resolution for future requests.

    Args:
        raw_name: Raw request phrase that was resolved.
        normalized_name: Supported catalog item selected for the phrase.
        confidence: Confidence score for the resolution.
    """
    if not _table_exists("alias_memory"):
        return

    normalized_phrase = _normalize_free_text(raw_name)
    timestamp = datetime.now().isoformat()

    with db_engine.begin() as conn:
        existing_row = conn.execute(
            text(
                """
                SELECT times_seen
                FROM alias_memory
                WHERE raw_phrase = :raw_phrase
                AND normalized_item_name = :normalized_item_name
                """
            ),
            {
                "raw_phrase": normalized_phrase,
                "normalized_item_name": normalized_name,
            },
        ).first()

        if existing_row:
            conn.execute(
                text(
                    """
                    UPDATE alias_memory
                    SET confidence = :confidence,
                        times_seen = :times_seen,
                        last_seen = :last_seen
                    WHERE raw_phrase = :raw_phrase
                    AND normalized_item_name = :normalized_item_name
                    """
                ),
                {
                    "confidence": confidence,
                    "times_seen": int(existing_row.times_seen) + 1,
                    "last_seen": timestamp,
                    "raw_phrase": normalized_phrase,
                    "normalized_item_name": normalized_name,
                },
            )
        else:
            pd.DataFrame(
                [
                    {
                        "raw_phrase": normalized_phrase,
                        "normalized_item_name": normalized_name,
                        "confidence": confidence,
                        "times_seen": 1,
                        "last_seen": timestamp,
                    }
                ]
            ).to_sql("alias_memory", conn, if_exists="append", index=False)


def _strip_request_context_for_item_parsing(raw_request: str) -> str:
    """
    Remove non-item clauses that interfere with quantity-based parsing.

    Args:
        raw_request: Full customer request text.

    Returns:
        Request text with delivery/date boilerplate removed.
    """
    cleaned_request = raw_request
    patterns = [
        r"\(Date of request:\s*\d{4}-\d{2}-\d{2}\)",
        r"(?i)\bplease confirm the order and delivery schedule\b[^.\n!]*[.\n!]*",
        r"(?i)\b(?:please\s+)?(?:ensure\s+)?delivery\b[^.\n!]*[.\n!]*",
        r"(?i)\b(?:i|we)\s+need[^.\n!]*\bdeliver(?:ed|y)\b[^.\n!]*[.\n!]*",
        r"(?i)\bthe supplies must be delivered\b[^.\n!]*[.\n!]*",
        r"(?i)\bplease deliver\b[^.\n!]*[.\n!]*",
        r"(?i)\bthank you\b[.\n!]*",
    ]

    for pattern in patterns:
        cleaned_request = re.sub(pattern, " ", cleaned_request)

    cleaned_request = cleaned_request.replace("\r", "\n")
    cleaned_request = re.sub(r"[•\-]\s*", "\n", cleaned_request)
    cleaned_request = re.sub(r"\s+", " ", cleaned_request)
    return cleaned_request.strip()


def _extract_candidate_item_segments(cleaned_request: str) -> List[str]:
    """
    Split cleaned request text into quantity-led candidate item segments.

    Args:
        cleaned_request: Request text after boilerplate removal.

    Returns:
        List of candidate item segments that start with a quantity.
    """
    quantity_matches = list(
        re.finditer(r"(?<![\w-])\d{1,3}(?:,\d{3})*(?=\s+[A-Za-z])", cleaned_request)
    )
    if not quantity_matches:
        return []

    segments: List[str] = []
    for index, match in enumerate(quantity_matches):
        end = quantity_matches[index + 1].start() if index + 1 < len(quantity_matches) else len(cleaned_request)
        segment = cleaned_request[match.start():end]
        segment = segment.strip(" ,;:.")
        segment = re.sub(r"^(?:and|plus)\s+", "", segment, flags=re.IGNORECASE)
        segment = re.split(r"(?i)\bfor\b", segment, maxsplit=1)[0].strip(" ,;:.")
        if segment:
            segments.append(segment)
    return segments


def _parse_item_segment(segment: str) -> Optional[ParsedRequestItem]:
    """
    Parse one quantity-led segment into a structured request item.

    Args:
        segment: Candidate item segment extracted from the request.

    Returns:
        Parsed item when the segment matches the expected structure, otherwise None.
    """
    with_of_match = re.match(
        r"""
        ^(?P<quantity>\d{1,3}(?:,\d{3})*)
        \s+
        (?P<unit>[a-zA-Z][a-zA-Z0-9%\"'./()-]*)
        \s+of\s+
        (?P<raw_name>.+)$
        """,
        segment,
        flags=re.IGNORECASE | re.VERBOSE,
    )
    if with_of_match:
        raw_name = with_of_match.group("raw_name").strip(" ,;:.")
        raw_name = re.sub(r"(?:,\s*)?(?:and|plus)\s*$", "", raw_name, flags=re.IGNORECASE)
        return ParsedRequestItem(
            raw_name=raw_name.strip(" ,;:."),
            quantity=int(with_of_match.group("quantity").replace(",", "")),
            unit=with_of_match.group("unit").lower(),
        )

    without_of_match = re.match(
        r"^(?P<quantity>\d{1,3}(?:,\d{3})*)\s+(?P<remainder>.+)$",
        segment,
        flags=re.IGNORECASE,
    )
    if not without_of_match:
        return None

    quantity = int(without_of_match.group("quantity").replace(",", ""))
    remainder = without_of_match.group("remainder").strip(" ,;:.")
    tokens = remainder.split()
    if not tokens:
        return None

    first_token = tokens[0].lower()
    if first_token in COMMON_UNIT_WORDS and len(tokens) > 1:
        unit = first_token
        raw_name = " ".join(tokens[1:])
    else:
        unit = "units"
        raw_name = remainder

    raw_name = re.sub(r"(?:,\s*)?(?:and|plus)\s*$", "", raw_name, flags=re.IGNORECASE)
    return ParsedRequestItem(
        raw_name=raw_name.strip(" ,;:."),
        quantity=quantity,
        unit=unit,
    )


def parse_request_items_from_text(raw_request: str) -> List[ParsedRequestItem]:
    """
    Deterministically parse request items from raw customer text.

    Args:
        raw_request: Original customer request text.

    Returns:
        Parsed request items extracted from the request.
    """
    cleaned_request = _strip_request_context_for_item_parsing(raw_request)
    segments = _extract_candidate_item_segments(cleaned_request)

    parsed_items: List[ParsedRequestItem] = []
    for segment in segments:
        parsed_item = _parse_item_segment(segment)
        if parsed_item:
            parsed_items.append(parsed_item)

    return parsed_items


def _candidate_catalog_names_from_phrase(raw_name: str) -> List[str]:
    """
    Generate plausible catalog candidates for a raw item phrase.

    Args:
        raw_name: Raw item phrase from the request.

    Returns:
        Ordered list of candidate catalog item names.
    """
    normalized_phrase = _normalize_free_text(raw_name)
    candidates: List[str] = []

    for keyword, catalog_name in SPECIAL_KEYWORD_CANDIDATES.items():
        if keyword in normalized_phrase and catalog_name in CATALOG_BY_NAME:
            candidates.append(catalog_name)

    for catalog_name, normalized_catalog_name in CATALOG_NAME_NORMALIZED.items():
        if normalized_catalog_name in normalized_phrase or normalized_phrase in normalized_catalog_name:
            candidates.append(catalog_name)

    close_matches = difflib.get_close_matches(
        normalized_phrase,
        list(CATALOG_NAME_NORMALIZED.values()),
        n=5,
        cutoff=0.45,
    )
    for close_match in close_matches:
        for catalog_name, normalized_catalog_name in CATALOG_NAME_NORMALIZED.items():
            if normalized_catalog_name == close_match:
                candidates.append(catalog_name)
                break

    deduped_candidates: List[str] = []
    for candidate in candidates:
        if candidate not in deduped_candidates:
            deduped_candidates.append(candidate)

    return deduped_candidates


def _score_catalog_candidate(raw_name: str, catalog_name: str) -> float:
    """
    Score how well a catalog item matches a raw request phrase.

    Args:
        raw_name: Raw item phrase from the request.
        catalog_name: Candidate supported catalog item name.

    Returns:
        Score between 0 and 1 representing match confidence.
    """
    normalized_phrase = _normalize_free_text(raw_name)
    normalized_catalog_name = CATALOG_NAME_NORMALIZED[catalog_name]
    raw_tokens = set(normalized_phrase.split())
    catalog_tokens = set(normalized_catalog_name.split())

    sequence_score = difflib.SequenceMatcher(
        None,
        normalized_phrase,
        normalized_catalog_name,
    ).ratio()
    overlap_score = len(raw_tokens & catalog_tokens) / max(len(catalog_tokens), 1)
    score = 0.55 * sequence_score + 0.35 * overlap_score

    if raw_tokens & {"a4", "a5", "letter", "legal", "24x36", "36"} and raw_tokens & catalog_tokens:
        score += 0.05
    if raw_tokens & {
        "glossy",
        "matte",
        "recycled",
        "kraft",
        "construction",
        "uncoated",
        "cardstock",
        "colored",
        "color",
    } and raw_tokens & catalog_tokens:
        score += 0.16
    if raw_tokens & {"plates", "plate", "cups", "cup", "napkins", "napkin", "envelopes", "envelope", "folders", "folder", "flyers", "flyer"} and raw_tokens & catalog_tokens:
        score += 0.1

    return min(score, 1.0)


def resolve_catalog_item(raw_name: str) -> Tuple[CatalogMatchResult, List[str]]:
    """
    Resolve a raw request phrase into a supported catalog item when possible.

    Args:
        raw_name: Raw item phrase from the request.

    Returns:
        Tuple containing the resolution result and the top candidate names considered.
    """
    alias_match = _find_alias_match(raw_name)
    if alias_match:
        return alias_match, [alias_match.normalized_name] if alias_match.normalized_name else []

    lexical_candidates = _candidate_catalog_names_from_phrase(raw_name)
    semantic_candidates = _get_catalog_embedding_candidates(raw_name)
    semantic_score_by_name = {
        candidate_name: score
        for candidate_name, score in semantic_candidates
    }
    candidate_names = list(dict.fromkeys(
        lexical_candidates + [candidate_name for candidate_name, _ in semantic_candidates]
    ))
    if not candidate_names:
        return (
            CatalogMatchResult(
                match_type="UNSUPPORTED",
                normalized_name=None,
                confidence=0.0,
                reason="No supported catalog item resembled the requested phrase.",
            ),
            [],
        )

    ranked_candidates = []
    raw_tokens = set(_normalize_free_text(raw_name).split())
    material_tokens = {
        "glossy",
        "matte",
        "cardstock",
        "colored",
        "color",
        "recycled",
        "kraft",
        "construction",
        "uncoated",
        "banner",
        "poster",
    }
    size_tokens = {"a4", "a5", "letter", "legal", "24x36", "36", "gsm", "lb"}
    for candidate_name in candidate_names:
        lexical_score = _score_catalog_candidate(raw_name, candidate_name)
        semantic_score = semantic_score_by_name.get(candidate_name, 0.0)
        heuristic_bonus = 0.08 if candidate_name in lexical_candidates else 0.0
        catalog_tokens = set(CATALOG_NAME_NORMALIZED[candidate_name].split())
        material_bonus = 0.0
        if (raw_tokens & material_tokens) and (catalog_tokens & material_tokens):
            material_bonus = 0.07
        size_bonus = 0.0
        if (raw_tokens & size_tokens) and (catalog_tokens & size_tokens):
            size_bonus = 0.02
        combined_score = min(
            1.0,
            (0.68 * semantic_score)
            + (0.24 * lexical_score)
            + heuristic_bonus
            + material_bonus
            + size_bonus,
        )
        ranked_candidates.append(
            (
                candidate_name,
                combined_score,
                semantic_score,
                lexical_score,
            )
        )

    ranked_candidates.sort(key=lambda entry: entry[1], reverse=True)

    best_name, best_score, best_semantic_score, best_lexical_score = ranked_candidates[0]
    top_candidates = [name for name, _, _, _ in ranked_candidates[:3]]
    second_score = ranked_candidates[1][1] if len(ranked_candidates) > 1 else 0.0

    if best_score < 0.62 or (
        best_lexical_score < 0.2 and best_semantic_score < 0.82
    ):
        return (
            CatalogMatchResult(
                match_type="UNSUPPORTED",
                normalized_name=None,
                confidence=best_score,
                reason=(
                    "Embedding similarity and lexical overlap were both too weak "
                    "to trust the best catalog match."
                ),
            ),
            top_candidates,
        )

    if len(ranked_candidates) > 1 and abs(best_score - second_score) <= 0.02:
        return (
            CatalogMatchResult(
                match_type="AMBIGUOUS",
                normalized_name=None,
                confidence=best_score,
                reason=(
                    "Multiple supported catalog items had nearly identical "
                    "similarity scores."
                ),
            ),
            top_candidates,
        )

    return (
        CatalogMatchResult(
            match_type="SUPPORTED",
            normalized_name=best_name,
            confidence=best_score,
            reason=(
                "Resolved using embedding similarity backed by lexical matching "
                f"(semantic={best_semantic_score:.2f}, lexical={best_lexical_score:.2f})."
            ),
        ),
        top_candidates,
    )


def convert_item_quantity(
    quantity: int,
    unit: str,
    normalized_name: str,
) -> Tuple[Optional[int], Optional[str], Optional[str]]:
    """
    Convert a request quantity into the workflow's normalized quantity scheme.

    Args:
        quantity: Requested quantity from the raw item parse.
        unit: Requested unit text from the raw item parse.
        normalized_name: Supported catalog item selected for the request phrase.

    Returns:
        Tuple of normalized quantity, normalized unit, and an optional issue message.
    """
    normalized_unit_key = unit.lower().strip()
    catalog_category = CATALOG_BY_NAME[normalized_name]["category"]

    if normalized_unit_key in {"box", "boxes", "packet", "packets", "pack", "packs"}:
        return None, None, "Pack-based quantities need a per-pack size before they can be normalized safely."

    if normalized_unit_key in UNIT_NORMALIZATION:
        normalized_unit, multiplier = UNIT_NORMALIZATION[normalized_unit_key]
        if normalized_unit == "sheets" and catalog_category == "product":
            normalized_unit = "units"
        return quantity * multiplier, normalized_unit, None

    if normalized_unit_key in {"roll", "rolls"} and "banner" in _normalize_free_text(normalized_name):
        return quantity, "rolls", None

    return quantity, "units", None


def normalize_request_items(parsed_items: List[ParsedRequestItem]) -> NormalizationResult:
    """
    Normalize parsed request items into supported catalog items.

    Args:
        parsed_items: Parsed request items extracted from the raw request.

    Returns:
        Structured normalization result for the request.
    """
    normalized_items: List[NormalizedRequestItem] = []
    unsupported_items: List[UnsupportedRequestItem] = []
    ambiguous_items: List[AmbiguousRequestItem] = []

    for parsed_item in parsed_items:
        resolution, candidate_names = resolve_catalog_item(parsed_item.raw_name)

        if resolution.match_type == "UNSUPPORTED" or not resolution.normalized_name:
            unsupported_items.append(
                UnsupportedRequestItem(
                    raw_name=parsed_item.raw_name,
                    quantity=parsed_item.quantity,
                    unit=parsed_item.unit,
                    reason=resolution.reason,
                )
            )
            continue

        if resolution.match_type == "AMBIGUOUS":
            ambiguous_items.append(
                AmbiguousRequestItem(
                    raw_name=parsed_item.raw_name,
                    quantity=parsed_item.quantity,
                    unit=parsed_item.unit,
                    candidate_names=candidate_names,
                    reason=resolution.reason,
                )
            )
            continue

        normalized_quantity, normalized_unit, issue = convert_item_quantity(
            quantity=parsed_item.quantity,
            unit=parsed_item.unit,
            normalized_name=resolution.normalized_name,
        )
        if issue or normalized_quantity is None or normalized_unit is None:
            ambiguous_items.append(
                AmbiguousRequestItem(
                    raw_name=parsed_item.raw_name,
                    quantity=parsed_item.quantity,
                    unit=parsed_item.unit,
                    candidate_names=[resolution.normalized_name],
                    reason=issue or "The item quantity could not be normalized safely.",
                )
            )
            continue

        normalized_items.append(
            NormalizedRequestItem(
                raw_name=parsed_item.raw_name,
                normalized_name=resolution.normalized_name,
                quantity=parsed_item.quantity,
                unit=parsed_item.unit,
                normalized_quantity=normalized_quantity,
                normalized_unit=normalized_unit,
                supported=True,
                confidence=resolution.confidence,
                unit_price=float(CATALOG_BY_NAME[resolution.normalized_name]["unit_price"]),
            )
        )

        if resolution.confidence >= 0.7:
            _remember_alias_match(
                raw_name=parsed_item.raw_name,
                normalized_name=resolution.normalized_name,
                confidence=resolution.confidence,
            )

    return NormalizationResult(
        normalized_items=normalized_items,
        unsupported_items=unsupported_items,
        ambiguous_items=ambiguous_items,
    )





def create_memory_tables(db_engine: Engine) -> None:
    """
    Create persistent long-memory tables used by the multi-agent workflow.
    """
    alias_memory_schema = pd.DataFrame(
        columns=[
            "raw_phrase",
            "normalized_item_name",
            "confidence",
            "times_seen",
            "last_seen",
        ]
    )
    alias_memory_schema.to_sql("alias_memory", db_engine, if_exists="append", index=False)

    request_memory_schema = pd.DataFrame(
        columns=[
            "request_text",
            "request_date",
            "delivery_deadline",
            "job_type",
            "order_size",
            "event_type",
            "mood",
            "normalized_items",
            "unsupported_items",
            "decision",
            "quote_total",
            "delivery_feasible",
            "notes",
            "timestamp",
        ]
    )
    request_memory_schema.to_sql("request_memory", db_engine, if_exists="append", index=False)


def make_request_state(raw_request: str, request_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Build the ephemeral shared state used to process a single customer request.
    """
    return {
        "request_id": request_id,
        "raw_request": raw_request,
        "intent": "unknown",
        "urgency": "normal",
        "request_date": None,
        "delivery_deadline": None,
        "request_profile": {
            "job_type": "unknown",
            "order_size": "unknown",
            "event_type": "unknown",
            "mood": "unknown",
        },
        "parsed_items": [],
        "normalized_items": [],
        "unsupported_items": [],
        "ambiguous_items": [],
        "inventory_result": {
            "items": [],
            "delivery_feasible": None,
            "overall_shortage": False,
        },
        "reorder_plan": [],
        "quote_result": {
            "base_total": 0.0,
            "discount_rate": 0.0,
            "discount_amount": 0.0,
            "final_total": 0.0,
            "similar_quotes_used": 0,
            "pricing_notes": [],
            "explanation": "",
        },
        "final_decision": "pending",
        "final_response": "",
        "errors": [],
    }


SHOWCASE_STAGE_ORDER = [
    ("analysis", "Request Analysis", "Breaking the request into validated structure."),
    ("inventory", "Inventory Check", "Checking stock depth and delivery feasibility."),
    ("quote", "Quote Engine", "Building pricing from catalog and historical context."),
    ("synthesis", "Fulfillment", "Combining results into the final decision."),
]


def normalize_display_mode(display_mode: str) -> str:
    """
    Normalize external display-mode input into a supported internal value.

    Args:
        display_mode: Requested terminal presentation mode.

    Returns:
        One of `showcase`, `debug`, or `quiet`.
    """
    normalized_mode = (display_mode or "quiet").strip().lower()
    if normalized_mode not in {"showcase", "debug", "quiet"}:
        return "quiet"
    return normalized_mode


def format_currency(value: Any) -> str:
    """
    Format a numeric value as a customer-facing currency string.

    Args:
        value: Numeric value to format.

    Returns:
        Value rendered as US dollars with two decimal places.
    """
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def build_decision_response(
    decision: str,
    quote_total: float,
    notes: Optional[List[str]] = None,
) -> str:
    """
    Build the plain-text customer response returned by the orchestrator.

    Args:
        decision: Final workflow decision string.
        quote_total: Final quoted amount.
        notes: Optional decision notes.

    Returns:
        Multi-line response string.
    """
    notes_str = "; ".join(notes or []) if notes else "None"
    return (
        f"Decision: {decision}\n"
        f"Quote Total: {format_currency(quote_total)}\n"
        f"Notes: {notes_str}"
    )


class WorkflowShowcase:
    """
    Rich-powered customer-facing terminal presentation for the multi-agent flow.

    The showcase layer never changes workflow decisions. It only converts the
    internal request state into a curated terminal experience while the agent
    pipeline runs in the background.
    """

    def __init__(
        self,
        request_id: str,
        raw_request: str,
        request_context: Optional[Dict[str, Any]] = None,
        animate: bool = True,
    ):
        """
        Initialize a showcase session for one customer request.

        Args:
            request_id: Stable request identifier shown in the UI.
            raw_request: Original customer request text.
            request_context: Optional request metadata supplied by the caller.
            animate: Whether to add short animation pauses between milestones.
        """
        self.request_id = request_id
        self.raw_request = raw_request
        self.request_context = request_context or {}
        self.animate = animate
        self.console = Console() if Console is not None else None
        self.enabled = all(
            dependency is not None
            for dependency in (Console, Group, Live, Panel, Spinner, Table, Text, box)
        )
        self.live = None
        self.stage_status = {
            stage_key: "pending"
            for stage_key, _, _ in SHOWCASE_STAGE_ORDER
        }
        self.stage_details = {
            stage_key: default_detail
            for stage_key, _, default_detail in SHOWCASE_STAGE_ORDER
        }
        self.events: List[Tuple[str, str, str]] = []
        self.request_state: Dict[str, Any] = make_request_state(raw_request, request_id)
        self.current_stage: Optional[str] = None
        self.final_card: Optional[Tuple[str, float, List[str]]] = None

    def open(self) -> None:
        """
        Open the live terminal dashboard for this request.
        """
        headline = (
            f"Receiving request {self.request_id}"
            if self.request_id
            else "Receiving customer request"
        )
        self.add_event(headline, style="bright_cyan")

        if not self.enabled:
            print(f"\n=== Request {self.request_id} ===")
            print(textwrap.shorten(self.raw_request.replace("\n", " "), width=120, placeholder="..."))
            return

        self.live = Live(
            self.render_dashboard(),
            console=self.console,
            refresh_per_second=12,
            transient=False,
        )
        self.live.__enter__()
        self.refresh()

    def close(self) -> None:
        """
        Close the live dashboard cleanly.
        """
        if self.live is not None:
            self.live.__exit__(None, None, None)
            self.live = None

        if self.enabled and self.console is not None and self.final_card is not None:
            self.console.print()
            decision, quote_total, notes = self.final_card
            note_text = "; ".join(notes or []) if notes else "No additional notes."
            final_table = Table.grid(padding=(0, 2))
            final_table.add_column(style="bold bright_white", justify="right")
            final_table.add_column(style="bright_white")
            final_table.add_row("Decision", decision)
            final_table.add_row("Quote", format_currency(quote_total))
            final_table.add_row("Notes", note_text)

            decision_style = "green" if "approved" in decision else "yellow"
            self.console.print(
                Panel(
                    final_table,
                    title=f"[bold {decision_style}]Customer Outcome[/bold {decision_style}]",
                    border_style=decision_style,
                    box=box.ASCII,
                    padding=(1, 2),
                )
            )
            self.final_card = None

    def refresh(self) -> None:
        """
        Refresh the rendered dashboard with the current internal state.
        """
        if self.live is not None:
            self.live.update(self.render_dashboard(), refresh=True)

    def pulse(self, steps: int = 1, delay_seconds: float = 0.08) -> None:
        """
        Add a brief animation pause after notable milestones.

        Args:
            steps: Number of refresh cycles to perform.
            delay_seconds: Delay between refresh cycles.
        """
        if not self.animate:
            return

        for _ in range(max(steps, 0)):
            self.refresh()
            time.sleep(delay_seconds)

    def add_event(self, message: str, style: str = "white") -> None:
        """
        Append a short status line to the event feed.

        Args:
            message: Human-readable event summary.
            style: Rich text style name used for the message.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.events.append((timestamp, message, style))
        self.events = self.events[-8:]
        self.refresh()
        if not self.enabled:
            print(f"[{timestamp}] {message}")

    def update_state(self, request_state: Dict[str, Any]) -> None:
        """
        Replace the showcase snapshot with the latest request state.

        Args:
            request_state: Current orchestrator state for the request.
        """
        self.request_state = request_state
        self.refresh()

    def start_stage(self, stage_key: str, detail: str) -> None:
        """
        Mark a stage as active and update the dashboard.

        Args:
            stage_key: Internal stage identifier.
            detail: Human-readable detail line for the stage.
        """
        self.current_stage = stage_key
        self.stage_status[stage_key] = "active"
        self.stage_details[stage_key] = detail
        self.add_event(detail, style="bright_cyan")

    def complete_stage(
        self,
        stage_key: str,
        detail: str,
        request_state: Optional[Dict[str, Any]] = None,
    ) -> None:
        """
        Mark a stage as completed.

        Args:
            stage_key: Internal stage identifier.
            detail: Human-readable completion detail.
            request_state: Optional latest request state snapshot.
        """
        self.stage_status[stage_key] = "done"
        self.stage_details[stage_key] = detail
        if request_state is not None:
            self.request_state = request_state
        self.add_event(detail, style="green")
        self.pulse(steps=2)

    def skip_stage(self, stage_key: str, detail: str) -> None:
        """
        Mark a stage as skipped.

        Args:
            stage_key: Internal stage identifier.
            detail: Human-readable skip reason.
        """
        self.stage_status[stage_key] = "skipped"
        self.stage_details[stage_key] = detail
        self.add_event(detail, style="yellow")

    def fail_stage(self, stage_key: str, error_message: str) -> None:
        """
        Mark a stage as failed.

        Args:
            stage_key: Internal stage identifier.
            error_message: Error summary shown in the dashboard.
        """
        self.stage_status[stage_key] = "error"
        self.stage_details[stage_key] = error_message
        self.add_event(error_message, style="bold red")
        self.pulse(steps=2)

    def finish(
        self,
        decision: str,
        quote_total: float,
        notes: Optional[List[str]] = None,
    ) -> None:
        """
        Render the final decision milestone.

        Args:
            decision: Final workflow decision.
            quote_total: Final quoted amount.
            notes: Optional final notes.
        """
        note_text = "; ".join(notes or []) if notes else "No additional notes."
        self.add_event(
            f"Decision locked: {decision} at {format_currency(quote_total)}.",
            style="bold green",
        )

        if not self.enabled:
            print(build_decision_response(decision, quote_total, notes))
            return

        self.final_card = (decision, quote_total, notes or [])

    def render_dashboard(self) -> Any:
        """
        Build the current rich renderable for the live terminal.

        Returns:
            Rich renderable object when Rich is available, otherwise a plain
            string fallback.
        """
        if not self.enabled:
            return ""

        top_row = Table.grid(expand=True)
        top_row.add_column(ratio=5)
        top_row.add_column(ratio=4)
        top_row.add_row(
            self._build_stage_panel(),
            self._build_snapshot_panel(),
        )

        bottom_row = Table.grid(expand=True)
        bottom_row.add_column(ratio=4)
        bottom_row.add_column(ratio=5)
        bottom_row.add_row(
            self._build_metrics_panel(),
            self._build_event_panel(),
        )

        return Group(
            self._build_header_panel(),
            top_row,
            bottom_row,
        )

    def _build_header_panel(self) -> Any:
        """
        Render the showcase header with progress and request metadata.

        Returns:
            Rich header panel.
        """
        completed_count = sum(
            1 for status in self.stage_status.values() if status == "done"
        )
        progress_slots = len(SHOWCASE_STAGE_ORDER)
        progress_fill = "#" * completed_count
        progress_empty = "-" * (progress_slots - completed_count)
        progress_bar = f"[{progress_fill}{progress_empty}] {completed_count}/{progress_slots}"

        context_label = self.request_context.get("context_label", "Customer request")
        request_date = self.request_context.get("request_date") or self.request_state.get("request_date") or "unknown"

        header_text = Text()
        header_text.append("MUNDER DIFFLIN // DIAMOND ELITE REQUEST PIPELINE\n", style="bold bright_white")
        header_text.append(f"{context_label} | Request {self.request_id} | {request_date}\n", style="cyan")
        header_text.append(f"Pipeline Progress {progress_bar}", style="bright_yellow")

        return Panel(
            header_text,
            border_style="bright_cyan",
            box=box.ASCII,
            padding=(1, 2),
        )

    def _build_stage_panel(self) -> Any:
        """
        Render the stage timeline panel.

        Returns:
            Rich panel containing stage progress.
        """
        status_map = {
            "pending": ("PENDING", "dim"),
            "active": ("ACTIVE", "bold bright_cyan"),
            "done": ("DONE", "bold green"),
            "skipped": ("SKIPPED", "bold yellow"),
            "error": ("ERROR", "bold red"),
        }

        stage_lines: List[Text] = []
        for stage_key, stage_label, _ in SHOWCASE_STAGE_ORDER:
            status_label, status_style = status_map[self.stage_status[stage_key]]
            detail = self.stage_details[stage_key]
            stage_line = Text()
            stage_line.append(f"{status_label:<7} ", style=status_style)
            stage_line.append(f"{stage_label}: ", style="bold bright_white")
            stage_line.append(
                textwrap.shorten(detail, width=62, placeholder="..."),
                style="white",
            )
            stage_lines.append(stage_line)

        return Panel(
            Group(*stage_lines),
            title="[bold bright_white]Pipeline Timeline[/bold bright_white]",
            border_style="bright_blue",
            box=box.ASCII,
        )

    def _build_snapshot_panel(self) -> Any:
        """
        Render a concise request snapshot panel.

        Returns:
            Rich panel summarizing the active request.
        """
        profile = self.request_state.get("request_profile", {})
        deadline = self.request_state.get("delivery_deadline") or "unknown"
        supported_count = len(self.request_state.get("normalized_items", []))
        unsupported_count = len(self.request_state.get("unsupported_items", []))
        ambiguous_count = len(self.request_state.get("ambiguous_items", []))
        item_preview = ", ".join(
            item.get("normalized_name", item.get("raw_name", "unknown"))
            for item in self.request_state.get("normalized_items", [])[:3]
        )
        if not item_preview:
            item_preview = "Waiting for catalog matching."

        snapshot = Table.grid(padding=(0, 1))
        snapshot.add_column(style="bold bright_white", justify="right")
        snapshot.add_column(style="white")
        snapshot.add_row("Event", str(profile.get("event_type", "unknown")))
        snapshot.add_row("Order Size", str(profile.get("order_size", "unknown")))
        snapshot.add_row("Deadline", str(deadline))
        snapshot.add_row("Supported", str(supported_count))
        snapshot.add_row("Unsupported", str(unsupported_count))
        snapshot.add_row("Ambiguous", str(ambiguous_count))
        snapshot.add_row(
            "Items",
            textwrap.shorten(item_preview, width=42, placeholder="..."),
        )
        snapshot.add_row(
            "Request",
            textwrap.shorten(
                self.raw_request.replace("\n", " "),
                width=42,
                placeholder="...",
            ),
        )

        return Panel(
            snapshot,
            title="[bold bright_white]Request Snapshot[/bold bright_white]",
            border_style="bright_white",
            box=box.ASCII,
        )

    def _build_metrics_panel(self) -> Any:
        """
        Render key inventory and quote metrics.

        Returns:
            Rich metrics panel.
        """
        inventory_result = self.request_state.get("inventory_result", {})
        quote_result = self.request_state.get("quote_result", {})
        normalized_items = self.request_state.get("normalized_items", [])
        item_preview = ", ".join(
            item.get("normalized_name", item.get("raw_name", "unknown"))
            for item in normalized_items[:3]
        ) or "Catalog matching in progress."

        shortage_count = sum(
            1
            for item in inventory_result.get("items", [])
            if int(item.get("shortage", 0)) > 0
        )
        delivery_feasible = inventory_result.get("delivery_feasible")
        delivery_text = (
            "Yes"
            if delivery_feasible is True
            else "No"
            if delivery_feasible is False
            else "Pending"
        )

        metrics = Table.grid(padding=(0, 1))
        metrics.add_column(style="bold bright_white", justify="right")
        metrics.add_column(style="white")
        metrics.add_row("Matched Items", item_preview)
        metrics.add_row("Shortages", str(shortage_count))
        metrics.add_row("Delivery Window", delivery_text)
        metrics.add_row("Base Quote", format_currency(quote_result.get("base_total", 0.0)))
        metrics.add_row("Final Quote", format_currency(quote_result.get("final_total", 0.0)))
        metrics.add_row("Similar Quotes", str(quote_result.get("similar_quotes_used", 0)))
        metrics.add_row(
            "Cash Snapshot",
            format_currency(self.request_context.get("cash_balance")),
        )
        metrics.add_row(
            "Inventory Snapshot",
            format_currency(self.request_context.get("inventory_value")),
        )

        return Panel(
            metrics,
            title="[bold bright_white]Live Metrics[/bold bright_white]",
            border_style="bright_green",
            box=box.ASCII,
        )

    def _build_event_panel(self) -> Any:
        """
        Render the rolling event feed.

        Returns:
            Rich panel for recent activity.
        """
        feed_lines: List[Text] = []
        for timestamp, message, style in self.events[-8:]:
            event_line = Text()
            event_line.append(f"{timestamp} ", style="dim")
            event_line.append(message, style=style)
            feed_lines.append(event_line)

        if not feed_lines:
            feed_lines = [Text("Waiting for the first workflow event...", style="dim")]

        return Panel(
            Group(*feed_lines),
            title="[bold bright_white]Signal Feed[/bold bright_white]",
            border_style="bright_yellow",
            box=box.ASCII,
        )

@tool
def analyze_request_metadata_tool(
    raw_request: str,
    intent: str,
    urgency: str,
    request_date: Optional[str] = None,
    delivery_deadline: Optional[str] = None,
    job_type: str = "unknown",
    order_size: str = "unknown",
    event_type: str = "unknown",
    mood: str = "unknown",
) -> RequestMetadataResult:
    """
    Validate and structure request-level metadata inferred by the analysis agent.

    Args:
        raw_request: Original customer request text.
        intent: Workflow intent label. Must be one of inventory, quote,
            fulfillment, mixed, or unknown.
        urgency: Request urgency label. Must be normal or urgent.
        request_date: Request date in YYYY-MM-DD format when known.
        delivery_deadline: Delivery deadline in YYYY-MM-DD format when known.
        job_type: Inferred or provided job type.
        order_size: Inferred or provided order size.
        event_type: Inferred or provided event type.
        mood: Inferred request mood.

    Returns:
        Validated structured metadata for the request.
    """
    allowed_intents = {"inventory", "quote", "fulfillment", "mixed", "unknown"}
    allowed_urgency = {"normal", "urgent"}

    validated_intent = intent if intent in allowed_intents else "unknown"
    validated_urgency = urgency if urgency in allowed_urgency else "normal"

    profile = RequestProfile(
        job_type=job_type or "unknown",
        order_size=order_size or "unknown",
        event_type=event_type or "unknown",
        mood=mood or "unknown",
    )

    result = RequestMetadataResult(
        raw_request=raw_request,
        intent=validated_intent,
        urgency=validated_urgency,
        request_date=request_date,
        delivery_deadline=delivery_deadline,
        request_profile=profile,
    ).model_dump()
    update_workflow_context(
        raw_request=raw_request,
        request_metadata=result,
        request_profile=result["request_profile"],
        request_date=request_date,
        delivery_deadline=delivery_deadline,
    )
    return result

@tool
def parse_request_items_tool(items: Optional[List[ParsedRequestItem]] = None) -> List[ParsedRequestItem]:
    """
    Validate the request items extracted by the analysis agent.

    Args:
        items: Item dictionaries extracted from the request by the analysis agent.

    Returns:
        Validated parsed request items.
    """
    source_items = items
    if source_items is None:
        raw_request = get_workflow_context("raw_request")
        if not raw_request:
            return []
        source_items = [
            item.model_dump()
            for item in parse_request_items_from_text(raw_request)
        ]

    validated_items: List[Dict[str, Any]] = []
    for raw_item in source_items:
        item = ParsedRequestItem.model_validate(raw_item)
        cleaned_name = re.sub(
            rf"^\s*{item.quantity}\s+{re.escape(item.unit)}\s+(?:of\s+)?",
            "",
            item.raw_name,
            flags=re.IGNORECASE,
        ).strip()
        cleaned_name = cleaned_name or item.raw_name
        validated_items.append(
            ParsedRequestItem(
                raw_name=cleaned_name,
                quantity=item.quantity,
                unit=item.unit,
            ).model_dump()
        )
    update_workflow_context(parsed_items=validated_items)
    return validated_items

@tool
def normalize_request_items_tool(
    normalized_items: Optional[List[NormalizedRequestItem]] = None,
    unsupported_items: Optional[List[UnsupportedRequestItem]] = None,
    ambiguous_items: Optional[List[AmbiguousRequestItem]] = None,
) -> NormalizationResult:
    """
    Validate the item normalization output produced by the analysis agent.

    Args:
        normalized_items: Supported normalized item records. When omitted, the
            tool will normalize the current workflow's parsed items directly.
        unsupported_items: Unsupported item records.
        ambiguous_items: Ambiguous item records.

    Returns:
        Structured normalization result.
    """
    should_use_context_normalization = (
        normalized_items is None and unsupported_items is None and ambiguous_items is None
    )
    if not should_use_context_normalization:
        provided_groups = [
            normalized_items or [],
            unsupported_items or [],
            ambiguous_items or [],
        ]
        if not any(provided_groups) and (
            get_workflow_context("parsed_items") or get_workflow_context("raw_request")
        ):
            should_use_context_normalization = True

    if should_use_context_normalization:
        parsed_items_context = get_workflow_context("parsed_items", [])
        parsed_items = [
            ParsedRequestItem.model_validate(item)
            for item in parsed_items_context
        ]
        if not parsed_items:
            raw_request = get_workflow_context("raw_request")
            if raw_request:
                parsed_items = parse_request_items_from_text(raw_request)
                update_workflow_context(
                    parsed_items=[item.model_dump() for item in parsed_items]
                )

        result = normalize_request_items(parsed_items).model_dump()
        update_workflow_context(
            normalized_items=result["normalized_items"],
            unsupported_items=result["unsupported_items"],
            ambiguous_items=result["ambiguous_items"],
            normalization_result=result,
        )
        return result

    validated_normalized_items = [
        NormalizedRequestItem.model_validate(item)
        for item in (normalized_items or [])
    ]
    validated_unsupported_items = [
        UnsupportedRequestItem.model_validate(item)
        for item in (unsupported_items or [])
    ]
    validated_ambiguous_items = [
        AmbiguousRequestItem.model_validate(item)
        for item in (ambiguous_items or [])
    ]

    for item in validated_normalized_items:
        if not item.supported:
            raise ValueError(
                "Items passed in normalized_items must be marked as supported."
            )
        if not item.normalized_name:
            raise ValueError(
                "Each supported normalized item must include a normalized_name."
            )
        if item.normalized_name not in CATALOG_BY_NAME:
            raise ValueError(
                f"Unsupported catalog item '{item.normalized_name}' was placed in normalized_items."
            )
        expected_unit_price = float(CATALOG_BY_NAME[item.normalized_name]["unit_price"])
        if abs(float(item.unit_price) - expected_unit_price) > 1e-9:
            raise ValueError(
                "unit_price for a supported normalized item must match the catalog price."
            )

    result = NormalizationResult(
        normalized_items=validated_normalized_items,
        unsupported_items=validated_unsupported_items,
        ambiguous_items=validated_ambiguous_items,
    ).model_dump()
    update_workflow_context(
        normalized_items=result["normalized_items"],
        unsupported_items=result["unsupported_items"],
        ambiguous_items=result["ambiguous_items"],
        normalization_result=result,
    )
    return result


@tool
def assess_inventory_tool(
    request_date: str,
    delivery_deadline: Optional[str] = None,
    items: Optional[List[NormalizedRequestItem]] = None,
) -> InventoryResult:
    """
    Assess inventory availability for normalized request items.

    Args:
        items: Supported normalized request items. When omitted, the tool uses
            normalized items stored in the current workflow context.
        request_date: Request date in YYYY-MM-DD format.
        delivery_deadline: Requested delivery deadline in YYYY-MM-DD format, if known.

    Returns:
        Structured inventory assessment result.
    """
    assessment_items: List[InventoryAssessmentItem] = []
    overall_shortage = False
    delivery_feasible = True

    source_items = items
    if not source_items:
        source_items = get_workflow_context("normalized_items", [])

    if not source_items:
        result = InventoryResult(
            items=[],
            delivery_feasible=False,
            overall_shortage=False,
        ).model_dump()
        update_workflow_context(inventory_result=result)
        return result

    for raw_item in source_items:
        item = NormalizedRequestItem.model_validate(raw_item)
        item_name = item.normalized_name
        if not item_name or item_name not in CATALOG_BY_NAME:
            raise ValueError(
                "assess_inventory_tool requires each item to include a supported normalized_name."
            )
        requested = int(item.normalized_quantity)

        stock_df = get_stock_level(item_name, request_date)
        available = 0
        if not stock_df.empty:
            available = int(stock_df["current_stock"].iloc[0])

        shortage = max(0, requested - available)
        needs_reorder = shortage > 0
        estimated_delivery = None
        item_feasible = True

        if needs_reorder:
            overall_shortage = True
            estimated_delivery = get_supplier_delivery_date(request_date, shortage)

            if delivery_deadline and estimated_delivery > delivery_deadline:
                item_feasible = False
                delivery_feasible = False

        assessment = InventoryAssessmentItem(
            item_name=item_name,
            requested=requested,
            available=available,
            shortage=shortage,
            needs_reorder=needs_reorder,
            estimated_delivery=estimated_delivery,
            feasible=item_feasible,
        )
        assessment_items.append(assessment)

    inventory_result = InventoryResult(
        items=assessment_items,
        delivery_feasible=delivery_feasible if assessment_items else None,
        overall_shortage=overall_shortage,
    )

    result = inventory_result.model_dump()
    update_workflow_context(inventory_result=result)
    return result

@tool
def retrieve_similar_quotes_tool(
    normalized_items: List[NormalizedRequestItem],
    request_profile: RequestProfile,
    limit: int = 5,
) -> List[HistoricalQuoteRecord]:
    """
    Retrieve similar historical quotes using normalized item names plus request metadata.

    Args:
        normalized_items: Supported normalized request items.
        request_profile: Structured request profile metadata.
        limit: Maximum number of quote records to return.

    Returns:
        Filtered list of similar historical quote records.
    """
    search_terms: List[str] = []
    validated_profile = RequestProfile.model_validate(request_profile)

    for raw_item in normalized_items:
        item = NormalizedRequestItem.model_validate(raw_item)
        normalized_name = item.normalized_name
        if normalized_name:
            search_terms.append(normalized_name)

    for key in ["job_type", "order_size", "event_type"]:
        value = getattr(validated_profile, key)
        if value and value != "unknown":
            search_terms.append(value)

    # Deduplicate while preserving order
    deduped_terms = list(dict.fromkeys(search_terms))

    if not deduped_terms:
        return []

    raw_matches = search_quote_history(deduped_terms, limit=limit * 2)

    filtered_matches: List[Dict[str, Any]] = []
    for match in raw_matches:
        total_amount = match.get("total_amount")
        try:
            total_value = float(total_amount)
        except (TypeError, ValueError):
            continue

        if total_value <= 0:
            continue

        filtered_matches.append(match)

        if len(filtered_matches) >= limit:
            break

    return [
        HistoricalQuoteRecord.model_validate(match).model_dump()
        for match in filtered_matches
    ]


@tool
def generate_quote_tool(
    normalized_items: List[NormalizedRequestItem],
    similar_quotes: List[HistoricalQuoteRecord],
    request_profile: RequestProfile,
) -> QuoteResult:
    """
    Generate a structured quote result using catalog prices as the pricing truth
    and historical quotes as contextual support.

    Args:
        normalized_items: Supported normalized request items.
        similar_quotes: Retrieved historical quote records.
        request_profile: Structured request profile metadata.

    Returns:
        Structured quote result.
    """
    base_total = 0.0
    pricing_notes: List[str] = []
    validated_profile = RequestProfile.model_validate(request_profile)
    validated_quotes = [
        HistoricalQuoteRecord.model_validate(quote)
        for quote in similar_quotes
    ]

    for raw_item in normalized_items:
        item = NormalizedRequestItem.model_validate(raw_item)
        quantity = int(item.normalized_quantity)
        unit_price = float(item.unit_price)
        base_total += quantity * unit_price

    order_size = validated_profile.order_size

    if order_size == "large":
        discount_rate = 0.15
        pricing_notes.append("Applied large-order discount.")
    elif order_size == "medium":
        discount_rate = 0.10
        pricing_notes.append("Applied medium-order discount.")
    elif order_size == "small":
        discount_rate = 0.05
        pricing_notes.append("Applied small-order discount.")
    else:
        discount_rate = 0.05 if base_total >= 100 else 0.0
        if discount_rate > 0:
            pricing_notes.append("Applied fallback bulk discount based on quote size.")

    discount_amount = round(base_total * discount_rate, 2)
    final_total = round(base_total - discount_amount, 2)

    if validated_quotes:
        pricing_notes.append(f"Used {len(validated_quotes)} similar historical quote(s) as context.")
    else:
        pricing_notes.append("No reliable historical quote matches were used.")

    explanation = (
        f"Base total calculated from catalog prices is ${base_total:.2f}. "
        f"A discount of {discount_rate * 100:.0f}% was applied, producing a final quote of ${final_total:.2f}."
    )

    quote_result = QuoteResult(
        base_total=round(base_total, 2),
        discount_rate=discount_rate,
        discount_amount=discount_amount,
        final_total=final_total,
        similar_quotes_used=len(validated_quotes),
        pricing_notes=pricing_notes,
        explanation=explanation,
    )

    return quote_result.model_dump()


@tool
def finalize_decision_tool(
    normalized_items: List[NormalizedRequestItem],
    unsupported_items: Optional[List[UnsupportedRequestItem]] = None,
    ambiguous_items: Optional[List[AmbiguousRequestItem]] = None,
    inventory_result: Optional[InventoryResult] = None,
    quote_result: Optional[QuoteResult] = None,
) -> FinalDecisionResult:
    """
    Produce the final business decision for the request based on normalization,
    inventory feasibility, and quote context.

    Args:
        normalized_items: Supported normalized request items.
        unsupported_items: Items that could not be mapped to the supported catalog.
        ambiguous_items: Items that could not be safely resolved.
        inventory_result: Structured inventory assessment result.
        quote_result: Structured quote result.

    Returns:
        Final decision package.
    """
    validated_normalized_items = [
        NormalizedRequestItem.model_validate(item)
        for item in normalized_items
    ]
    validated_unsupported_items = [
        UnsupportedRequestItem.model_validate(item)
        for item in (unsupported_items or [])
    ]
    validated_ambiguous_items = [
        AmbiguousRequestItem.model_validate(item)
        for item in (ambiguous_items or [])
    ]
    validated_inventory_result = InventoryResult.model_validate(inventory_result or {})
    validated_quote_result = QuoteResult.model_validate(quote_result or {})

    notes: List[str] = []

    if not validated_normalized_items:
        notes.append("No supported items were available for quoting or fulfillment.")
        return FinalDecisionResult(
            decision="declined",
            delivery_feasible=False,
            quote_total=0.0,
            notes=notes,
        ).model_dump()

    inventory_items = [item.model_dump() for item in validated_inventory_result.items]
    inventory_by_name = {
        item["item_name"]: item for item in inventory_items
    }

    feasible_items = [item for item in inventory_items if item.get("feasible") is True]
    infeasible_items = [item for item in inventory_items if item.get("feasible") is False]

    if validated_unsupported_items:
        notes.append(f"{len(validated_unsupported_items)} item(s) were unsupported.")
    if validated_ambiguous_items:
        notes.append(f"{len(validated_ambiguous_items)} item(s) were ambiguous.")
    if infeasible_items:
        notes.append(f"{len(infeasible_items)} supported item(s) miss the requested deadline.")

    if inventory_items and len(feasible_items) == len(inventory_items) and not validated_unsupported_items and not validated_ambiguous_items:
        decision = "approved_full"
    elif feasible_items:
        decision = "approved_partial"
    elif inventory_items and infeasible_items:
        decision = "delayed"
    else:
        decision = "declined"

    delivery_feasible = validated_inventory_result.delivery_feasible

    full_base_total = sum(
        int(item.normalized_quantity) * float(item.unit_price)
        for item in validated_normalized_items
    )

    full_quote_total = float(validated_quote_result.final_total)
    effective_discount_ratio = 1.0
    if full_base_total > 0 and full_quote_total > 0:
        effective_discount_ratio = min(max(full_quote_total / full_base_total, 0.0), 1.0)

    approved_sales_items = []
    for item in validated_normalized_items:
        item_name = item.normalized_name
        inventory_item = inventory_by_name.get(item_name)
        if not inventory_item:
            continue
        if inventory_item.get("feasible", False):
            approved_sales_items.append(item)

    approved_base_total = sum(
        int(item.normalized_quantity) * float(item.unit_price)
        for item in approved_sales_items
    )

    if decision in {"approved_full", "approved_partial"}:
        quote_total = round(approved_base_total * effective_discount_ratio, 2)
    else:
        quote_total = 0.0

    return FinalDecisionResult(
        decision=decision,
        delivery_feasible=delivery_feasible,
        quote_total=quote_total,
        notes=notes,
    ).model_dump()

@tool
def write_transactions_tool(
    normalized_items: List[NormalizedRequestItem],
    inventory_result: InventoryResult,
    reorder_plan: Optional[List[ReorderPlanItem]] = None,
    decision: str = "declined",
    request_date: Optional[str] = None,
    quote_total: float = 0.0,
) -> TransactionWriteResult:
    """
    Write approved sales transactions and approved reorder transactions.

    Args:
        normalized_items: Supported normalized request items.
        inventory_result: Structured inventory assessment result.
        reorder_plan: Structured reorder plan.
        decision: Final decision string.
        request_date: Request date in YYYY-MM-DD format.
        quote_total: Final quoted amount for the approved portion of the request.

    Returns:
        Transaction write summary.
    """
    validated_normalized_items = [
        NormalizedRequestItem.model_validate(item)
        for item in normalized_items
    ]
    validated_inventory_result = InventoryResult.model_validate(inventory_result)
    validated_reorder_plan = [
        ReorderPlanItem.model_validate(item)
        for item in (reorder_plan or [])
    ]
    sales_written = 0
    stock_orders_written = 0

    if decision not in {"approved_full", "approved_partial"}:
        return TransactionWriteResult(
            sales_written=0,
            stock_orders_written=0,
            message="No transactions written because the request was not approved.",
        ).model_dump()

    fallback_date = request_date or datetime.now().strftime("%Y-%m-%d")

    # Build lookup for approved reorder timing
    reorder_by_name = {}
    for reorder_item in validated_reorder_plan:
        if not reorder_item.approved:
            continue
        reorder_by_name[reorder_item.item_name] = reorder_item

    # Write approved reorder transactions using the supplier delivery date
    for item_name, reorder_item in reorder_by_name.items():
        quantity_to_order = int(reorder_item.quantity_to_order)
        reorder_date = reorder_item.estimated_delivery or fallback_date

        matching_catalog = next(
            (item for item in paper_supplies if item["item_name"] == item_name),
            None
        )
        if matching_catalog is None:
            continue

        total_cost = round(quantity_to_order * float(matching_catalog["unit_price"]), 2)

        create_transaction(
            item_name=item_name,
            transaction_type="stock_orders",
            quantity=quantity_to_order,
            price=total_cost,
            date=reorder_date,
        )
        stock_orders_written += 1

    inventory_by_name = {
        item.item_name: item.model_dump() for item in validated_inventory_result.items
    }

    # Only feasible items are sold
    approved_sales_items: List[NormalizedRequestItem] = []
    for item in validated_normalized_items:
        item_name = item.normalized_name
        inventory_item = inventory_by_name.get(item_name)
        if not inventory_item:
            continue
        if not inventory_item.get("feasible", False):
            continue
        approved_sales_items.append(item)

    approved_base_total = sum(
        int(item.normalized_quantity) * float(item.unit_price)
        for item in approved_sales_items
    )

    effective_discount_ratio = 0.0
    if approved_base_total > 0:
        effective_discount_ratio = min(max(float(quote_total) / approved_base_total, 0.0), 1.0)

    for item in approved_sales_items:
        item_name = item.normalized_name
        requested_quantity = int(item.normalized_quantity)

        matching_catalog = next(
            (catalog_item for catalog_item in paper_supplies if catalog_item["item_name"] == item_name),
            None
        )
        if matching_catalog is None:
            continue

        inventory_item = inventory_by_name.get(item_name, {})
        sale_date = fallback_date

        if inventory_item.get("needs_reorder", False):
            reorder_item = reorder_by_name.get(item_name)
            if reorder_item and reorder_item.estimated_delivery:
                sale_date = max(fallback_date, reorder_item.estimated_delivery)

        base_price = requested_quantity * float(matching_catalog["unit_price"])
        discounted_price = round(base_price * effective_discount_ratio, 2)

        create_transaction(
            item_name=item_name,
            transaction_type="sales",
            quantity=requested_quantity,
            price=discounted_price,
            date=sale_date,
        )
        sales_written += 1

    return TransactionWriteResult(
        sales_written=sales_written,
        stock_orders_written=stock_orders_written,
        message="Transactions written successfully.",
    ).model_dump()




@tool
def log_request_memory_tool(
    raw_request: str,
    request_date: Optional[str],
    delivery_deadline: Optional[str],
    request_profile: RequestProfile,
    normalized_items: List[NormalizedRequestItem],
    unsupported_items: Optional[List[UnsupportedRequestItem]] = None,
    decision: str = "declined",
    quote_total: float = 0.0,
    delivery_feasible: Optional[bool] = None,
    notes: Optional[List[str]] = None,
) -> RequestMemoryLogResult:
    """
    Persist the final request outcome into request_memory.

    Args:
        raw_request: Original request text.
        request_date: Request date in YYYY-MM-DD format, if known.
        delivery_deadline: Delivery deadline in YYYY-MM-DD format, if known.
        request_profile: Structured request profile metadata.
        normalized_items: Supported normalized items.
        unsupported_items: Unsupported item records.
        decision: Final business decision.
        quote_total: Final quoted amount.
        delivery_feasible: Whether fulfillment by deadline was feasible.
        notes: Final decision notes.

    Returns:
        Summary of the memory logging action.
    """
    validated_profile = RequestProfile.model_validate(request_profile)
    validated_normalized_items = [
        NormalizedRequestItem.model_validate(item)
        for item in normalized_items
    ]
    validated_unsupported_items = [
        UnsupportedRequestItem.model_validate(item)
        for item in (unsupported_items or [])
    ]
    notes = notes or []

    row = {
        "request_text": raw_request,
        "request_date": request_date,
        "delivery_deadline": delivery_deadline,
        "job_type": validated_profile.job_type,
        "order_size": validated_profile.order_size,
        "event_type": validated_profile.event_type,
        "mood": validated_profile.mood,
        "normalized_items": json.dumps([item.model_dump() for item in validated_normalized_items]),
        "unsupported_items": json.dumps([item.model_dump() for item in validated_unsupported_items]),
        "decision": decision,
        "quote_total": float(quote_total),
        "delivery_feasible": delivery_feasible,
        "notes": " | ".join(notes),
        "timestamp": datetime.now().isoformat(),
    }

    pd.DataFrame([row]).to_sql("request_memory", db_engine, if_exists="append", index=False)

    return RequestMemoryLogResult(
        logged=True,
        decision=decision,
        quote_total=float(quote_total),
        message="Request outcome logged to persistent memory.",
    ).model_dump()


@tool
def build_reorder_plan_tool(inventory_result: InventoryResult) -> List[ReorderPlanItem]:
    """
    Build a structured reorder plan from an inventory assessment result.

    Args:
        inventory_result: Output from `assess_inventory_tool`.

    Returns:
        List of reorder plan items.
    """
    validated_inventory_result = InventoryResult.model_validate(inventory_result)
    reorder_plan: List[Dict[str, Any]] = []

    for assessment in validated_inventory_result.items:
        shortage = int(assessment.shortage)
        if shortage <= 0:
            continue

        reorder_item = ReorderPlanItem(
            item_name=assessment.item_name,
            quantity_to_order=shortage,
            estimated_delivery=assessment.estimated_delivery,
            approved=False,
        )
        reorder_plan.append(reorder_item.model_dump())

    return reorder_plan

# Set up and load your env parameters and instantiate your model.
dotenv.load_dotenv(dotenv_path='../.env')
openai_api_key = os.getenv('UDACITY_OPENAI_API_KEY')

model = OpenAIServerModel(
    model_id='gpt-4o-mini',
    api_base='https://openai.vocareum.com/v1',
    api_key=openai_api_key,
)


"""Set up tools for your agents to use, these should be methods that combine the database functions above
 and apply criteria to them to ensure that the flow of the system is correct."""

class InventoryRetrievalAgent(ToolCallingAgent):
    """
    Agent responsible for inventory assessment and reorder planning.
    """

    def __init__(self, model_to_use: OpenAIServerModel):
        super().__init__(
            tools=[
                assess_inventory_tool,
                build_reorder_plan_tool,
            ],
            model=model_to_use,
            name="inventory_retrieval_agent",
            description=(
                "Checks inventory feasibility for normalized catalog items and builds "
                "reorder plans when shortages exist. "
                "Its responsibilities are: "
                "1. assess current stock using the provided inventory tool; "
                "2. determine shortages and delivery feasibility; "
                "3. generate a structured reorder plan. "
                "It must stay within inventory and replenishment responsibilities only."
            ),
        )


# quoting agent
class QuoteRetrievalAgent(ToolCallingAgent):
    """
    Agent responsible for retrieving similar historical quotes and generating
    a structured quote result.
    """

    def __init__(self, model_to_use: OpenAIServerModel):
        super().__init__(
            tools=[
                retrieve_similar_quotes_tool,
                generate_quote_tool,
            ],
            model=model_to_use,
            name="quote_retrieval_agent",
            description=(
                "Retrieves relevant historical quote context and generates a structured quote. "
                "Its responsibilities are: "
                "1. retrieve similar historical quote records using normalized items and request metadata; "
                "2. generate a quote using catalog prices as the pricing truth and historical quotes as support. "
                "It must not make final fulfillment decisions or write transactions."
            ),
        )


# ordering agent
class RequestAnalysisAgent(ToolCallingAgent):
    """
    Agent responsible for analyzing the incoming request and converting it into
    structured request metadata, parsed items, and normalized items.
    """

    def __init__(self, model_to_use: OpenAIServerModel):
        super().__init__(
            tools=[
                analyze_request_metadata_tool,
                parse_request_items_tool,
                normalize_request_items_tool,
            ],
            model=model_to_use,
            name="request_analysis_agent",
            description=(
                "Analyzes customer requests for the paper company. "
                "Its responsibilities are: "
                "1. infer request metadata such as intent, urgency, request date, "
                "delivery deadline, job type, order size, event type, and mood; "
                "2. extract structured item lines from the request; "
                "3. normalize extracted items into supported catalog items, and "
                "separate unsupported or ambiguous items. "
                "It must use the provided tools to submit structured outputs."
            ),
        )

class SynthesisFulfillmentAgent(ToolCallingAgent):
    """
    Agent responsible for turning analyzed, inventoried, and quoted request data
    into a final business outcome and persisting the approved result.
    """

    def __init__(self, model_to_use: OpenAIServerModel):
        super().__init__(
            tools=[
                finalize_decision_tool,
                write_transactions_tool,
                log_request_memory_tool,
            ],
            model=model_to_use,
            name="synthesis_fulfillment_agent",
            description=(
                "Synthesizes normalized request data, inventory results, and quote results "
                "into the final business decision. "
                "Its responsibilities are: "
                "1. determine whether the request is approved in full, approved partially, delayed, or declined; "
                "2. write approved transactions; "
                "3. log the final request outcome into persistent memory. "
                "It must not perform request parsing or quote retrieval."
            ),
        )

class OrchestratorAgent:
    """
    Central workflow controller for the paper company multi-agent system.
    It coordinates the specialized agents but is not itself a ToolCallingAgent.
    """

    def __init__(self, model_to_use: OpenAIServerModel):
        self.model = model_to_use
        self.request_analysis_agent = RequestAnalysisAgent(model_to_use)
        self.inventory_retrieval_agent = InventoryRetrievalAgent(model_to_use)
        self.quote_retrieval_agent = QuoteRetrievalAgent(model_to_use)
        self.synthesis_fulfillment_agent = SynthesisFulfillmentAgent(model_to_use)

    def _run_agent_with_mode(
        self,
        agent: ToolCallingAgent,
        prompt: str,
        display_mode: str = "quiet",
    ) -> Any:
        """
        Run a specialist agent while respecting the selected terminal mode.

        Args:
            agent: Specialist agent to execute.
            prompt: Prompt to send to the specialist agent.
            display_mode: One of `debug`, `showcase`, or `quiet`.

        Returns:
            Whatever the underlying `agent.run` call returns.
        """
        normalized_mode = normalize_display_mode(display_mode)
        if normalized_mode == "debug":
            return agent.run(prompt)

        stdout_buffer = io.StringIO()
        stderr_buffer = io.StringIO()
        with contextlib.redirect_stdout(stdout_buffer), contextlib.redirect_stderr(stderr_buffer):
            return agent.run(prompt)

    def _build_request_analysis_summary(self, request_state: Dict[str, Any]) -> str:
        """
        Summarize the request-analysis stage for the showcase timeline.

        Args:
            request_state: Current request state after analysis.

        Returns:
            Customer-facing analysis summary.
        """
        supported_items = request_state.get("normalized_items", [])
        unsupported_items = request_state.get("unsupported_items", [])
        ambiguous_items = request_state.get("ambiguous_items", [])
        if supported_items:
            item_list = ", ".join(
                item["normalized_name"]
                for item in supported_items[:3]
                if item.get("normalized_name")
            )
            return (
                f"Catalog mapped {len(supported_items)} supported item(s)"
                f" with {len(unsupported_items)} unsupported and"
                f" {len(ambiguous_items)} ambiguous. Top matches: {item_list}."
            )

        return (
            f"No supported items found."
            f" Unsupported: {len(unsupported_items)} | Ambiguous: {len(ambiguous_items)}."
        )

    def _build_inventory_summary(self, request_state: Dict[str, Any]) -> str:
        """
        Summarize the inventory stage for the showcase timeline.

        Args:
            request_state: Current request state after inventory assessment.

        Returns:
            Customer-facing inventory summary.
        """
        inventory_result = request_state.get("inventory_result", {})
        shortage_items = [
            item for item in inventory_result.get("items", [])
            if int(item.get("shortage", 0)) > 0
        ]
        reorder_count = len(request_state.get("reorder_plan", []))
        delivery_feasible = inventory_result.get("delivery_feasible")

        if shortage_items:
            return (
                f"Detected {len(shortage_items)} shortage item(s)."
                f" Reorder actions prepared: {reorder_count}."
                f" Delivery feasible: {delivery_feasible}."
            )

        return (
            f"All supported items are covered by stock."
            f" Delivery feasible: {delivery_feasible}."
        )

    def _build_quote_summary(self, request_state: Dict[str, Any]) -> str:
        """
        Summarize the quote stage for the showcase timeline.

        Args:
            request_state: Current request state after quote generation.

        Returns:
            Customer-facing quote summary.
        """
        quote_result = request_state.get("quote_result", {})
        return (
            f"Quote built from base {format_currency(quote_result.get('base_total', 0.0))}"
            f" to final {format_currency(quote_result.get('final_total', 0.0))}."
            f" Historical references used: {quote_result.get('similar_quotes_used', 0)}."
        )

    def _build_synthesis_summary(self, request_state: Dict[str, Any]) -> str:
        """
        Summarize the synthesis stage for the showcase timeline.

        Args:
            request_state: Current request state after synthesis.

        Returns:
            Customer-facing final summary.
        """
        return (
            f"Decision {request_state.get('final_decision', 'pending')}"
            f" locked at {format_currency(request_state.get('quote_result', {}).get('final_total', 0.0))}."
        )


    def _extract_tool_result(self, agent: ToolCallingAgent, tool_name: str) -> Any:
        """
        Extract the most recent structured result produced by a specific tool call
        from an agent's memory.

        This is an internal orchestration helper, not agent business logic.
        """
        def parse_step_output_entries(raw_output: Any) -> List[Any]:
            """Best-effort parse of one or more tool outputs stored on a step."""
            if raw_output is None:
                return []
            if hasattr(raw_output, "model_dump"):
                return [raw_output.model_dump()]
            if isinstance(raw_output, (dict, list)):
                return [raw_output]
            if not isinstance(raw_output, str):
                return [raw_output]

            parsed_entries: List[Any] = []
            for line in raw_output.splitlines():
                candidate = line.strip()
                if not candidate:
                    continue
                try:
                    parsed_entries.append(ast.literal_eval(candidate))
                except (ValueError, SyntaxError):
                    parsed_entries.append(candidate)
            return parsed_entries

        for step in reversed(agent.memory.steps):
            if not hasattr(step, "tool_calls") or not step.tool_calls:
                continue

            matched_call = None
            matched_index = None
            for index, tool_call in enumerate(step.tool_calls):
                if getattr(tool_call, "name", None) == tool_name:
                    matched_call = tool_call
                    matched_index = index
                    break

            if matched_call is None or matched_index is None:
                continue

            if hasattr(step, "action_output") and step.action_output is not None:
                action_entries = parse_step_output_entries(step.action_output)
                if len(action_entries) == len(step.tool_calls):
                    selected_entry = action_entries[matched_index]
                    if not isinstance(selected_entry, str) or "required" not in selected_entry.lower():
                        return selected_entry

            if hasattr(step, "observations") and step.observations is not None:
                observation_entries = parse_step_output_entries(step.observations)
                if len(observation_entries) == len(step.tool_calls):
                    selected_entry = observation_entries[matched_index]
                    if not isinstance(selected_entry, str) or "required" not in selected_entry.lower():
                        return selected_entry

            if hasattr(matched_call, "arguments") and matched_call.arguments is not None:
                return matched_call.arguments

        raise ValueError(f"Could not extract result for tool '{tool_name}' from agent memory.")

    def _validate_request_analysis_outputs(
        self,
        metadata_result: Dict[str, Any],
        parsed_items_result: List[Dict[str, Any]],
        normalization_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Strictly validate RequestAnalysisAgent outputs before they enter shared state.
        Raises WorkflowValidationError on any schema or structure violation.
        """
        allowed_intents = {"inventory", "quote", "fulfillment", "mixed", "unknown"}
        allowed_urgency = {"normal", "urgent"}

        try:
            metadata = RequestMetadataResult.model_validate(metadata_result)
            intent = metadata.intent
            urgency = metadata.urgency

            if intent not in allowed_intents:
                raise WorkflowValidationError(
                    f"Invalid intent returned by RequestAnalysisAgent: {intent}"
                )

            if urgency not in allowed_urgency:
                raise WorkflowValidationError(
                    f"Invalid urgency returned by RequestAnalysisAgent: {urgency}"
                )

            parsed_items = [
                ParsedRequestItem.model_validate(item)
                for item in parsed_items_result
            ]

            normalization = NormalizationResult.model_validate(normalization_result)
            if parsed_items and not (
                normalization.normalized_items
                or normalization.unsupported_items
                or normalization.ambiguous_items
            ):
                raise WorkflowValidationError(
                    "RequestAnalysisAgent returned an empty normalization payload."
                )

            return {
                "intent": intent,
                "urgency": urgency,
                "request_date": metadata.request_date,
                "delivery_deadline": metadata.delivery_deadline,
                "request_profile": metadata.request_profile.model_dump(),
                "parsed_items": [item.model_dump() for item in parsed_items],
                "normalized_items": [
                    item.model_dump() for item in normalization.normalized_items
                ],
                "unsupported_items": [
                    item.model_dump() for item in normalization.unsupported_items
                ],
                "ambiguous_items": [
                    item.model_dump() for item in normalization.ambiguous_items
                ],
            }

        except ValidationError as e:
            raise WorkflowValidationError(
                f"RequestAnalysisAgent schema validation failed: {e}"
            ) from e
        except (TypeError, KeyError, ValueError) as e:
            if isinstance(e, WorkflowValidationError):
                raise
            raise WorkflowValidationError(
                f"RequestAnalysisAgent returned invalid structured output: {e}"
            ) from e

    def _extract_request_date_fallback(self, raw_request: str) -> Optional[str]:
        """
        Extract a request date from the raw request text when the agent omitted it.

        Args:
            raw_request: Original customer request text.

        Returns:
            Request date in ISO format when found, otherwise None.
        """
        match = re.search(r"Date of request:\s*(\d{4}-\d{2}-\d{2})", raw_request)
        if match:
            return match.group(1)
        return None

    def _extract_delivery_deadline_fallback(self, raw_request: str) -> Optional[str]:
        """
        Extract a delivery deadline from the raw request text when the agent omitted it.

        Args:
            raw_request: Original customer request text.

        Returns:
            Delivery deadline in ISO format when found, otherwise None.
        """
        deadline_match = re.search(
            r"(?i)\b(?:deliver(?:ed|y)?|delivery)\b[^.]*?\bby\s+"
            r"([A-Za-z]+ \d{1,2}, \d{4})",
            raw_request,
        )
        if not deadline_match:
            return None

        try:
            return datetime.strptime(
                deadline_match.group(1),
                "%B %d, %Y",
            ).strftime("%Y-%m-%d")
        except ValueError:
            return None

    def _build_request_analysis_fallback(
        self,
        raw_request: str,
        metadata_result: Optional[Dict[str, Any]],
        parsed_items_result: Optional[List[Dict[str, Any]]],
        normalization_result: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        Recover request analysis state when the specialist agent omits a required tool payload.

        The primary path is LLM-driven. This fallback only fills gaps when
        the agent produced partial structured output but failed to complete the
        full request-analysis tool chain.

        Args:
            raw_request: Original customer request text.
            metadata_result: Best metadata payload recovered from agent memory.
            parsed_items_result: Best parsed-items payload recovered from agent memory.
            normalization_result: Best normalization payload recovered from agent memory.

        Returns:
            A validated request-analysis payload ready for shared workflow state.
        """
        try:
            metadata = RequestMetadataResult.model_validate(metadata_result or {})
        except ValidationError:
            metadata = RequestMetadataResult(
                raw_request=raw_request,
                intent="unknown",
                urgency="normal",
                request_date=self._extract_request_date_fallback(raw_request),
                delivery_deadline=self._extract_delivery_deadline_fallback(raw_request),
                request_profile=RequestProfile(),
            )

        try:
            parsed_items = [
                ParsedRequestItem.model_validate(item)
                for item in (parsed_items_result or [])
            ]
        except ValidationError:
            parsed_items = []

        if not parsed_items:
            parsed_items = parse_request_items_from_text(raw_request)

        try:
            normalization = NormalizationResult.model_validate(normalization_result or {})
            if not (
                normalization.normalized_items
                or normalization.unsupported_items
                or normalization.ambiguous_items
            ):
                raise ValueError("Normalization payload was empty.")
        except (ValidationError, ValueError):
            normalization = normalize_request_items(parsed_items)

        return self._validate_request_analysis_outputs(
            metadata_result={
                "raw_request": metadata.raw_request,
                "intent": metadata.intent,
                "urgency": metadata.urgency,
                "request_date": metadata.request_date,
                "delivery_deadline": metadata.delivery_deadline,
                "request_profile": metadata.request_profile.model_dump(),
            },
            parsed_items_result=[item.model_dump() for item in parsed_items],
            normalization_result=normalization.model_dump(),
        )

    def _run_request_analysis_stage(
        self,
        raw_request: str,
        request_state: Dict[str, Any],
        display_mode: str = "quiet",
    ) -> Dict[str, Any]:
        """
        Run the RequestAnalysisAgent stage with strict tool-order and output-shape expectations.
        """
        self.request_analysis_agent.memory.steps = []
        reset_workflow_context(
            request_id=request_state.get("request_id"),
            raw_request=raw_request,
            parsed_items=request_state.get("parsed_items", []),
            normalized_items=request_state.get("normalized_items", []),
            unsupported_items=request_state.get("unsupported_items", []),
            ambiguous_items=request_state.get("ambiguous_items", []),
        )
        request_analysis_contracts = render_pydantic_contracts(
            [
                RequestProfile,
                RequestMetadataResult,
                ParsedRequestItem,
                NormalizedRequestItem,
                UnsupportedRequestItem,
                AmbiguousRequestItem,
                NormalizationResult,
            ]
        )

        analysis_prompt = f"""
You are the RequestAnalysisAgent for a paper company workflow.

You must analyze exactly one customer request and submit structured outputs through tools.

Customer request:
\"\"\"{raw_request}\"\"\"

Use these exact Pydantic model schema dumps when constructing tool arguments:
```python
{request_analysis_contracts}
```

You must complete these three tasks in this exact order:

TASK 1: metadata
Call analyze_request_metadata_tool exactly once with:
- raw_request: the original request text
- intent: one of inventory, quote, fulfillment, mixed, unknown
- urgency: one of normal, urgent
- request_date: YYYY-MM-DD if explicitly known, otherwise null
- delivery_deadline: YYYY-MM-DD if explicitly known, otherwise null
- job_type: inferred best label or "unknown"
- order_size: inferred best label or "unknown"
- event_type: inferred best label or "unknown"
- mood: inferred best label or "unknown"

TASK 2: parsed items
Call parse_request_items_tool exactly once with a list of item dictionaries.
Each dictionary must contain:
- raw_name
- quantity
- unit

TASK 3: normalized items
Call normalize_request_items_tool exactly once with no arguments.
It will read the parsed items from workflow context, apply catalog similarity,
and return a NormalizationResult that matches the Pydantic schema dump above.
Do not manufacture normalized_items, unsupported_items, or ambiguous_items yourself.

Use only these exact supported catalog item names and prices:
{json.dumps([{"item_name": item["item_name"], "unit_price": item["unit_price"]} for item in paper_supplies], ensure_ascii=True)}

Normalization rules:
- If safely supported, put it in normalized_items.
- If not supported, put it in unsupported_items.
- If unclear between multiple supported options, put it in ambiguous_items.
- normalized_name must be copied verbatim from the supported catalog list above.
- Do not pluralize, paraphrase, or invent catalog item names.
- Do not invent catalog names.
- Do not omit requested items silently.
- The normalization tool already knows the parsed items from TASK 2, so the
  correct TASK 3 call is an empty argument object.

Important:
- You must call all three tools.
- You must call them in order.
- When a later tool needs prior results, rely on the workflow context only when
  the task instructions explicitly say so.
- Do not stop after one tool.
- Do not return prose instead of tool calls.
"""

        metadata_result: Optional[Dict[str, Any]] = None
        parsed_items_result: Optional[List[Dict[str, Any]]] = None
        normalization_result: Optional[Dict[str, Any]] = None

        try:
            _ = self._run_agent_with_mode(
                self.request_analysis_agent,
                analysis_prompt,
                display_mode=display_mode,
            )

            metadata_result = self._extract_tool_result(
                self.request_analysis_agent,
                "analyze_request_metadata_tool",
            )
            parsed_items_result = self._extract_tool_result(
                self.request_analysis_agent,
                "parse_request_items_tool",
            )
            normalization_result = self._extract_tool_result(
                self.request_analysis_agent,
                "normalize_request_items_tool",
            )

            validated_analysis = self._validate_request_analysis_outputs(
                metadata_result,
                parsed_items_result,
                normalization_result,
            )
        except Exception as e:
            request_state["errors"].append(
                f"RequestAnalysisAgent fallback used: {e}"
            )
            validated_analysis = self._build_request_analysis_fallback(
                raw_request=raw_request,
                metadata_result=metadata_result,
                parsed_items_result=parsed_items_result,
                normalization_result=normalization_result,
            )

        request_state["intent"] = validated_analysis["intent"]
        request_state["urgency"] = validated_analysis["urgency"]
        request_state["request_date"] = validated_analysis["request_date"]
        request_state["delivery_deadline"] = validated_analysis["delivery_deadline"]
        request_state["request_profile"] = validated_analysis["request_profile"]
        request_state["parsed_items"] = validated_analysis["parsed_items"]
        request_state["normalized_items"] = validated_analysis["normalized_items"]
        request_state["unsupported_items"] = validated_analysis["unsupported_items"]
        request_state["ambiguous_items"] = validated_analysis["ambiguous_items"]

        if not request_state["request_date"]:
            request_state["request_date"] = self._extract_request_date_fallback(raw_request)
        if not request_state["delivery_deadline"]:
            request_state["delivery_deadline"] = self._extract_delivery_deadline_fallback(raw_request)

        return request_state

    def _run_inventory_stage(
        self,
        request_state: Dict[str, Any],
        display_mode: str = "quiet",
    ) -> Dict[str, Any]:
        """
        Run the InventoryRetrievalAgent stage with strict tool-order and output validation.
        """
        if not request_state["normalized_items"]:
            request_state["inventory_result"] = InventoryResult(
                items=[],
                delivery_feasible=False,
                overall_shortage=False,
            ).model_dump()
            request_state["reorder_plan"] = []
            return request_state

        if not request_state["request_date"]:
            raise WorkflowValidationError(
                "Inventory stage requires request_date, but none was available."
            )

        reset_workflow_context(
            request_id=request_state.get("request_id"),
            raw_request=request_state.get("raw_request"),
            request_date=request_state["request_date"],
            delivery_deadline=request_state["delivery_deadline"],
            normalized_items=request_state["normalized_items"],
            unsupported_items=request_state.get("unsupported_items", []),
            ambiguous_items=request_state.get("ambiguous_items", []),
        )

        def run_inventory_tools_directly() -> Tuple[InventoryResult, List[ReorderPlanItem]]:
            """Run inventory computations directly as a resilient fallback."""
            inventory_result_raw = assess_inventory_tool.forward(
                items=request_state["normalized_items"],
                request_date=request_state["request_date"],
                delivery_deadline=request_state["delivery_deadline"],
            )
            reorder_plan_raw = build_reorder_plan_tool.forward(
                inventory_result=inventory_result_raw
            )
            inventory_result = InventoryResult.model_validate(inventory_result_raw)
            reorder_plan = [
                ReorderPlanItem.model_validate(item)
                for item in reorder_plan_raw
            ]
            return inventory_result, reorder_plan

        self.inventory_retrieval_agent.memory.steps = []
        inventory_contracts = render_pydantic_contracts(
            [
                NormalizedRequestItem,
                InventoryAssessmentItem,
                InventoryResult,
                ReorderPlanItem,
            ]
        )

        inventory_prompt = f"""
You are the InventoryRetrievalAgent for a paper company workflow.

Use the following normalized request items:
{json.dumps(request_state["normalized_items"], ensure_ascii=True)}

Request date: {request_state["request_date"]}
Delivery deadline: {request_state["delivery_deadline"]}

Use these exact Pydantic model schema dumps when constructing tool arguments:
```python
{inventory_contracts}
```

You must complete these tasks in this exact order:

TASK 1: inventory assessment
Call assess_inventory_tool exactly once with:
- request_date: {request_state["request_date"]}
- delivery_deadline: {request_state["delivery_deadline"]}
The tool will read the normalized request items from workflow context, so you
do not need to resend the items payload unless you intentionally want to.

TASK 2: reorder plan
Call build_reorder_plan_tool exactly once with the inventory result from TASK 1.

Important:
- Use both tools.
- Use them in order.
- Pass the full inventory result into build_reorder_plan_tool.
- Do not perform quote logic.
- Do not make final approval decisions.
"""

        try:
            _ = self._run_agent_with_mode(
                self.inventory_retrieval_agent,
                inventory_prompt,
                display_mode=display_mode,
            )

            inventory_result_raw = self._extract_tool_result(
                self.inventory_retrieval_agent,
                "assess_inventory_tool",
            )
            reorder_plan_raw = self._extract_tool_result(
                self.inventory_retrieval_agent,
                "build_reorder_plan_tool",
            )

            inventory_result = InventoryResult.model_validate(inventory_result_raw)
            reorder_plan = [
                ReorderPlanItem.model_validate(item)
                for item in reorder_plan_raw
            ]
            if request_state["normalized_items"] and not inventory_result.items:
                raise WorkflowValidationError(
                    "InventoryRetrievalAgent returned an empty inventory assessment."
                )
        except Exception as e:
            request_state["errors"].append(
                f"InventoryRetrievalAgent fallback used: {e}"
            )
            inventory_result, reorder_plan = run_inventory_tools_directly()

        request_state["inventory_result"] = inventory_result.model_dump()
        request_state["reorder_plan"] = [item.model_dump() for item in reorder_plan]

        return request_state

    def _run_quote_stage(
        self,
        request_state: Dict[str, Any],
        display_mode: str = "quiet",
    ) -> Dict[str, Any]:
        """
        Run the QuoteRetrievalAgent stage with strict tool-order and output validation.
        """
        if not request_state["normalized_items"]:
            request_state["quote_result"] = QuoteResult().model_dump()
            return request_state

        reset_workflow_context(
            request_id=request_state.get("request_id"),
            raw_request=request_state.get("raw_request"),
            request_profile=request_state["request_profile"],
            normalized_items=request_state["normalized_items"],
            unsupported_items=request_state.get("unsupported_items", []),
            ambiguous_items=request_state.get("ambiguous_items", []),
            inventory_result=request_state.get("inventory_result", {}),
        )

        def run_quote_tools_directly() -> QuoteResult:
            """Run quote computations directly as a resilient fallback."""
            similar_quotes_raw = retrieve_similar_quotes_tool.forward(
                normalized_items=request_state["normalized_items"],
                request_profile=request_state["request_profile"],
            )
            _ = [
                HistoricalQuoteRecord.model_validate(item)
                for item in similar_quotes_raw
            ]
            quote_result_raw = generate_quote_tool.forward(
                normalized_items=request_state["normalized_items"],
                similar_quotes=similar_quotes_raw,
                request_profile=request_state["request_profile"],
            )
            return QuoteResult.model_validate(quote_result_raw)

        self.quote_retrieval_agent.memory.steps = []
        quote_contracts = render_pydantic_contracts(
            [
                NormalizedRequestItem,
                RequestProfile,
                HistoricalQuoteRecord,
                QuoteResult,
            ]
        )

        quote_prompt = f"""
You are the QuoteRetrievalAgent for a paper company workflow.

Use the following normalized request items:
{json.dumps(request_state["normalized_items"], ensure_ascii=True)}

Request profile:
{json.dumps(request_state["request_profile"], ensure_ascii=True)}

Use these exact Pydantic model schema dumps when constructing tool arguments:
```python
{quote_contracts}
```

You must complete these tasks in this exact order:

TASK 1: retrieve similar quotes
Call retrieve_similar_quotes_tool exactly once with:
- normalized_items: the full normalized request items shown above
- request_profile: the full request profile shown above

TASK 2: generate quote
Call generate_quote_tool exactly once with:
- normalized_items: the full normalized request items shown above
- similar_quotes: the full output from TASK 1
- request_profile: the full request profile shown above

Important:
- Use both tools.
- Use them in order.
- Pass the full similar_quotes output into generate_quote_tool.
- Do not make inventory or fulfillment decisions.
"""

        try:
            _ = self._run_agent_with_mode(
                self.quote_retrieval_agent,
                quote_prompt,
                display_mode=display_mode,
            )

            _similar_quotes_raw = self._extract_tool_result(
                self.quote_retrieval_agent,
                "retrieve_similar_quotes_tool",
            )
            quote_result_raw = self._extract_tool_result(
                self.quote_retrieval_agent,
                "generate_quote_tool",
            )

            quote_result = QuoteResult.model_validate(quote_result_raw)
        except Exception as e:
            request_state["errors"].append(
                f"QuoteRetrievalAgent fallback used: {e}"
            )
            quote_result = run_quote_tools_directly()

        request_state["quote_result"] = quote_result.model_dump()

        return request_state

    def _run_synthesis_stage(
        self,
        request_state: Dict[str, Any],
        display_mode: str = "quiet",
    ) -> Dict[str, Any]:
        """
        Run the SynthesisFulfillmentAgent stage with strict tool-order and output validation.
        """
        self.synthesis_fulfillment_agent.memory.steps = []
        reset_workflow_context(
            request_id=request_state.get("request_id"),
            raw_request=request_state["raw_request"],
            request_date=request_state["request_date"],
            delivery_deadline=request_state["delivery_deadline"],
            request_profile=request_state["request_profile"],
            normalized_items=request_state["normalized_items"],
            unsupported_items=request_state["unsupported_items"],
            ambiguous_items=request_state["ambiguous_items"],
            inventory_result=request_state["inventory_result"],
            reorder_plan=request_state["reorder_plan"],
            quote_result=request_state["quote_result"],
        )

        # Pre-approve all reorder plan items so write_transactions_tool will process them
        for item in request_state["reorder_plan"]:
            item["approved"] = True

        def run_synthesis_tools_directly() -> FinalDecisionResult:
            """Run synthesis and persistence tools directly as a resilient fallback."""
            decision_result = finalize_decision_tool.forward(
                normalized_items=request_state["normalized_items"],
                unsupported_items=request_state["unsupported_items"],
                ambiguous_items=request_state["ambiguous_items"],
                inventory_result=request_state["inventory_result"],
                quote_result=request_state["quote_result"],
            )
            decision = FinalDecisionResult.model_validate(decision_result)
            transaction_result = write_transactions_tool.forward(
                normalized_items=request_state["normalized_items"],
                inventory_result=request_state["inventory_result"],
                reorder_plan=request_state["reorder_plan"],
                decision=decision.decision,
                request_date=request_state["request_date"],
                quote_total=decision.quote_total,
            )
            RequestMemoryLogResult.model_validate(
                log_request_memory_tool.forward(
                    raw_request=request_state["raw_request"],
                    request_date=request_state["request_date"],
                    delivery_deadline=request_state["delivery_deadline"],
                    request_profile=request_state["request_profile"],
                    normalized_items=request_state["normalized_items"],
                    unsupported_items=request_state["unsupported_items"],
                    decision=decision.decision,
                    quote_total=decision.quote_total,
                    delivery_feasible=decision.delivery_feasible,
                    notes=decision.notes,
                )
            )
            TransactionWriteResult.model_validate(transaction_result)
            return decision

        synthesis_contracts = render_pydantic_contracts(
            [
                NormalizedRequestItem,
                UnsupportedRequestItem,
                AmbiguousRequestItem,
                InventoryAssessmentItem,
                InventoryResult,
                ReorderPlanItem,
                QuoteResult,
                FinalDecisionResult,
                TransactionWriteResult,
                RequestMemoryLogResult,
            ]
        )

        synthesis_prompt = f"""
You are the SynthesisFulfillmentAgent for a paper company workflow.

Normalized items:
{json.dumps(request_state["normalized_items"], ensure_ascii=True)}

Unsupported items:
{json.dumps(request_state["unsupported_items"], ensure_ascii=True)}

Ambiguous items:
{json.dumps(request_state["ambiguous_items"], ensure_ascii=True)}

Inventory result:
{json.dumps(request_state["inventory_result"], ensure_ascii=True)}

Reorder plan:
{json.dumps(request_state["reorder_plan"], ensure_ascii=True)}

Quote result:
{json.dumps(request_state["quote_result"], ensure_ascii=True)}

Request date: {request_state["request_date"]}
Delivery deadline: {request_state["delivery_deadline"]}

Original request:
{request_state["raw_request"]}

Request profile:
{json.dumps(request_state["request_profile"], ensure_ascii=True)}

Use these exact Pydantic model schema dumps when constructing tool arguments:
```python
{synthesis_contracts}
```

You must complete these tasks in this exact order:

TASK 1: finalize decision
Call finalize_decision_tool exactly once with:
- normalized_items: the full normalized item list shown above
- unsupported_items: the full unsupported item list shown above
- ambiguous_items: the full ambiguous item list shown above
- inventory_result: the full inventory result shown above
- quote_result: the full quote result shown above

TASK 2: write transactions
Call write_transactions_tool exactly once with:
- normalized_items: the full normalized item list shown above
- inventory_result: the full inventory result shown above
- reorder_plan: the full reorder plan shown above
- decision: the decision returned by TASK 1
- request_date: {request_state["request_date"]}
- quote_total: the quote_total returned by TASK 1

TASK 3: log request memory
Call log_request_memory_tool exactly once with:
- raw_request: the original request shown above
- request_date: {request_state["request_date"]}
- delivery_deadline: {request_state["delivery_deadline"]}
- request_profile: the full request profile shown above
- normalized_items: the full normalized item list shown above
- unsupported_items: the full unsupported item list shown above
- decision: the decision returned by TASK 1
- quote_total: the quote_total returned by TASK 1
- delivery_feasible: the delivery_feasible value returned by TASK 1
- notes: the notes returned by TASK 1

Important:
- Use all three tools.
- Use them in order.
- Pass required fields explicitly into write_transactions_tool and log_request_memory_tool.
"""

        try:
            _ = self._run_agent_with_mode(
                self.synthesis_fulfillment_agent,
                synthesis_prompt,
                display_mode=display_mode,
            )

            decision_result = self._extract_tool_result(
                self.synthesis_fulfillment_agent,
                "finalize_decision_tool",
            )
            _txn_result = self._extract_tool_result(
                self.synthesis_fulfillment_agent,
                "write_transactions_tool",
            )
            _memory_result = self._extract_tool_result(
                self.synthesis_fulfillment_agent,
                "log_request_memory_tool",
            )
            decision = FinalDecisionResult.model_validate(decision_result)
        except Exception as e:
            request_state["errors"].append(
                f"SynthesisFulfillmentAgent fallback used: {e}"
            )
            decision = run_synthesis_tools_directly()

        request_state["final_decision"] = decision.decision
        request_state["quote_result"]["final_total"] = decision.quote_total
        request_state["inventory_result"]["delivery_feasible"] = decision.delivery_feasible
        request_state["final_notes"] = decision.notes

        return request_state

    def process_request(
        self,
        raw_request: str,
        request_id: Optional[str] = None,
        display_mode: str = "quiet",
        request_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Process a single customer request through the full agent pipeline.

        Args:
            raw_request: Original customer request text.
            request_id: Stable identifier for the request.
            display_mode: One of `showcase`, `debug`, or `quiet`.
            request_context: Optional customer-facing context for showcase mode.

        Returns:
            Final plain-text workflow response.
        """
        normalized_mode = normalize_display_mode(display_mode)
        request_state = make_request_state(raw_request, request_id)
        reset_workflow_context(
            request_id=request_id,
            raw_request=raw_request,
        )

        showcase = None
        if normalized_mode == "showcase":
            showcase = WorkflowShowcase(
                request_id=request_id or "ad-hoc",
                raw_request=raw_request,
                request_context=request_context,
            )
            showcase.open()
            showcase.update_state(request_state)

        try:
            # Stage 1: Request Analysis
            try:
                if showcase is not None:
                    showcase.start_stage(
                        "analysis",
                        "Parsing the request into metadata and catalog-ready items.",
                    )
                request_state = self._run_request_analysis_stage(
                    raw_request,
                    request_state,
                    display_mode=normalized_mode,
                )
                if showcase is not None:
                    showcase.complete_stage(
                        "analysis",
                        self._build_request_analysis_summary(request_state),
                        request_state=request_state,
                    )
            except Exception as e:
                if showcase is not None:
                    showcase.fail_stage("analysis", f"Request analysis failed: {e}")
                return f"[Error in request analysis] {e}"

            # Skip remaining stages if no supported items
            if not request_state["normalized_items"]:
                decline_notes = ["No supported items found in the request."]
                if showcase is not None:
                    showcase.skip_stage(
                        "inventory",
                        "Inventory check skipped because the request has no supported items.",
                    )
                    showcase.skip_stage(
                        "quote",
                        "Quote engine skipped because nothing supported can be priced.",
                    )
                    showcase.skip_stage(
                        "synthesis",
                        "Fulfillment stage skipped because the request was declined early.",
                    )
                    showcase.finish(
                        decision="declined",
                        quote_total=0.0,
                        notes=decline_notes,
                    )
                return build_decision_response(
                    decision="declined",
                    quote_total=0.0,
                    notes=decline_notes,
                )

            # Stage 2: Inventory
            try:
                if showcase is not None:
                    showcase.start_stage(
                        "inventory",
                        "Checking stock coverage and supplier lead times.",
                    )
                request_state = self._run_inventory_stage(
                    request_state,
                    display_mode=normalized_mode,
                )
                if showcase is not None:
                    showcase.complete_stage(
                        "inventory",
                        self._build_inventory_summary(request_state),
                        request_state=request_state,
                    )
            except Exception as e:
                if showcase is not None:
                    showcase.fail_stage("inventory", f"Inventory stage failed: {e}")
                return f"[Error in inventory stage] {e}"

            # Stage 3: Quote
            try:
                if showcase is not None:
                    showcase.start_stage(
                        "quote",
                        "Pricing the request against catalog truth and historical memory.",
                    )
                request_state = self._run_quote_stage(
                    request_state,
                    display_mode=normalized_mode,
                )
                if showcase is not None:
                    showcase.complete_stage(
                        "quote",
                        self._build_quote_summary(request_state),
                        request_state=request_state,
                    )
            except Exception as e:
                if showcase is not None:
                    showcase.fail_stage("quote", f"Quote stage failed: {e}")
                return f"[Error in quote stage] {e}"

            # Stage 4: Synthesis & Fulfillment
            try:
                if showcase is not None:
                    showcase.start_stage(
                        "synthesis",
                        "Locking the final decision and persistence actions.",
                    )
                request_state = self._run_synthesis_stage(
                    request_state,
                    display_mode=normalized_mode,
                )
                if showcase is not None:
                    showcase.complete_stage(
                        "synthesis",
                        self._build_synthesis_summary(request_state),
                        request_state=request_state,
                    )
            except Exception as e:
                if showcase is not None:
                    showcase.fail_stage("synthesis", f"Synthesis stage failed: {e}")
                return f"[Error in synthesis stage] {e}"

            decision = request_state.get("final_decision", "pending")
            quote_total = request_state.get("quote_result", {}).get("final_total", 0.0)
            notes = request_state.get("final_notes", [])
            if showcase is not None:
                showcase.finish(decision=decision, quote_total=quote_total, notes=notes)

            return build_decision_response(
                decision=decision,
                quote_total=quote_total,
                notes=notes,
            )
        finally:
            if showcase is not None:
                showcase.close()


# Run your test scenarios by writing them here. Make sure to keep track of them.

def run_test_scenarios(display_mode: str = "showcase"):
    """
    Run the bundled sample scenarios through the orchestrator.

    Args:
        display_mode: Terminal presentation mode for the run. Supported values
            are `showcase`, `debug`, and `quiet`.

    Returns:
        List of scenario result dictionaries.
    """
    normalized_mode = normalize_display_mode(display_mode)
    console = Console() if normalized_mode == "showcase" and Console is not None else None

    if normalized_mode == "showcase" and console is not None and Panel is not None:
        console.print(
            Panel(
                "Initializing database and launching the premium request pipeline.",
                title="[bold bright_white]Munder Difflin Showcase[/bold bright_white]",
                border_style="bright_cyan",
                box=box.ASCII,
                padding=(1, 2),
            )
        )
    else:
        print("Initializing Database...")

    init_database(db_engine)
    create_memory_tables(db_engine)
    try:
        quote_requests_sample = pd.read_csv("quote_requests_sample.csv")
        quote_requests_sample["request_date"] = pd.to_datetime(
            quote_requests_sample["request_date"], format="%m/%d/%y", errors="coerce"
        )
        quote_requests_sample.dropna(subset=["request_date"], inplace=True)
        quote_requests_sample = quote_requests_sample.sort_values("request_date")
    except Exception as e:
        print(f"FATAL: Error loading test data: {e}")
        return

    # Get initial state
    initial_date = quote_requests_sample["request_date"].min().strftime("%Y-%m-%d")
    report = generate_financial_report(initial_date)
    current_cash = report["cash_balance"]
    current_inventory = report["inventory_value"]

    orchestrator = OrchestratorAgent(model)

    results = []
    for idx, row in quote_requests_sample.iterrows():
        request_date = row["request_date"].strftime("%Y-%m-%d")
        context_label = f"{row['job']} organizing {row['event']}"

        if normalized_mode != "showcase":
            print(f"\n=== Request {idx+1} ===")
            print(f"Context: {context_label}")
            print(f"Request Date: {request_date}")
            print(f"Cash Balance: {format_currency(current_cash)}")
            print(f"Inventory Value: {format_currency(current_inventory)}")

        # Process request
        request_with_date = f"{row['request']} (Date of request: {request_date})"

        response = orchestrator.process_request(
            request_with_date,
            request_id=str(idx + 1),
            display_mode=normalized_mode,
            request_context={
                "context_label": context_label,
                "request_date": request_date,
                "cash_balance": current_cash,
                "inventory_value": current_inventory,
            },
        )

        # Update state
        report = generate_financial_report(request_date)
        current_cash = report["cash_balance"]
        current_inventory = report["inventory_value"]

        if normalized_mode == "showcase" and console is not None and Panel is not None:
            console.print(
                Panel(
                    (
                        f"{response}\n"
                        f"Updated Cash: {format_currency(current_cash)}\n"
                        f"Updated Inventory: {format_currency(current_inventory)}"
                    ),
                    title=f"[bold bright_white]Request {idx + 1} Ledger Snapshot[/bold bright_white]",
                    border_style="bright_green",
                    box=box.ASCII,
                    padding=(1, 2),
                )
            )
        else:
            print(f"Response: {response}")
            print(f"Updated Cash: {format_currency(current_cash)}")
            print(f"Updated Inventory: {format_currency(current_inventory)}")

        results.append(
            {
                "request_id": idx + 1,
                "request_date": request_date,
                "cash_balance": current_cash,
                "inventory_value": current_inventory,
                "response": response,
            }
        )

        time.sleep(0.35 if normalized_mode == "showcase" else 1)

    # Final report
    final_date = quote_requests_sample["request_date"].max().strftime("%Y-%m-%d")
    final_report = generate_financial_report(final_date)
    if normalized_mode == "showcase" and console is not None and Panel is not None:
        final_table = Table.grid(padding=(0, 2))
        final_table.add_column(style="bold bright_white", justify="right")
        final_table.add_column(style="white")
        final_table.add_row("Final Cash", format_currency(final_report["cash_balance"]))
        final_table.add_row("Final Inventory", format_currency(final_report["inventory_value"]))
        final_table.add_row("Requests Processed", str(len(results)))
        console.print(
            Panel(
                final_table,
                title="[bold bright_white]Final Financial Report[/bold bright_white]",
                border_style="bright_yellow",
                box=box.ASCII,
                padding=(1, 2),
            )
        )
    else:
        print("\n===== FINAL FINANCIAL REPORT =====")
        print(f"Final Cash: {format_currency(final_report['cash_balance'])}")
        print(f"Final Inventory: {format_currency(final_report['inventory_value'])}")

    # Save results
    pd.DataFrame(results).to_csv("test_results.csv", index=False)
    return results


if __name__ == "__main__":
    results = run_test_scenarios(
        display_mode=os.getenv("MUNDER_DISPLAY_MODE", "showcase")
    )
