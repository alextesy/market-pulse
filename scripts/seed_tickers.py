#!/usr/bin/env python3
"""Ticker seeding script for Market Pulse.

Downloads and processes ticker data from NASDAQ, NYSE, and other sources.
Implements cleaning rules and alias generation as specified in requirements.
"""

import csv
import logging
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.request import urlopen

import pandas as pd
import yaml
from sqlalchemy.exc import IntegrityError

from market_pulse.db.session import get_db_session
from market_pulse.repos.ticker import TickerRepository
from market_pulse.settings import get_settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Data sources
NASDAQ_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
NYSE_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"
SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
SEC_CIK_URL = "https://www.sec.gov/files/company_tickers.json"

# Common company synonyms for alias generation
COMPANY_SYNONYMS = {
    "apple": ["aapl", "apple inc", "apple computer"],
    "microsoft": ["msft", "microsoft corporation"],
    "amazon": ["amzn", "amazon.com", "amazon.com inc"],
    "google": ["googl", "goog", "alphabet", "alphabet inc"],
    "tesla": ["tsla", "tesla inc", "tesla motors"],
    "netflix": ["nflx", "netflix inc"],
    "facebook": ["meta", "fb", "meta platforms", "facebook inc"],
    "nvidia": ["nvda", "nvidia corporation"],
    "berkshire": ["brk", "brk.a", "brk.b", "berkshire hathaway"],
    "jpmorgan": ["jpm", "jp morgan", "jpmorgan chase", "jpmorgan chase & co"],
    "bank of america": ["bac", "bofa", "bank of america corporation"],
    "walmart": ["wmt", "wal-mart", "wal-mart stores"],
    "disney": ["dis", "walt disney", "walt disney company"],
    "coca-cola": ["ko", "coke", "coca cola", "coca-cola company"],
    "mcdonalds": ["mcd", "mcdonald's", "mcdonalds corporation"],
}

# Test/placeholder tickers to exclude
TEST_TICKERS = {
    "TEST",
    "DUMMY",
    "PLACEHOLDER",
    "EXAMPLE",
    "SAMPLE",
    "TEMP",
    "TMP",
    "ZZZZ",
    "AAAA",
    "BBBB",
    "CCCC",
    "DDDD",
    "EEEE",
    "FFFF",
}

# Regex for valid ticker symbols (allows dots for class shares and digits)
TICKER_REGEX = re.compile(r"^[A-Z][A-Z0-9]{0,4}(\.[A-Z])?$")


def download_nasdaq_data() -> pd.DataFrame:
    """Download NASDAQ ticker data."""
    logger.info("Downloading NASDAQ ticker data...")
    try:
        df = pd.read_csv(NASDAQ_URL, sep="|")

        # Check that data is not null
        if df.empty:
            logger.error("Downloaded NASDAQ data is empty")
            return pd.DataFrame()

        if df.isnull().all().all():
            logger.error("Downloaded NASDAQ data contains only null values")
            return pd.DataFrame()

        logger.info(f"Downloaded {len(df)} NASDAQ tickers")
        return df
    except Exception as e:
        logger.error(f"Failed to download NASDAQ data: {e}")
        return pd.DataFrame()


def download_nyse_data() -> pd.DataFrame:
    """Download NYSE ticker data."""
    logger.info("Downloading NYSE ticker data...")
    try:
        df = pd.read_csv(NYSE_URL, sep="|")

        # Check that data is not null
        if df.empty:
            logger.error("Downloaded NYSE data is empty")
            return pd.DataFrame()

        if df.isnull().all().all():
            logger.error("Downloaded NYSE data contains only null values")
            return pd.DataFrame()

        logger.info(f"Downloaded {len(df)} NYSE tickers")
        return df
    except Exception as e:
        logger.error(f"Failed to download NYSE data: {e}")
        return pd.DataFrame()


def download_sp500_data() -> pd.DataFrame:
    """Download S&P 500 data from Wikipedia."""
    logger.info("Downloading S&P 500 data...")
    try:
        # Read S&P 500 table from Wikipedia
        tables = pd.read_html(SP500_URL)
        if tables:
            df = tables[0]  # First table contains the ticker data
            # Rename columns to match our expected format
            df = df.rename(
                columns={
                    "Symbol": "Symbol",
                    "Security": "Name",
                    "GICS Sector": "Sector",
                }
            )
            logger.info(f"Downloaded {len(df)} S&P 500 tickers")
            return df
    except Exception as e:
        logger.error(f"Failed to download S&P 500 data: {e}")
    return pd.DataFrame()


