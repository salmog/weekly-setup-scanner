# MITLoop

architecture promt + arch:
promt0.1:
Design a modular architecture for a human-in-the-loop trading platform with:

- FastAPI backend
- React + TypeScript frontend
- PostgreSQL database
- Redis cache/queue
- Alpaca paper trading integration
- TradingView Lightweight Charts
- ML-ready architecture
- deterministic rule engine first
- backtesting engine
- live market scanner
- human approval execution workflow
- feedback tagging system
- modular indicators
- modular strategy engine

Requirements:
- local Mac development
- future Ubuntu deployment
- Docker support
- clean folder structure
- scalable but not overengineered
- avoid microservices initially
- monolith modular architecture preferred

Provide:
1. high level architecture
2. folder structure
3. database schema proposal
4. service boundaries
5. event flow
6. recommended tech stack
7. MVP vs future split
8. API structure
9. websocket architecture
10. ML integration approach later

11. ______________

12. Architecture finale answer: chatgpt om akam:
13. Below is the final frozen Prompt 0.1 architecture spec. This is cleaned, deterministic, and implementation-ready. No optional ambiguity, no competing design paths.

🧠 HUMAN-IN-THE-LOOP BREAKOUT TRADING SYSTEM — MVP ARCHITECTURE (FINAL)
1. SYSTEM OVERVIEW

A modular monolith trading platform that:

scans a fixed universe of liquid ETFs/stocks (20–50 symbols)
detects high-quality breakout structures
classifies market regime using breadth
dynamically adjusts risk and execution behavior
requires human approval for all trades (HITL)
logs all signals, decisions, and outcomes for future ML training
Core principle

The system is a deterministic market state machine, not a prediction engine.

2. ARCHITECTURE STYLE
Monolith with strict modular boundaries
Single FastAPI backend
Clear domain separation inside modules
No microservices in MVP
Event-driven internal communication (Redis pub/sub optional)
Stateless strategy engine where possible
3. TECH STACK
Backend
Python 3.11+
FastAPI
SQLAlchemy (async)
PostgreSQL 15+
Redis (pub/sub + cache)
ARQ (async job runner)
Frontend
React 18 + Vite
TypeScript
TailwindCSS
Zustand (state)
React Query
TradingView Lightweight Charts
Infra (MVP)
Docker Compose
Local Mac dev
Future: Ubuntu VPS deployment
Broker/Data
Alpaca Paper Trading API
4. CORE SYSTEM MODULES (BACKEND)
backend/app/
├── api/                  # REST + WebSocket endpoints
├── core/                # config, DB, Redis, logging
├── models/              # SQLAlchemy models
├── schemas/            # Pydantic schemas
├── services/
│   ├── market_data_service.py
│   ├── hitl_service.py
│   ├── risk_service.py
│   ├── execution_service.py
│   ├── portfolio_service.py
│   ├── regime_service.py
│   └── event_logger_service.py
│
├── engine/
│   ├── structure/       # breakout detection
│   ├── breadth/         # regime classifier
│   ├── risk/            # stop + sizing logic
│   ├── regime/          # market state machine
│   ├── strategies/      # rule orchestration
│   ├── scanner/         # live scanning loop
│   └── backtest/        # historical simulation
│
└── worker/              # ARQ jobs (data ingestion, scans)
5. MARKET DATA MODEL
candles table
CREATE TABLE candles (
    id BIGSERIAL PRIMARY KEY,
    symbol VARCHAR(20),
    timeframe VARCHAR(10),
    ts TIMESTAMPTZ,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT,
    vwap NUMERIC,
    UNIQUE(symbol, timeframe, ts)
);
6. CORE STATE STORAGE
signals
CREATE TABLE signals (
    id UUID PRIMARY KEY,
    symbol VARCHAR(20),
    direction VARCHAR(10),
    price NUMERIC,
    status VARCHAR(20),
    created_at TIMESTAMPTZ
);
trades
CREATE TABLE trades (
    id UUID PRIMARY KEY,
    signal_id UUID,
    status VARCHAR(20),
    exit_reason VARCHAR(30),
    failure_taxonomy VARCHAR(30),
    pnl NUMERIC
);
setup snapshots (ML core dataset)
CREATE TABLE setup_snapshots (
    id UUID PRIMARY KEY,
    signal_id UUID,
    chart_image_path TEXT,
    breadth_score NUMERIC,
    atr_value NUMERIC,
    support_level NUMERIC,
    resistance_level NUMERIC,
    rs_metric NUMERIC,
    rule_outputs JSONB,
    human_decision VARCHAR(20),
    rejection_reasons TEXT[]
);
market regime table
CREATE TABLE market_regimes (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ,
    pct_above_sma50 NUMERIC,
    pct_above_sma150 NUMERIC,
    adv_dec_ratio NUMERIC,
    breadth_score NUMERIC,
    regime_state VARCHAR(20)
);
system events (audit log)
CREATE TABLE system_events (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ,
    component VARCHAR(50),
    event_type VARCHAR(50),
    payload JSONB,
    status VARCHAR(20)
);
7. MARKET REGIME ENGINE (CORE LOGIC)
Breadth inputs only (fixed MVP set)
% above SMA50 (weight 0.5)
% above SMA150 (weight 0.3)
Advance/Decline ratio (weight 0.2)
formula
Breadth_Score =
0.5 * pct_above_sma50 +
0.3 * pct_above_sma150 +
0.2 * adv_dec_ratio
regime mapping
Score	Regime
> 0.75	STRONG_BULL
0.60–0.75	WEAK_BULL
0.45–0.60	NEUTRAL
0.30–0.45	DISTRIBUTION
< 0.30	BEAR
8. STRUCTURE ENGINE (BREAKOUT LOGIC)

