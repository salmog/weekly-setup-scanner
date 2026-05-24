import React from 'react';
import { StrategyMetadata } from '../types/strategy';

interface Props {
  strategies: StrategyMetadata[];
  systemState: any;
}

export default function InstitutionalAnalytics({ strategies, systemState }: Props) {
  const totalAllocation = strategies.reduce((sum, s) => sum + s.live_metrics.currentAllocation, 0);
  const totalPnL = strategies.reduce((sum, s) => sum + s.live_metrics.realizedPnLToday, 0);
  const totalPositions = strategies.reduce((sum, s) => sum + s.live_metrics.activePositions, 0);
  const totalOrders = strategies.reduce((sum, s) => sum + s.live_metrics.pendingOrders, 0);
  
  const isPnLPositive = totalPnL >= 0;
  const backtestRunning = systemState?.backtest_running || false;
  const backtestProgress = systemState?.backtest_progress || 0;

  const executeFullMatrixBacktest = async () => {
    try {
      await fetch('http://172.237.145.214:8080/api/v2/analytics/backtest', { method: 'POST' });
    } catch (err) {
      console.error("Backtest engine connection failure:", err);
    }
  };

  return (
    <div className="p-6 overflow-y-auto space-y-6 flex-1">
      <div className="text-xs font-bold text-muted uppercase tracking-widest mb-3">Institutional Analytics Engine</div>

      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-surface border border-border rounded p-4">
          <div className="text-[10px] text-muted font-bold tracking-wider uppercase">Aggregated Net Assets</div>
          <div className="text-base font-extrabold mt-1 text-primary">${totalAllocation.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
          <div className="text-[11px] text-muted mt-2">Combined portfolio balance</div>
        </div>
        <div className="bg-surface border border-border rounded p-4">
          <div className="text-[10px] text-muted font-bold tracking-wider uppercase">Live Session PnL</div>
          <div className={`text-base font-extrabold mt-1 ${isPnLPositive ? 'text-success' : 'text-danger'}`}>
            {isPnLPositive ? '+' : ''}${totalPnL.toLocaleString(undefined, { minimumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-muted mt-2">Combined intraday performance</div>
        </div>
        <div className="bg-surface border border-border rounded p-4">
          <div className="text-[10px] text-muted font-bold tracking-wider uppercase">Market Position Exposure</div>
          <div className="text-base font-extrabold mt-1 text-warning">{totalPositions} Active</div>
          <div className="text-[11px] text-muted mt-2">Risk-allocated inventory slices</div>
        </div>
        <div className="bg-surface border border-border rounded p-4">
          <div className="text-[10px] text-muted font-bold tracking-wider uppercase">Pending Order Gateways</div>
          <div className="text-base font-extrabold mt-1 text-primary">{totalOrders} En Route</div>
          <div className="text-[11px] text-muted mt-2">Active routing pipeline instances</div>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <div className="xl:col-span-2 bg-surface border border-border rounded p-5 space-y-6">
          <h3 className="text-xs font-extrabold text-primary tracking-tight">Historical Simulation Performance Matrix</h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-medium border-collapse">
              <thead>
                <tr className="border-b border-border bg-background/20 text-muted text-[10px] uppercase font-bold tracking-wider">
                  <th className="p-3 pl-4">Strategy</th>
                  <th className="p-3">Sample Period</th>
                  <th className="p-3">Win Rate</th>
                  <th className="p-3">Profit Factor</th>
                  <th className="p-3">Max DD</th>
                  <th className="p-3">Sharpe</th>
                  <th className="p-3 pr-4 text-end">Total Trades</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/60">
                {strategies.map((strat) => (
                  <tr key={strat.strategy_id} className="hover:bg-border/10 transition">
                    <td className="p-3 pl-4 font-black text-primary">{strat.strategy_name}</td>
                    <td className="p-3 font-mono text-muted">{strat.performance_metrics?.backtestPeriod}</td>
                    <td className="p-3 font-mono font-bold text-success">{strat.performance_metrics?.winRate?.toFixed(1)}%</td>
                    <td className="p-3 font-mono text-primary font-bold">x{strat.performance_metrics?.profitFactor?.toFixed(2)}</td>
                    <td className="p-3 font-mono text-danger font-semibold">-{strat.performance_metrics?.maxDrawdown?.toFixed(1)}%</td>
                    <td className="p-3 font-mono text-warning font-bold">{strat.performance_metrics?.sharpeRatio?.toFixed(2)}</td>
                    <td className="p-3 pr-4 text-end font-mono text-muted font-bold">{strat.performance_metrics?.totalTrades}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="bg-surface border border-border rounded p-5 flex flex-col justify-between">
          <div>
            <h3 className="text-xs font-extrabold text-primary tracking-tight mb-4">Monte Carlo Simulation Engine</h3>
            <div className="space-y-3.5">
              <div className="flex justify-between items-center border-b border-border/50 pb-2">
                <span className="text-xs text-muted font-medium">Confidence Interval Target</span>
                <span className="text-xs font-bold text-primary">99.9%</span>
              </div>
              <div className="flex justify-between items-center border-b border-border/50 pb-2">
                <span className="text-xs text-muted font-medium">Calculation Iterations</span>
                <span className="text-xs font-bold text-primary">10,000 Path Permutations</span>
              </div>
              <div className="flex justify-between items-center border-b border-border/50 pb-2">
                <span className="text-xs text-muted font-medium">Risk-Free Rate Baseline</span>
                <span className="text-xs font-bold text-primary">4.21% (US10Y)</span>
              </div>
            </div>
          </div>

          <div className="mt-6 space-y-3">
            {backtestRunning && (
              <div className="space-y-1.5">
                <div className="flex justify-between text-[10px] font-mono font-black text-warning uppercase">
                  <span>Running Matrix Estimations...</span>
                  <span>{backtestProgress}%</span>
                </div>
                <div className="w-full bg-background border border-border h-2 rounded-full overflow-hidden">
                  <div className="bg-warning h-full transition-all duration-300" style={{ width: `${backtestProgress}%` }} />
                </div>
              </div>
            )}
            <button 
              onClick={executeFullMatrixBacktest}
              disabled={backtestRunning}
              className={`w-full text-xs font-black uppercase tracking-wider py-3 rounded border transition cursor-pointer ${
                backtestRunning 
                  ? 'bg-background border-border text-muted opacity-50' 
                  : 'bg-background border-border text-primary hover:bg-border/30 hover:border-primary/50'
              }`}
            >
              {backtestRunning ? 'Processing Engine Computations...' : '⚡ Execute Full Matrix Backtest'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
