import sqlite3, json, os

db = "output/strategy_state.db"
if not os.path.exists(db):
    print(f"ERROR: {db} not found")
    exit(1)

conn = sqlite3.connect(db)

for t in [
    "strategy_snapshots",
    "trade_log",
    "strategy_insights",
    "multi_tf_snapshots",
    "model_usage_log"
]:
    n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    print(f"{t}: {n}")

orphans = conn.execute(
    "SELECT COUNT(*) FROM trade_log WHERE entry_snapshot_id IS NULL"
).fetchone()[0]
print("orphaned trades:", orphans, "— OK" if orphans == 0 else "FAIL")

bad = conn.execute(
    "SELECT COUNT(*) FROM trade_log WHERE exit_time IS NOT NULL AND realized_pnl IS NULL"
).fetchone()[0]
print("closed trades missing pnl:", bad, "— OK" if bad == 0 else "FAIL")

conn.close()
