import React from 'react';

interface Props {
  systemState: any;
}

export default function RiskController({ systemState }: Props) {

  const handleStrategyRiskTune = async (stratKey: string, val: number) => {
    try {
      await fetch('http://172.237.145.214:8080/api/v2/risk/strategy-tune', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_key: stratKey, risk_pct: val })
      });
    } catch (err) {
      console.error("Strategy risk sync failure:", err);
    }
  };

  const handleLiquidate = async (stratKey: string, symbol: string) => {
    try {
      await fetch('http://172.237.145.214:8080/api/v2/risk/liquidate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ strategy_key: stratKey, symbol: symbol })
      });
    } catch (err) {
      console.error("Liquidation failure:", err);
    }
  };

  return (
    <div className="bg-surface border border-border rounded p-4 space-y-4">
      <div className="border-b border-border/40 pb-2">
        <span className="text-xs font-bold uppercase text-primary">Model Isolated Risk Tuners</span>
      </div>

      <div className="space-y-4">
        {Object.entries(systemState?.accounts || {}).map(([stratKey, acc]: [string, any]) => {
          const currentRisk = acc?.current_risk_pct ?? 1.0;
          return (
            <div key={stratKey} className="space-y-1.5 bg-background/40 border border-border/40 p-2.5 rounded">
              <div className="flex justify-between items-center text-[10px] font-bold uppercase tracking-tight">
                <span className="text-primary">{stratKey.replace('_', ' // ')}</span>
                <span className="text-warning font-mono">{currentRisk.toFixed(1)}% Allocation</span>
              </div>
              <input 
                type="range" min="0.1" max="5.0" step="0.1"
                value={currentRisk} 
                onChange={(e) => handleStrategyRiskTune(stratKey, parseFloat(e.target.value))}
                className="w-full accent-primary h-1 bg-background border border-border rounded-lg appearance-none cursor-pointer" 
              />
            </div>
          );
        })}
      </div>

      <div className="space-y-2 border-t border-border/40 pt-3">
        <label className="text-[10px] text-muted font-bold uppercase block">Active Inventory Ledger Slices</label>
        <div className="space-y-1.5 max-h-36 overflow-y-auto pr-1">
          {Object.entries(systemState?.accounts || {}).flatMap(([stratKey, acc]: [string, any]) => 
            (acc?.open_positions || []).map((pos: any, idx: number) => (
              <div key={`${stratKey}-${idx}`} className="bg-background border border-border/60 rounded p-2 flex items-center justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-xs font-black text-primary">{pos.symbol}</span>
                    <span className="text-[9px] font-mono text-muted">({stratKey.split('_')[0]})</span>
                  </div>
                  <div className="text-[10px] text-muted font-mono mt-0.5">
                    {pos.qty} Share @ ${pos.entry?.toFixed(2)}
                  </div>
                </div>
                <div className="flex items-center space-x-3 font-mono text-xs">
                  <span className={pos.pnl >= 0 ? "text-success font-bold" : "text-danger font-bold"}>
                    {pos.pnl >= 0 ? '+' : ''}${pos.pnl?.toFixed(2)}
                  </span>
                  <button 
                    onClick={() => handleLiquidate(stratKey, pos.symbol)}
                    className="bg-surface border border-danger/30 text-danger hover:bg-danger hover:text-white text-[9px] font-black px-1.5 py-0.5 rounded transition cursor-pointer"
                  >
                    MKT CLOSE
                  </button>
                </div>
              </div>
            ))
          )}
          {(!systemState?.accounts || Object.values(systemState?.accounts || {}).every((acc: any) => !acc?.open_positions?.length)) && (
            <div className="text-muted text-[11px] text-center py-2 font-mono">No active position inventory logs.</div>
          )}
        </div>
      </div>
    </div>
  );
}
