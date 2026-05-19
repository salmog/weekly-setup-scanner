import os

import pandas as pd
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="MIT-Loop Quant API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"status": "online", "message": "Quant Engine API is running"}


@app.get("/api/portfolio/metrics")
def get_portfolio_metrics():
    """Serves the latest portfolio simulation metrics to the UI."""
    csv_path = "/code/portfolio_trades_export.csv"

    if not os.path.exists(csv_path):
        return {"error": "Trade data not found. Run simulation first."}

    df = pd.read_csv(csv_path)

    total_trades = len(df)
    wins = len(df[df["PnL_Net"] > 0])
    win_rate = (wins / total_trades) * 100 if total_trades > 0 else 0
    total_pnl = df["PnL_Net"].sum()

    # Get last 15 trades for the dashboard table
    recent_trades = df.tail(15).fillna("").to_dict(orient="records")

    return {
        "metrics": {
            "total_trades": total_trades,
            "win_rate": round(win_rate, 2),
            "total_pnl": round(total_pnl, 2),
        },
        "recent_trades": recent_trades,
    }