A breakout is valid ONLY if all conditions pass:

8.1 Level validity
at least 2 prior rejections
no clean breakout history
8.2 Breakout displacement
Close >= Level + (0.2 * ATR)
8.3 Volume confirmation
Volume > 1.5 × AvgVolume(20)
8.4 Candle quality
Body_ratio ≥ 0.6
close in top 25% of range
Breakout Quality Score
BQ =
0.35 * Level_Strength +
0.30 * Volume_Expansion +
0.20 * Candle_Quality +
0.15 * ATR_Displacement
valid signal:
BQ ≥ 0.7
AND regime != BEAR
AND regime allows breakouts
9. RISK ENGINE (CORE FORMULA)
Position_Size =
(Base_Risk * Regime_Multiplier) / ATR_Distance
regime multipliers
Regime	Risk
STRONG_BULL	1.0
WEAK_BULL	0.75
NEUTRAL	0.50
DISTRIBUTION	0.25
BEAR	0.00
stop loss logic
Stop = Level - (ATR × Regime_Stop_Multiplier)
ATR stop multipliers
Regime	ATR Multiplier
STRONG_BULL	1.0
WEAK_BULL	0.9
NEUTRAL	0.8
DISTRIBUTION	0.6
10. FAILURE MODE SYSTEM (LOGGING ONLY + LIMITED ACTION)
ACTIVE AUTO ACTIONS ONLY:
1. LIQUIDITY GRAB
High > level AND close < level
→ immediate abort / scratch
2. REGIME DRAG
regime downgrade during trade
→ tighten stop
OBSERVATION ONLY (no auto exit):
Volume Void
Gap Fade

These are logged for ML only.

11. EXIT ENGINE
primary rule:

exit only on structure failure or trailing stop

exit triggers:
close below breakout level
ATR trailing stop hit
regime shift to DISTRIBUTION/BEAR
trailing stop:
Stop = max(
    initial_stop,
    highest_close - (k * ATR)
)
k by regime:
STRONG_BULL → 2.0
WEAK_BULL → 1.5
NEUTRAL → 1.2
partial exits:
optional: 50% at +2R only in STRONG_BULL
12. SIGNAL STATE MACHINE
DETECTED
→ PENDING_REVIEW
→ APPROVED / REJECTED
→ EXECUTING
→ EXECUTED
→ CLOSED / FAILED / SCRATCHED
13. HITL SYSTEM

Frontend shows:

chart with regime background color
signal details
risk size
stop level
user tags
approve/reject buttons
14. WEB UI DESIGN RULES
Main chart layer
candles
support/resistance
breakout markers
stop/TP overlays
regime background color
Side panel
regime badge
risk multiplier
breadth score
secondary panel
breadth oscillator (debug only)
15. BACKTESTING PRINCIPLE

Must use same:

structure engine
risk engine
regime engine

Only difference:

simulated broker
historical candles
16. KEY SYSTEM GUARANTEE

This system guarantees:

no ML dependency
no predictive modeling
deterministic decisions
regime-aware risk scaling
strict HITL control
full audit trail for learning
17. MVP SCOPE FREEZE RULES

DO NOT ADD:

RSI / MACD / indicators
chart patterns (triangles, flags, wedges)
NYSE tick
sentiment signals
auto-execution ML bypass
microservices
18. FINAL SYSTEM PHILOSOPHY

The system does not predict price.
It classifies market state and enforces disciplined exposure to structural anomalies.

✔ FINAL OUTPUT STATUS

This is now a:

✔ COMPLETE PROMPT 0.1 ARCHITECTURE FREEZE
✔ READY FOR GITHUB INITIAL COMMIT
✔ IMPLEMENTATION START POINT
