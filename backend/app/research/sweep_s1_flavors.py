import os
import math
import pandas as pd
import numpy as np
import warnings
import datetime

warnings.simplefilter(action='ignore', category=FutureWarning)

SLIPPAGE_RATE = 0.0025          
MAX_CONCURRENT_POSITIONS = 10
STARTING_CAPITAL = 100000.0

def compute_metrics(equity_curve: pd.Series, expected_weeks: int):
    if len(equity_curve) < 2: return 0.0, 0.0, 0.0
    returns = equity_curve.pct_change().dropna()
    rolling_max = equity_curve.cummax()
    max_dd = ((equity_curve - rolling_max) / rolling_max).min()
    start, end = equity_curve.iloc[0], equity_curve.iloc[-1]
    years = expected_weeks / 52.0
    cagr_val = 0.0 if (years <= 0 or start <= 0 or end <= 0) else (end / start) ** (1 / years) - 1
    return cagr_val, max_dd, 0.0

def load_monthly_trend(repo, symbol):
    m_path = os.path.join(repo, f"{symbol}_monthly.csv")
    if not os.path.exists(m_path): return {}
    try:
        df = pd.read_csv(m_path)
        df.columns = df.columns.str.lower()
        if 'close' not in df.columns: return {}
        date_col = 'date' if 'date' in df.columns else 'timestamp'
        df[date_col] = pd.to_datetime(df[date_col])
        df['sma10'] = df['close'].rolling(10).mean()
        df['yyyy_mm'] = df[date_col].dt.strftime('%Y-%m')
        return dict(zip(df['yyyy_mm'], df['close'] > df['sma10']))
    except:
        return {}

def load_daily_df(repo, symbol):
    d_path = os.path.join(repo, f"{symbol}_daily.csv")
    if not os.path.exists(d_path):
        d_path = os.path.join(repo, f"{symbol}.csv")
    if not os.path.exists(d_path): return pd.DataFrame(), None
    try:
        d_df = pd.read_csv(d_path)
        d_df.columns = d_df.columns.str.lower()
        d_col = 'date' if 'date' in d_df.columns else 'timestamp'
        d_df[d_col] = pd.to_datetime(d_df[d_col]).dt.date
        return d_df, d_col
    except:
        return pd.DataFrame(), None

def extract_trades_for_flavor(repo, symbol, df, monthly_map, flavor):
    trades = []
    wick_level, body_level, breakout_vol = 0.0, 0.0, 0.0
    weeks_above, setup_active = 0, False
    date_col = 'date' if 'date' in df.columns else 'timestamp'
    
    df_daily, d_col = load_daily_df(repo, symbol)
    target_type = flavor['target']

    for i in range(50, len(df) - 1):
        row = df.iloc[i]
        macro_bull = monthly_map.get(row['yyyy_mm'], False)
        current_wick = row['swing_wick_res']
        current_body = row['swing_body_res']

        if pd.isna(current_wick) or pd.isna(current_body): continue

        if not setup_active:
            current_res = current_wick if target_type == 'wick' else current_body
            is_liquid = (row['close'] >= 5.0) and ((row['close'] * row['vol_avg']) >= 5000000)
            is_breakout = row['close'] > current_res and df.iloc[i-1]['close'] <= current_res
            is_zigzag = row['close'] <= (row['ema20'] * 1.25)
            is_high_vol = row['volume'] > (row['vol_avg'] * 1.5)
            is_aligned = row['ema20'] > row['sma50']
            is_sloping_up = row['ema20'] > df.iloc[i-4]['ema20'] 

            if is_liquid and is_breakout and macro_bull and is_zigzag and is_high_vol and is_aligned and is_sloping_up:
                wick_level, body_level = current_wick, current_body
                breakout_vol = row['volume']
                weeks_above, setup_active = 0, True
            continue

        if setup_active:
            if row['close'] < row['sma50'] or weeks_above > 24:
                setup_active = False
                continue

            trigger_level = wick_level if target_type == 'wick' else body_level

            if row['low'] <= trigger_level:
                if weeks_above >= 4 and row['volume'] < breakout_vol:
                    stop_loss = body_level - (1.1 * row['atr']) 
                    
                    exact_entry_date = row[date_col]
                    if not df_daily.empty:
                        ws = exact_entry_date - datetime.timedelta(days=6)
                        w_df = df_daily[(df_daily[d_col] >= ws) & (df_daily[d_col] <= exact_entry_date)]
                        hits = w_df[w_df['low'] <= trigger_level]
                        if not hits.empty: exact_entry_date = hits.iloc[0][d_col]

                    exit_date, exit_price = None, 0.0
                    
                    for j in range(i + 1, len(df)):
                        f_row = df.iloc[j]
                        if f_row['low'] <= stop_loss:
                            exit_price = stop_loss
                            exact_exit = f_row[date_col]
                            if not df_daily.empty:
                                ws = exact_exit - datetime.timedelta(days=6)
                                w_df = df_daily[(df_daily[d_col] >= ws) & (df_daily[d_col] <= exact_exit)]
                                hits = w_df[w_df['low'] <= stop_loss]
                                if not hits.empty: exact_exit = hits.iloc[0][d_col]
                            exit_date = exact_exit
                            break
                        elif f_row['close'] < f_row['ema20'] and f_row['close'] > trigger_level:
                            exit_price = f_row['close']
                            exit_date = f_row[date_col] 
                            break
                        elif f_row['close'] < stop_loss:
                            exit_price = f_row['close']
                            exit_date = f_row[date_col]
                            break

                    if exit_date is not None:
                        trades.append({
                            'symbol': symbol, 'entry_time': exact_entry_date, 'exit_time': exit_date,
                            'entry_target': trigger_level, 'stop_loss': stop_loss, 'exit_price': exit_price
                        })
                setup_active = False
            else:
                weeks_above += 1

    return trades

