# Finnhub Data Catalog - Cryptocurrency Data

## Tổng quan

Finnhub cung cấp 2 loại API chính cho dữ liệu crypto:

1. **WebSocket API** - Real-time streaming data (trades)
2. **REST API** - Historical & aggregated data (candles, exchanges, symbols)

---

## 1. WebSocket API - Real-time Data

### 1.1 Crypto Trades (Real-time)

**Endpoint**: `wss://ws.finnhub.io?token={API_KEY}`

**Data Type**: Live trade executions

**Message Format**:

```json
{
  "type": "trade",
  "data": [
    {
      "s": "BINANCE:BTCUSDT", // Symbol
      "p": 43250.5, // Price
      "t": 1699123456789, // Timestamp (ms)
      "v": 0.125, // Volume
      "c": ["@"] // Conditions
    }
  ]
}
```

**Supported Exchanges**:

- BINANCE
- COINBASE
- KRAKEN
- BITFINEX
- BITSTAMP
- GEMINI
- HUOBI
- FTX (discontinued)

**Use Cases**:

- Real-time trade monitoring
- Price alerts
- High-frequency trading analysis
- Market microstructure analysis

**Medallion Architecture**:

- **Bronze Layer**: Raw trades với timestamp, symbol, price, volume
- **Silver Layer**: Clean data, standardize exchanges, deduplicate
- **Gold Layer**: Aggregated metrics (VWAP, trade volume per interval, price changes)

---

## 2. REST API - Historical & Aggregated Data

### 2.1 Crypto Candles (OHLC)

**Endpoint**: `GET https://finnhub.io/api/v1/crypto/candle`

**Parameters**:

- `symbol`: Crypto pair (e.g., BINANCE:BTCUSDT)
- `resolution`: Time interval (1, 5, 15, 30, 60, D, W, M)
  - `1` = 1 minute
  - `5` = 5 minutes
  - `15` = 15 minutes
  - `30` = 30 minutes
  - `60` = 1 hour
  - `D` = Daily
  - `W` = Weekly
  - `M` = Monthly
- `from`: Start timestamp (Unix seconds)
- `to`: End timestamp (Unix seconds)

**Response**:

```json
{
  "c": [43250.5, 43300.2], // Close prices
  "h": [43350.0, 43400.5], // High prices
  "l": [43200.0, 43250.0], // Low prices
  "o": [43220.0, 43260.0], // Open prices
  "v": [125.5, 130.2], // Volume
  "t": [1699123200, 1699123260], // Timestamps
  "s": "ok" // Status
}
```

**Use Cases**:

- Historical price analysis
- Backtesting trading strategies
- Technical indicators calculation
- Trend analysis

**Medallion Architecture**:

- **Bronze Layer**: Raw OHLC data với resolution timestamp
- **Silver Layer**: Fill missing candles, handle gaps, validate OHLC constraints
- **Gold Layer**: Technical indicators (SMA, EMA, RSI, MACD, Bollinger Bands)

---

### 2.2 Crypto Exchanges

**Endpoint**: `GET https://finnhub.io/api/v1/crypto/exchange`

**Response**:

```json
[
  "BINANCE",
  "COINBASE",
  "KRAKEN",
  "BITFINEX",
  ...
]
```

**Use Cases**:

- List available exchanges
- Multi-exchange analysis
- Exchange metadata

**Medallion Architecture**:

- **Bronze**: Raw exchange list
- **Silver**: Exchange metadata (region, trading pairs count)
- **Gold**: Exchange rankings, liquidity analysis

---

### 2.3 Crypto Symbols

**Endpoint**: `GET https://finnhub.io/api/v1/crypto/symbol?exchange={EXCHANGE}`

**Parameters**:

- `exchange`: Exchange name (e.g., BINANCE)

**Response**:

```json
[
  {
    "description": "Binance BTCUSDT",
    "displaySymbol": "BTC/USDT",
    "symbol": "BINANCE:BTCUSDT"
  },
  {
    "description": "Binance ETHUSDT",
    "displaySymbol": "ETH/USDT",
    "symbol": "BINANCE:ETHUSDT"
  }
]
```

**Use Cases**:

- Symbol discovery
- Available pairs listing
- Trading pair metadata

**Medallion Architecture**:

- **Bronze**: Raw symbol list per exchange
- **Silver**: Standardize symbol format, extract base/quote currency
- **Gold**: Symbol popularity, trading activity, pair correlations

---

### 2.4 Crypto Profile (Coming Soon / Premium)

**Endpoint**: May require premium tier

**Data**:

- Market cap
- Circulating supply
- Total supply
- Max supply
- Website
- Description

---

## 3. Data Collection Strategy

### 3.1 Real-time Collection (WebSocket)

