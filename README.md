# BoneFi — Solana Token Intelligence Platform

<div align="center">
  <img src="https://img.shields.io/badge/Solana-14f195?style=for-the-badge&logo=solana&logoColor=black"/>
  <img src="https://img.shields.io/badge/Python-3.11-blue?style=for-the-badge&logo=python"/>
  <img src="https://img.shields.io/badge/FastAPI-0.104-teal?style=for-the-badge&logo=fastapi"/>
  <br>
  <strong>Analytics Platform for Solana Tokens — Focus on Small & Mid Cap</strong>
</div>

---

## About the Platform

BoneFi is a specialized analytics platform for in-depth Solana token analysis. We focus on small and mid-cap tokens where traditional tools often fall short due to limited data or unique on-chain activity patterns.

**Our mission** — fully automate on-chain data collection and analysis to provide traders and researchers with an objective picture: who actually holds the token, whether bots are present, how insiders behave, and the likelihood of a scam.

The platform is built on a microservices architecture consisting of three independent components:
- **Data Management** — data collection and storage
- **Data Analysis** — analytics and risk assessment
- **Client Management** — web interface

---

## Key Features

### Data Collection
- Automated transaction collection via Solana RPC
- WARP proxy support for bypassing rate limits
- Async processing for 100k+ transactions
- Data optimization for analytics

### Bot & Manipulation Detection
| Type | What We Detect |
|------|----------------|
| **Bot Clusters** | Wallets created en masse at the same time |
| **Insiders** | Wallets that bought within the first 5 minutes |
| **Snipers** | Wallets funded by the deployer |
| **Coordination** | Synchronized actions (3+ within 10 seconds) |
| **Wash Trading** | Artificial volume inflation |
| **Robotic Patterns** | Repeating amounts, perfect intervals |

### Risk Metrics
- **MSI (Malicious Supply Index)** — percentage of supply controlled by malicious bots
- **Temporal Entropy** — measures naturalness of timing patterns
- **Anti-Fragmentation** — detects fake holders
- **Domino Effect** — detects coordinated dumps
- **Migration Footprint** — analyzes early holder behavior
- **Herding Index** — detects bot armies

### Visualization
- **BubbleMap** — interactive holder distribution map
- **Activity Chart** — combined transaction and volume chart
- **Top Holders** — tables with classification

---

## Quick Start

```bash
# Clone repository
git clone https://github.com/IT-AKYLA/BoneFI.git
cd BoneFI

# Virtual environment
python -m venv venv
source venv/bin/activate  # Linux/Mac
venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
cd backend/data-analysis && pip install -r requirements.txt
cd ../data-management && pip install -r requirements.txt

# Start Redis
docker run -d -p 6379:6379 redis:7-alpine

# Run services
cd backend/data-management && python run_api.py   # port 8001
cd backend/data-analysis && python run_api.py     # port 8000

# Open web interface
open frontend/client-management/web-dashboard/BoneFI.html
Docker Deployment
bash
# Build and run all services
docker-compose -f deploy/docker-compose.yml up -d

# Check status
docker-compose -f deploy/docker-compose.yml ps

# View logs
docker-compose -f deploy/docker-compose.yml logs -f

# Stop all services
docker-compose -f deploy/docker-compose.yml down
API Examples
bash
# Analyze token
curl "http://localhost:8000/api/analyze/sync/5YC49sjG8SVXbnbTMFnUQmsPsBXKfR3jYERpmcXTpump"

# Get revolutionary score
curl "http://localhost:8000/api/token/5YC49sjG8SVXbnbTMFnUQmsPsBXKfR3jYERpmcXTpump/revolutionary/score"

# Get MSI (Malicious Supply Index)
curl "http://localhost:8000/api/token/5YC49sjG8SVXbnbTMFnUQmsPsBXKfR3jYERpmcXTpump/malicious"

# List top holders
curl "http://localhost:8000/api/token/5YC49sjG8SVXbnbTMFnUQmsPsBXKfR3jYERpmcXTpump/holders?limit=20"
Testing
bash
# Run unit tests
pytest backend/data-analysis/tests/ -v
pytest backend/data-management/tests/ -v

# Run integration tests (requires running services)
pytest tests/integration/ -v -m "integration"

# Run with coverage
pytest --cov=backend --cov-report=html
License
MIT © 2025 BoneFi Team

<div align="center"> <sub>Built for the Solana ecosystem — see the true holders</sub> </div> ```