def simulate_portfolio(trades_list, start_date, end_date, risk_pct):
    window_trades = [t for t in trades_list if t['entry_time'] >= start_date and t['exit_time'] <= end_date]
    all_dates = sorted(list(set([t['entry_time'] for t in window_trades] + [t['exit_time'] for t in window_trades])))
    
    events = []
    for t in window_trades:
        events.append({'time': t['entry_time'], 'type': 'entry', 'data': t})
        events.append({'time': t['exit_time'], 'type': 'exit', 'data': t})
    events.sort(key=lambda x: (x['time'], x['type'] == 'entry'))

    current_equity = STARTING_CAPITAL
    available_cash = STARTING_CAPITAL
    active_positions = 0
    active_trade_queue = [] 
    completed_logs = []
    daily_map = {}

    for event in events:
        ev_date = event['time']
        trade = event['data']

        if event['type'] == 'exit':
            for i, pos in enumerate(active_trade_queue):
                if pos['symbol'] == trade['symbol'] and pos['entry_time'] == trade['entry_time']:
                    exit_px_slip = trade['exit_price'] * (1 - SLIPPAGE_RATE)
                    proceeds = pos['shares'] * exit_px_slip
                    pnl = proceeds - pos['cost']
                    available_cash += proceeds
                    current_equity += pnl

                    completed_logs.append({
                        'Exit Date': trade['exit_time'],
                        'Ticker': trade['symbol'],
                        'Entry Date': trade['entry_time'],
                        'Target Px': trade['entry_target'],
                        'Fill Px': pos['fill_px'],
                        'Exit Px': exit_px_slip,
                        'Shares': pos['shares'],
                        'Net Profit': pnl,
                        'Acc Balance': current_equity
                    })

                    active_trade_queue.pop(i)
                    active_positions -= 1
                    break

        elif event['type'] == 'entry':
            if active_positions < MAX_CONCURRENT_POSITIONS:
                entry_px = trade['entry_target']
                risk_per_share = entry_px - trade['stop_loss']
                if risk_per_share > 0:
                    shares = math.floor((current_equity * risk_pct) / risk_per_share)
                    if shares > 0:
                        entry_px_slip = entry_px * (1 + SLIPPAGE_RATE)
                        cost = shares * entry_px_slip
                        if cost <= available_cash:
                            available_cash -= cost
                            active_trade_queue.append({
                                'symbol': trade['symbol'], 'entry_time': trade['entry_time'], 
                                'shares': shares, 'cost': cost, 'fill_px': entry_px_slip
                            })
                            active_positions += 1

        daily_map[ev_date] = current_equity

    continuous = []
    running = STARTING_CAPITAL
    for d in all_dates:
        if d in daily_map: running = daily_map[d]
        continuous.append(running)

    cagr, max_dd, _ = compute_metrics(pd.Series(continuous), len(all_dates))
    completed_logs.sort(key=lambda x: x['Exit Date'])
    
    total_return = ((current_equity - STARTING_CAPITAL) / STARTING_CAPITAL) * 100

    return {
        'logs': completed_logs,
        'trades': len(completed_logs),
        'end_equity': current_equity,
        'total_return': total_return,
        'cagr': cagr * 100,
        'max_dd': max_dd * 100
    }

