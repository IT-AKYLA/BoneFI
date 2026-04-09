# BoneFi Token Analyzer Platform

A Solana token analysis system for detecting bots, insiders, and manipulations based on on-chain data.

## Architecture

The project consists of three independent services:

- **Data Management** — data collection and storage
- **Data Analysis** — data analytics
- **Client Management** — web interface for displaying results

## Features

### Data Collection
- Solana RPC connection via WARP proxy
- Redis data compression (gzip, compression ratio up to 25x)
- Automatic result caching

### Analytics
- Bot cluster detection by wallet creation time
- Insider identification
- Deployer-funded sniper detection
- Pattern-drawing bot detection
- Wash trading detection
- Sell pressure index
- Whale accumulation rate assessment

### Visualization
- Smart BubbleMap with color-coded wallet types
- Combined activity and volume charts
- Top holders tables with classification

## Risk Metrics

### Suspicious Supply Index (SSI)
Main metric — percentage of supply controlled by suspicious wallets:
- CRITICAL (>20%) — STRONG AVOID
- HIGH (10-20%) — AVOID
- MEDIUM (5-10%) — CAUTION
- LOW (<5%) — POTENTIAL

### Bot Classification
- MICRO_BOT — small holdings, many transactions
- SYNCHRONIZED_BOT — mass-created wallets
- MINNOW_BOT — small whales (0.2-1%)
- WHALE_BOT — large bots (1-3%)
- MEGA_WHALE_BOT — very large (>3%)

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /health | Health check |
| GET | /api/tokens | List all tokens |
| GET | /api/analyze/{mint} | Full token analysis |
| GET | /api/chart/{mint} | Combined chart |
| GET | /api/bubblemap/{mint} | BubbleMap data |

## Installation & Setup

### Local Development

```bash
# Clone repository
git clone https://github.com/IT-AKYLA/bonefi-analyzer-platform.git
cd bonefi-analyzer-platform

# Setup virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r data-management/requirements.txt
pip install -r data-analysis/requirements.txt

# Start Redis
docker-compose up -d redis

# Start API servers
cd data-analysis
python run_api.py

# New terminal
cd data-management
python run_api.py