```python
# Current Implementation
WEBSOCKET_SYMBOLS = [
    "BINANCE:BTCUSDT",
    "BINANCE:ETHUSDT",
    "BINANCE:BNBUSDT",
]

# Bronze Layer: Raw trades
# Table: bronze.crypto_trades
# Partition: by date (trade_date)
```

### 3.2 Historical Collection (REST)

```python
# Batch job - Airflow DAG
HISTORICAL_SYMBOLS = [
    "BINANCE:BTCUSDT",
    "BINANCE:ETHUSDT",
]

RESOLUTIONS = ["1", "5", "15", "60", "D"]

# Bronze Layer: Raw OHLC candles
# Table: bronze.crypto_candles
# Partition: by symbol, resolution, date
```

---

## 4. Recommended Data Pipeline

### Phase 1: Real-time Trades (Current)

**Data Source**: WebSocket Trades

**Pipeline**:

```
WebSocket → Kafka (finnhub-btc) → Spark → Iceberg (Bronze)
```

**Tables**:

- `bronze.crypto_trades_raw`

**Columns**:

```sql
CREATE TABLE bronze.crypto_trades_raw (
    symbol STRING,
    price DOUBLE,
    volume DOUBLE,
    timestamp_ms BIGINT,
    conditions ARRAY<STRING>,
    trade_date DATE,
    ingestion_timestamp TIMESTAMP
) PARTITIONED BY (trade_date);
```

---

### Phase 2: Historical Candles

**Data Source**: REST API Crypto Candles

**Pipeline**:

```
Airflow → REST API → S3/MinIO → Spark → Iceberg (Bronze)
```

**Tables**:

- `bronze.crypto_candles_raw`

**Columns**:

```sql
CREATE TABLE bronze.crypto_candles_raw (
    symbol STRING,
    resolution STRING,
    open_price DOUBLE,
    high_price DOUBLE,
    low_price DOUBLE,
    close_price DOUBLE,
    volume DOUBLE,
    candle_timestamp BIGINT,
    candle_date DATE,
    ingestion_timestamp TIMESTAMP
) PARTITIONED BY (symbol, resolution, candle_date);
```

---

### Phase 3: Silver Layer Transformations

#### 3.1 Trades → Aggregated Trades

**Transformations**:

- Deduplicate trades (same symbol, price, timestamp)
- Standardize symbol format
- Convert timestamp to datetime
- Flag suspicious trades (outliers)
- Enrich with exchange metadata

**Table**: `silver.crypto_trades_clean`

```sql
CREATE TABLE silver.crypto_trades_clean (
    trade_id STRING,  -- Generated UUID
    exchange STRING,
    base_currency STRING,
    quote_currency STRING,
    price DOUBLE,
    volume DOUBLE,
    trade_datetime TIMESTAMP,
    trade_date DATE,
    is_outlier BOOLEAN,
    processing_timestamp TIMESTAMP
) PARTITIONED BY (exchange, trade_date);
```

#### 3.2 Candles → Validated Candles

**Transformations**:

- Validate OHLC constraints (L ≤ O,C ≤ H)
- Fill missing candles (forward-fill, interpolation)
- Calculate derived metrics (price_change, price_change_pct)
- Flag gaps and anomalies

**Table**: `silver.crypto_candles_clean`

```sql
CREATE TABLE silver.crypto_candles_clean (
    candle_id STRING,
    exchange STRING,
    base_currency STRING,
    quote_currency STRING,
    resolution STRING,
    open_price DOUBLE,
    high_price DOUBLE,
    low_price DOUBLE,
    close_price DOUBLE,
    volume DOUBLE,
    candle_datetime TIMESTAMP,
    price_change DOUBLE,
    price_change_pct DOUBLE,
    has_gap BOOLEAN,
    is_valid BOOLEAN,
    processing_timestamp TIMESTAMP
) PARTITIONED BY (exchange, resolution, candle_date);
```

---

### Phase 4: Gold Layer Analytics

#### 4.1 Trading Metrics

**Table**: `gold.crypto_trading_metrics`

```sql
CREATE TABLE gold.crypto_trading_metrics (
    metric_date DATE,
    exchange STRING,
    symbol STRING,
    -- Price metrics
    open_price DOUBLE,
    close_price DOUBLE,
    high_price DOUBLE,
    low_price DOUBLE,
    vwap DOUBLE,  -- Volume Weighted Average Price
    -- Volume metrics
    total_volume DOUBLE,
    trade_count BIGINT,
    avg_trade_size DOUBLE,
    -- Volatility
    price_std_dev DOUBLE,
    price_range DOUBLE,
    -- Returns
    daily_return DOUBLE,
    daily_return_pct DOUBLE
) PARTITIONED BY (exchange, metric_date);
```

#### 4.2 Technical Indicators

**Table**: `gold.crypto_technical_indicators`

