export type Timeframe = '1m' | '5m' | '15m' | '1h' | '4h' | '1D' | '1W' | '1M';
export type AssetClass = 'STOCKS' | 'ETF' | 'OPTIONS' | 'FUTURES' | 'CRYPTO' | 'FOREX';
export type MarketRegime = 'BULL_TREND' | 'BEAR_TREND' | 'RANGING' | 'VOLATILE' | 'ALL';
export type ValidationStatus = 'DRAFT' | 'BACKTESTING' | 'PAPER_TRADING' | 'LIVE_APPROVED' | 'DEPRECATED';
export type Environment = 'PAPER' | 'LIVE' | 'BOTH';

export interface PerformanceMetrics {
  winRate: number;
  profitFactor: number;
  maxDrawdown: number;
  sharpeRatio: number;
  totalTrades: number;
  backtestPeriod: string;
}

export interface LiveMetrics {
  currentAllocation: number;
  availableCash: number;
  unrealizedPnL: number;
  realizedPnLToday: number;
  activePositions: number;
  pendingOrders: number;
}

export interface StrategyMetadata {
  strategy_id: string;
  strategy_name: string;
  timeframe: Timeframe[];
  asset_class: AssetClass[];
  execution_engine: string;
  signal_engine: string;
  risk_model: string;
  broker_support: string[];
  leverage_support: boolean;
  options_support: boolean;
  market_regime_compatibility: MarketRegime[];
  live_or_paper: Environment;
  validation_status: ValidationStatus;
  python_logic_reference: string;
  pine_logic_reference: string;
  performance_metrics: PerformanceMetrics;
  live_metrics: LiveMetrics;
}