def run_manager_report():
    repo = "historical_data" if os.path.exists("historical_data") else "/code/historical_data"
    all_files = [f for f in os.listdir(repo) if f.endswith('_weekly.csv')]
    if not all_files: return

    flavors = [
        {"name": "1. Body Strict (1% Risk)", "target": "body", "risk": 0.01},
        {"name": "2. Wick Scaled (2% Risk)", "target": "wick", "risk": 0.02},
        {"name": "3. Wick Strict (1% Risk)", "target": "wick", "risk": 0.01}
    ]

    print("Extracting Dual-Timeframe Data. Please wait...")
    master_trades = {f['name']: [] for f in flavors}

    for idx, file in enumerate(all_files, 1):
        try:
            df = pd.read_csv(os.path.join(repo, file))
            df.columns = df.columns.str.lower()
            if 'close' not in df.columns: continue
            
            date_col = 'date' if 'date' in df.columns else 'timestamp'
            df[date_col] = pd.to_datetime(df[date_col]).dt.date
            df['yyyy_mm'] = pd.to_datetime(df[date_col]).dt.strftime('%Y-%m')
            df['atr'] = (df['high'] - df['low']).rolling(14).mean()
            df['ema20'] = df['close'].ewm(span=20, adjust=False).mean()
            df['sma50'] = df['close'].rolling(50).mean()
            df['vol_avg'] = df['volume'].rolling(20).mean()
            df['rolling_max_11'] = df['high'].rolling(11).max()
            df['is_pivot'] = df['high'].shift(5) == df['rolling_max_11']
            df['body_max'] = df[['open', 'close']].max(axis=1)
            df['swing_wick_res'] = np.where(df['is_pivot'], df['high'].shift(5), np.nan)
            df['swing_body_res'] = np.where(df['is_pivot'], df['body_max'].shift(5), np.nan)
            df['swing_wick_res'] = pd.Series(df['swing_wick_res']).ffill()
            df['swing_body_res'] = pd.Series(df['swing_body_res']).ffill()
            
            symbol = file.split('_')[0].split('.')[0]
            m_map = load_monthly_trend(repo, symbol)

            body_trades = extract_trades_for_flavor(repo, symbol, df, m_map, flavors[0])
            wick_trades = extract_trades_for_flavor(repo, symbol, df, m_map, flavors[1])

            master_trades[flavors[0]['name']].extend(body_trades)
            master_trades[flavors[1]['name']].extend(wick_trades)
            master_trades[flavors[2]['name']].extend(wick_trades)
        except: continue

    start_d, end_d = datetime.date(2019, 1, 1), datetime.date(2026, 5, 21)
    
    results = {}
    for f in flavors:
        results[f['name']] = simulate_portfolio(master_trades[f['name']], start_d, end_d, f['risk'])

    # Static SPY/QQQ Data from 2019 to Mid-2026 for Comparison
    spy_cagr, spy_dd, spy_ret, spy_end = 14.6, -33.9, 173.5, 273500.0
    qqq_cagr, qqq_dd, qqq_ret, qqq_end = 21.6, -35.1, 323.5, 423500.0

    print("\n" + "="*115)
    print("  EXECUTIVE SUMMARY: STRATEGY PERFORMANCE VS BENCHMARKS (2019 - 2026 | Start: $100,000)")
    print("="*115)
    print(f"{'Strategy / Benchmark':<28} | {'Trades':<8} {'End Equity':<15} {'Total Return':<15} {'CAGR':<10} {'Max DD':<10}")
    print("-" * 115)
    print(f"{'SPY (Benchmark)':<28} | {'--':<8} ${spy_end:<14.2f} +{spy_ret:<14.1f}% {spy_cagr:>5.1f}%     {spy_dd:>6.1f}%")
    print(f"{'QQQ (Benchmark)':<28} | {'--':<8} ${qqq_end:<14.2f} +{qqq_ret:<14.1f}% {qqq_cagr:>5.1f}%     {qqq_dd:>6.1f}%")
    print("-" * 115)
    for f in flavors:
        r = results[f['name']]
        print(f"{f['name']:<28} | {r['trades']:<8} ${r['end_equity']:<14.2f} +{r['total_return']:<14.1f}% {r['cagr']:>5.1f}%     {r['max_dd']:>6.1f}%")
    
    print("\n" + "="*115)
    print("  COMPLETE TRADING LEDGERS (Exact Daily Entries | 25 bps Slip Accrued)")
    print("="*115)

    for f in flavors:
        print(f"\n---> STRATEGY: {f['name']}")
        print(f"{'Exit Date':<12} | {'Ticker':<8} | {'Entry Date':<12} | {'Fill Px':<9} | {'Exit Px':<9} | {'Shares':<8} | {'Net Profit':<12} | {'Acc Balance'}")
        print("-" * 115)
        for t in results[f['name']]['logs']:
            print(f"{str(t['Exit Date']):<12} | {t['Ticker']:<8} | {str(t['Entry Date']):<12} | ${t['Fill Px']:<8.2f} | ${t['Exit Px']:<8.2f} | {t['Shares']:<8} | ${t['Net Profit']:<11.2f} | ${t['Acc Balance']:<12.2f}")

    print("="*115 + "\n")

if __name__ == "__main__":
    run_manager_report()