```sql
CREATE TABLE gold.crypto_technical_indicators (
    indicator_date DATE,
    exchange STRING,
    symbol STRING,
    resolution STRING,
    -- Moving Averages
    sma_7 DOUBLE,
    sma_14 DOUBLE,
    sma_30 DOUBLE,
    ema_7 DOUBLE,
    ema_14 DOUBLE,
    ema_30 DOUBLE,
    -- Momentum
    rsi_14 DOUBLE,
    macd DOUBLE,
    macd_signal DOUBLE,
    macd_histogram DOUBLE,
    -- Volatility
    bb_upper DOUBLE,
    bb_middle DOUBLE,
    bb_lower DOUBLE,
    atr_14 DOUBLE
) PARTITIONED BY (exchange, resolution, indicator_date);
```

#### 4.3 Market Summary

**Table**: `gold.crypto_market_summary`

```sql
CREATE TABLE gold.crypto_market_summary (
    summary_date DATE,
    exchange STRING,
    -- Overall metrics
    total_trading_volume DOUBLE,
    total_trades BIGINT,
    active_pairs INT,
    -- Top performers
    top_gainer_symbol STRING,
    top_gainer_change_pct DOUBLE,
    top_loser_symbol STRING,
    top_loser_change_pct DOUBLE,
    -- Market sentiment
    positive_returns_count INT,
    negative_returns_count INT,
    market_sentiment STRING  -- bullish, bearish, neutral
) PARTITIONED BY (summary_date);
```

---

## 5. Data Volume Estimates

### Real-time Trades (WebSocket)

**Assumptions**:

- 1 symbol (BTC)
- ~100 trades/hour (conservative for free tier)
- 24 hours/day

**Daily Volume**:

- Trades: ~2,400 records/day
- Size: ~2,400 × 200 bytes = 480 KB/day
- Monthly: ~14 MB

**Multiple Symbols**:

- 10 symbols: ~140 MB/month
- 50 symbols: ~700 MB/month

### Historical Candles (REST)

**Assumptions**:

- 10 symbols
- 5 resolutions (1m, 5m, 15m, 1h, 1d)
- 1 year history

**Volume**:

- 1-minute: 525,600 candles/year/symbol
- Daily: 365 candles/year/symbol
- Total: ~5.8M candles for 10 symbols
- Size: ~5.8M × 100 bytes = 580 MB

---

## 6. API Rate Limits

### Free Tier

- WebSocket: 1 connection
- REST API: 60 calls/minute
- Symbols: Limited to major pairs

### Premium Tier

- WebSocket: Multiple connections
- REST API: Higher rate limits
- All trading pairs

---

## 7. Recommended Implementation Priority

### Priority 1 (MVP) - COMPLETE

✅ WebSocket trades for BTC
✅ Kafka ingestion
✅ Basic Iceberg bronze table

### Priority 2 (Next)

🔄 Historical candles (REST API)
🔄 Airflow DAG for batch ingestion
🔄 Silver layer transformations

### Priority 3 (Advanced)

⏳ Multiple crypto pairs
⏳ Gold layer analytics
⏳ Technical indicators
⏳ Dashboard/visualization

### Priority 4 (Enterprise)

⏳ Real-time alerting
⏳ ML models (price prediction)
⏳ Multi-exchange arbitrage detection
⏳ Portfolio tracking

---

## 8. Sample Symbols for Testing

### Top 10 by Market Cap (Binance)

1. `BINANCE:BTCUSDT` - Bitcoin
2. `BINANCE:ETHUSDT` - Ethereum
3. `BINANCE:BNBUSDT` - Binance Coin
4. `BINANCE:SOLUSDT` - Solana
5. `BINANCE:XRPUSDT` - Ripple
6. `BINANCE:ADAUSDT` - Cardano
7. `BINANCE:DOGEUSDT` - Dogecoin
8. `BINANCE:AVAXUSDT` - Avalanche
9. `BINANCE:DOTUSDT` - Polkadot
10. `BINANCE:MATICUSDT` - Polygon

### Stable Pairs

- `BINANCE:USDCUSDT`
- `BINANCE:BUSDUSDT`

### DeFi Tokens

- `BINANCE:UNIUSDT` - Uniswap
- `BINANCE:LINKUSDT` - Chainlink
- `BINANCE:AAVEUSDT` - Aave

---

## 9. Next Steps

1. **Complete current WebSocket implementation**

   - Fix snappy compression issue ✅
   - Verify trades are flowing to Kafka
   - Create Spark job to write to Iceberg Bronze

2. **Implement Historical Data Collection**

   - Create Airflow DAG for REST API
   - Collect 1-day candles for top 10 cryptos
   - Write to Iceberg Bronze

3. **Build Silver Layer**

   - Spark job to clean and validate trades
   - Spark job to process candles
   - Implement data quality checks

4. **Build Gold Layer**

   - Aggregation jobs for metrics
   - Technical indicators calculation
   - Market summary generation

5. **Visualization**
   - Superset/Grafana dashboards
   - Real-time monitoring
   - Historical trend analysis
