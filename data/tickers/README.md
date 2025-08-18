# Ticker Data Sources

This directory contains processed ticker data for the Market Pulse system.

## Data Sources

### Primary Sources

1. **NASDAQ Listed Stocks**
   - Source: https://www.nasdaq.com/market-activity/stocks/screener?download=true
   - Description: Official NASDAQ stock screener with all listed securities
   - Updated: Daily
   - Format: CSV with Symbol, Name, Last Sale, Net Change, % Change, Market Cap, Country, IPO Year, Volume, Sector, Industry

2. **NYSE Listed Stocks**
   - Source: https://www.nasdaq.com/market-activity/stocks/screener?exchange=nyse&download=true
   - Description: NYSE stock screener via NASDAQ's platform
   - Updated: Daily
   - Format: Same as NASDAQ format

### Secondary Sources

3. **S&P 500 Companies**
   - Source: https://en.wikipedia.org/wiki/List_of_S%26P_500_companies
   - Description: Wikipedia table of S&P 500 constituents
   - Updated: As Wikipedia is updated
   - Format: HTML table with Symbol, Security, GICS Sector, GICS Sub-Industry, Headquarters Location, Date Added, Founded

4. **SEC CIK Mapping**
   - Source: https://www.sec.gov/files/company_tickers.json
   - Description: Official SEC mapping of ticker symbols to CIK numbers
   - Updated: Regularly by SEC
   - Format: JSON with cik_str, name, ticker, exchange, sic, sicDescription, category

## Data Processing

### Cleaning Rules Applied

1. **Symbol Cleaning**
   - Convert to uppercase
   - Strip whitespace
   - Remove trailing suffixes (^, /, .)
   - Filter out test/placeholder symbols
   - Validate with regex: `^[A-Z]{1,5}$`

2. **Name Cleaning**
   - Strip whitespace and normalize
   - Remove common corporate suffixes (Inc, Corp, Corporation, Company, Co, LLC, Ltd, Limited)

3. **Deduplication**
   - Remove duplicate symbols
   - Merge names when identical but different cases

4. **Alias Generation**
   - Cashtag format: `$SYMBOL`
   - Lowercase symbol
   - Lowercase company name
   - Company name without spaces
   - Common synonyms (e.g., "apple" → "aapl", "apple inc", "apple computer")
   - S&P 500 indicator for constituents

### Special Handling

- **Class Shares**: BRK.A and BRK.B are kept with aliases to BRK
- **Preferred Shares**: Ignored (filtered out)
- **Test Listings**: Removed (TEST, DUMMY, PLACEHOLDER, etc.)

## Output Files

- `tickers_main.csv`: Main ticker data with all fields
- `tickers_by_exchange.csv`: Count breakdown by exchange
- `README.md`: This documentation file

## Validation

The seeding script validates:
- Minimum 6,000 tickers total
- No duplicate symbols
- Regex validity for all symbols
- Aliases present for top 100 symbols
- Database insertion success

## Usage

Run the seeding script:
```bash
make seed-tickers
```

Or directly:
```bash
uv run python -m scripts.seed_tickers
```

## Database Schema

The processed data populates the `ticker` table with:
- `symbol` (TEXT PK): Cleaned ticker symbol
- `name` (TEXT): Cleaned company name
- `exchange` (TEXT): NASDAQ, NYSE, etc.
- `cik` (TEXT NULL): SEC CIK number
- `aliases` (JSONB): Generated aliases and synonyms
- `valid_from` (DATE NULL): Historical validity start
- `valid_to` (DATE NULL): Historical validity end

## Maintenance

The data should be refreshed periodically to capture:
- New listings
- Delistings
- Symbol changes
- Company name changes
- S&P 500 constituent changes

Consider running the seeding script weekly or monthly depending on your needs.
