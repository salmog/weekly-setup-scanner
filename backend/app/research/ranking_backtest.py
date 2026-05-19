import pandas as pd


def run_ranked_portfolio(trades: pd.DataFrame, top_n: int = 5, score_column: str = "ml_score"):
    if trades.empty:
        return pd.DataFrame()

    trades = trades.copy()
    trades["entry_date"] = pd.to_datetime(trades["entry_time"]).dt.date

    selected = []
    grouped = trades.groupby("entry_date")

    for _, day_trades in grouped:
        ranked = day_trades.sort_values(by=score_column, ascending=False)
        chosen = ranked.head(top_n)
        selected.append(chosen)

    if not selected:
        return pd.DataFrame()

    return pd.concat(selected).reset_index(drop=True)