def download_sec_cik_data() -> Dict[str, str]:
    """Download SEC CIK↔ticker map (pads CIK to 10)."""
    logger.info("Downloading SEC CIK data...")
    try:
        import json
        import urllib.request

        headers = {
            "User-Agent": "MarketPulseBot/1.0 (alex@example.com)",  # include email
            "Accept": "application/json",
        }
        req = urllib.request.Request(SEC_CIK_URL, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.load(resp)

        # data is dict keyed by "0","1",... each with {"cik_str","ticker","title"}
        cik_map = {
            item["ticker"].upper().strip(): str(item["cik_str"]).zfill(10)
            for item in (data.values() if isinstance(data, dict) else data)
            if isinstance(item, dict)
            and item.get("ticker")
            and item.get("cik_str") is not None
        }

        logger.info(f"Downloaded {len(cik_map)} CIK mappings")
        return cik_map
    except Exception as e:
        logger.error(f"Failed to download SEC CIK data: {e}")
        return {}


def clean_ticker_symbol(symbol: str) -> Optional[str]:
    """Clean ticker symbol according to rules."""
    if not symbol or not isinstance(symbol, str):
        return None

    # Convert to uppercase and strip whitespace
    cleaned = symbol.upper().strip()

    # Remove common suffixes
    cleaned = re.sub(r"[./^]$", "", cleaned)

    # Remove test/placeholder tickers
    if cleaned in TEST_TICKERS:
        return None

    # Validate with regex
    if not TICKER_REGEX.match(cleaned):
        return None

    return cleaned


def clean_company_name(name: str) -> Optional[str]:
    """Clean company name."""
    if not name or not isinstance(name, str):
        return None

    # Strip whitespace and normalize
    cleaned = " ".join(name.strip().split())

    # Remove common suffixes
    cleaned = re.sub(
        r"\s+(Inc|Corp|Corporation|Company|Co|LLC|Ltd|Limited)\s*$",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    return cleaned if cleaned else None


def load_manual_aliases() -> Dict[str, List[str]]:
    """Load manual aliases from YAML file."""
    manual_aliases_file = Path("data/tickers/manual_aliases.yaml")
    if not manual_aliases_file.exists():
        logger.warning("Manual aliases file not found")
        return {}

    try:
        with open(manual_aliases_file, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("aliases", {})
    except Exception as e:
        logger.error(f"Failed to load manual aliases: {e}")
        return {}


def generate_aliases(symbol: str, name: str) -> Dict[str, List[str]]:
    """Generate aliases for a ticker."""
    aliases = []

    # Add cashtag
    aliases.append(f"${symbol}")

    # Add lowercase version
    aliases.append(symbol.lower())

    # Add company name variations
    if name:
        # Add lowercase name
        aliases.append(name.lower())

        # Add name without spaces
        aliases.append(name.lower().replace(" ", ""))

        # Add common synonyms
        name_lower = name.lower()
        for synonym_key, synonym_list in COMPANY_SYNONYMS.items():
            if synonym_key in name_lower:
                aliases.extend(synonym_list)

    # Add manual aliases
    manual_aliases = load_manual_aliases()
    if symbol in manual_aliases:
        aliases.extend(manual_aliases[symbol])

    # Remove duplicates
    aliases = list(set(aliases))

    return {"aliases": aliases}


def process_ticker_data() -> List[Dict]:
    """Process and clean all ticker data sources."""
    logger.info("Processing ticker data sources...")

    # Download data from all sources
    nasdaq_df = download_nasdaq_data()
    nyse_df = download_nyse_data()
    sp500_df = download_sp500_data()
    cik_map = download_sec_cik_data()

    # Combine all data
    all_tickers = []
    seen_symbols = set()

    # Process NASDAQ data
    if not nasdaq_df.empty:
        for _, row in nasdaq_df.iterrows():
            symbol = clean_ticker_symbol(row.get("Symbol", ""))
            if not symbol or symbol in seen_symbols:
                continue

            name = clean_company_name(row.get("Security Name", ""))
            exchange = "NASDAQ"
            cik = cik_map.get(symbol)

            ticker_data = {
                "symbol": symbol,
                "name": name,
                "exchange": exchange,
                "cik": cik,
                "aliases": generate_aliases(symbol, name),
                "valid_from": None,
                "valid_to": None,
            }

            all_tickers.append(ticker_data)
            seen_symbols.add(symbol)

    # Process NYSE data
    if not nyse_df.empty:
        for _, row in nyse_df.iterrows():
            symbol = clean_ticker_symbol(row.get("ACT Symbol", ""))
            if not symbol or symbol in seen_symbols:
                continue

            name = clean_company_name(row.get("Security Name", ""))
            exchange = "NYSE"
            cik = cik_map.get(symbol)

            ticker_data = {
                "symbol": symbol,
                "name": name,
                "exchange": exchange,
                "cik": cik,
                "aliases": generate_aliases(symbol, name),
                "valid_from": None,
                "valid_to": None,
            }

            all_tickers.append(ticker_data)
            seen_symbols.add(symbol)

    # Process S&P 500 data (add as additional exchange info)
    if not sp500_df.empty:
        sp500_symbols = set()
        for _, row in sp500_df.iterrows():
            symbol = clean_ticker_symbol(row.get("Symbol", ""))
            if symbol:
                sp500_symbols.add(symbol)

        # Update existing tickers with S&P 500 info
        for ticker in all_tickers:
            if ticker["symbol"] in sp500_symbols:
                if not ticker.get("aliases"):
                    ticker["aliases"] = {"aliases": []}
                ticker["aliases"]["aliases"].append("sp500")

    logger.info(f"Processed {len(all_tickers)} unique tickers")
    return all_tickers


def save_to_csv(tickers: List[Dict], output_dir: Path) -> None:
    """Save processed ticker data to CSV files."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save main ticker data
    main_file = output_dir / "tickers_main.csv"
    with open(main_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["symbol", "name", "exchange", "cik", "aliases"]
        )
        writer.writeheader()
        for ticker in tickers:
            writer.writerow(
                {
                    "symbol": ticker["symbol"],
                    "name": ticker["name"],
                    "exchange": ticker["exchange"],
                    "cik": ticker["cik"],
                    "aliases": ticker["aliases"],
                }
            )

    logger.info(f"Saved {len(tickers)} tickers to {main_file}")

    # Save exchange breakdown
    exchange_counts = {}
    for ticker in tickers:
        exchange = ticker["exchange"]
        exchange_counts[exchange] = exchange_counts.get(exchange, 0) + 1

    exchange_file = output_dir / "tickers_by_exchange.csv"
    with open(exchange_file, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["exchange", "count"])
        for exchange, count in exchange_counts.items():
            writer.writerow([exchange, count])

    logger.info(f"Saved exchange breakdown to {exchange_file}")


def validate_tickers(tickers: List[Dict]) -> bool:
    """Validate ticker data according to acceptance criteria."""
    logger.info("Validating ticker data...")

    # Check minimum count
    if len(tickers) < 6000:
        logger.error(f"Only {len(tickers)} tickers found, need at least 6000")
        return False

    # Check for duplicates
    symbols = [t["symbol"] for t in tickers]
    if len(symbols) != len(set(symbols)):
        logger.error("Duplicate symbols found")
        return False

    # Check regex validity
    invalid_symbols = [s for s in symbols if not TICKER_REGEX.match(s)]
    if invalid_symbols:
        logger.error(f"Invalid symbols found: {invalid_symbols[:10]}")
        return False

    # Check aliases for top symbols
    top_symbols = [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "TSLA",
        "META",
        "NVDA",
        "BRK.A",
        "JPM",
        "V",
    ]
    missing_aliases = []
    for symbol in top_symbols:
        ticker = next((t for t in tickers if t["symbol"] == symbol), None)
        if not ticker or not ticker.get("aliases"):
            missing_aliases.append(symbol)

    if missing_aliases:
        logger.warning(f"Missing aliases for top symbols: {missing_aliases}")

    logger.info("Ticker validation passed")
    return True


def seed_database(tickers: List[Dict]) -> bool:
    """Seed the database with ticker data."""
    logger.info("Seeding database with ticker data...")

    repo = TickerRepository()

    try:
        # Clear existing data (optional - comment out if you want to preserve)
        with get_db_session() as session:
            session.execute("DELETE FROM ticker")
            session.commit()

        # Bulk insert tickers
        repo.bulk_insert_tickers(tickers)

        # Verify insertion
        with get_db_session() as session:
            count = session.execute("SELECT COUNT(*) FROM ticker").scalar()
            logger.info(f"Successfully seeded {count} tickers in database")

        return True
    except Exception as e:
        logger.error(f"Failed to seed database: {e}")
        return False


def main() -> int:
    """Main function for ticker seeding."""
    logger.info("Starting ticker seeding process...")

    # Get settings
    settings = get_settings()

    # Create output directory
    output_dir = Path("data/tickers")

    try:
        # Process ticker data
        tickers = process_ticker_data()

        if not tickers:
            logger.error("No ticker data processed")
            return 1

        # Validate data
        if not validate_tickers(tickers):
            logger.error("Ticker validation failed")
            return 1

        # Save to CSV
        save_to_csv(tickers, output_dir)

        # Seed database
        if not seed_database(tickers):
            logger.error("Database seeding failed")
            return 1

        logger.info("Ticker seeding completed successfully")
        return 0

    except Exception as e:
        logger.error(f"Ticker seeding failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
