export interface Trade {
  Symbol: string;
  Direction: string;
  Entry_Time: string;
  Exit_Time: string;
  Entry_Price: number;
  Exit_Price: number;
  PnL_Net: number;
  R_Multiple: number;
  Exit_Reason: string;
  ML_Score: number;
  SPY_Dist: number;
}

export interface Metrics {
  total_pnl: number;
  win_rate: number;
  total_trades: number;
}

export interface ApiResponse {
  metrics: Metrics;
  recent_trades: Trade[];
}
