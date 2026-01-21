# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**不败之地 (Unbeatable Position)** - A value investing tool that replaces "guessing market direction" with a disciplined system: competence circle stock pool + PB trigger prices + 4-action workflow (Buy/Add/Hold/Sell) + risk controls and structural reviews.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the Streamlit app
streamlit run app.py

# Initialize demo data (optional)
python scripts/init_demo_data.py
```

## Project Structure

```
UBA/
├── app.py                    # Main Streamlit entry point
├── pages/                    # Streamlit multi-page app
│   ├── 1_📋_股票池.py        # Stock pool management
│   ├── 2_📊_仪表盘.py        # Dashboard with signals overview
│   ├── 3_🔔_信号中心.py      # Signal handling & 4-action workflow
│   ├── 4_💼_持仓管理.py      # Portfolio management
│   └── 5_📈_股票详情.py      # Stock detail with PB charts
├── src/
│   ├── database/
│   │   ├── models.py         # SQLAlchemy models (Asset, Threshold, Valuation, Signal, Action, etc.)
│   │   └── connection.py     # Database connection management
│   └── services/
│       ├── stock_pool.py     # Stock pool CRUD operations
│       ├── valuation.py      # PB data fetching (akshare) and storage
│       ├── signal_engine.py  # PB trigger detection and signal generation
│       ├── risk_control.py   # Position limits and compliance checks
│       ├── action_service.py # 4-action workflow execution and logging
│       ├── stock_analyzer.py # Auto-analysis: stock info, PB stats, threshold recommendations
│       └── realtime_service.py # Real-time quote fetching (price, PB, change%)
├── data/                     # SQLite database (auto-created)
└── scripts/
    └── init_demo_data.py     # Demo data generator
```

## Tech Stack

- **UI**: Streamlit
- **Database**: SQLite + SQLAlchemy
- **Data Source**: 东方财富 API (real-time), Tushare (historical PB, optional)
- **Charts**: Plotly

## Core Data Models

- `Asset` - Stock pool with competence scores and notes
- `Threshold` - PB trigger thresholds per stock (buy/add/sell)
- `Valuation` - Historical PB data with source tracking
- `PortfolioPosition` - Current holdings and average costs
- `Signal` - Generated buy/add/sell signals when PB crosses thresholds
- `Action` - Trade execution logs with mandatory reasoning
- `Cost` - Transaction fees, taxes, slippage

## Key Business Logic

### Signal Generation (signal_engine.py)
- BUY signal: current PB <= buy_pb threshold
- ADD signal: holding position AND current PB <= add_pb threshold
- SELL signal: holding position AND current PB >= sell_pb threshold
- Each signal includes human-readable explanation with percentile info

### Risk Control (risk_control.py)
- Single stock position cap: 10% (configurable)
- Total position cap: 100%
- Force-execute requires explicit reason

### 4-Action Workflow (action_service.py)
- BUY/ADD/HOLD/SELL with mandatory `reason` field
- Optional emotion tracking
- Compliance logging for violations

### Stock Auto-Analysis (stock_analyzer.py)
- Auto-detect stock name, market, industry from code
- Fetch 5-year PB history (Tushare with fallback to 东方财富)
- Calculate: min/max/avg/median PB, percentiles
- Recommend thresholds: buy_pb (25th percentile), add_pb (10th), sell_pb (75th)

### Real-time Data (realtime_service.py)
- Fetch real-time quotes: price, PB, PE, change%, volume
- Batch fetching for multiple stocks
- Used by dashboard for live monitoring
- Auto-refresh every 30 seconds (configurable)
