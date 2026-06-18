import os

filepath = '/root/MITLoop/mit-loop-live/main.py'
with open(filepath, 'r') as f:
    lines = f.readlines()

patched = False
with open(filepath, 'w') as f:
    for line in lines:
        # Disable the old S1 Body Strict by removing "body" from the loop target list
        if 'for target_type in ["body", "wick"]:' in line:
            f.write(line.replace('["body", "wick"]', '["wick"]'))
            
        # Inject the new S1 1-Hour Logic right above the S3 4-Hour logic
        elif 'csv_4h_path = os.path.join(HISTORICAL_DATA_DIR, f"{symbol}_4h.csv")' in line and not patched:
            indent = line.split('csv_4h')[0]
            f.write(indent + "# --- NEW S1: 1-HOUR V-SHAPE CAPITULATION ---\n")
            f.write(indent + "csv_1h_path = os.path.join(HISTORICAL_DATA_DIR, f\"{symbol}_1h.csv\")\n")
            f.write(indent + "df_w['sma30'] = df_w['close'].rolling(30).mean()\n")
            f.write(indent + "if pd.notna(df_w['sma30'].iloc[-1]) and current_row['close'] >= df_w['sma30'].iloc[-1] * 0.85 and os.path.exists(csv_1h_path):\n")
            f.write(indent + "    cycle_high = df_w['high'].iloc[-26:].max()\n")
            f.write(indent + "    drawdown = (cycle_high - current_row['close']) / cycle_high\n")
            f.write(indent + "    if drawdown >= 0.15:\n")
            f.write(indent + "        df_1h = pd.read_csv(csv_1h_path)\n")
            f.write(indent + "        df_1h.columns = df_1h.columns.str.lower()\n")
            f.write(indent + "        if not df_1h.empty:\n")
            f.write(indent + "            for c in ['open', 'high', 'low', 'close']: df_1h[c] = pd.to_numeric(df_1h[c], errors='coerce').fillna(0)\n")
            f.write(indent + "            row_1h = df_1h.iloc[-1]\n")
            f.write(indent + "            tail_size_1h = (min(row_1h['open'], row_1h['close']) - row_1h['low']) / row_1h['close']\n")
            f.write(indent + "            if tail_size_1h > 0.03:\n")
            f.write(indent + "                prelim_setups.append({\n")
            f.write(indent + "                    'symbol': symbol, 'strategy': 'Strategy 1: 1H_Hybrid', 'type': '1H_TAIL',\n")
            f.write(indent + "                    'target': float(row_1h['low']), 'age_label': '1H',\n")
            f.write(indent + "                    'csv_close': float(row_1h['close']), 'csv_vol': 0.0,\n")
            f.write(indent + "                    'breakout_vol': 0.0, 'atr': float(daily_atr)\n")
            f.write(indent + "                })\n")
            f.write(indent + "# -------------------------------------------\n")
            f.write(line)
            patched = True
        else:
            f.write(line)

print("✅ Live main.py successfully patched with 1H S1 Logic!")
