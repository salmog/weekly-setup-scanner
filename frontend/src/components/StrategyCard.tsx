import React, { useState } from 'react';
import { StrategyMetadata } from '../types/strategy';
import StrategyWorkbench from './StrategyWorkbench';

interface Props {
  strategy: StrategyMetadata;
}

export default function StrategyCard({ strategy }: Props) {
  const [showWorkbench, setShowWorkbench] = useState(false);
  const pnl = strategy.live_metrics.realizedPnLToday;
  const isPositive = pnl >= 0;

  return (
    <>
      <div 
        onClick={() => setShowWorkbench(true)}
        className="bg-surface border border-border rounded flex flex-col justify-between cursor-pointer hover:border-primary/40 transition group"
      >
        <div className="p-5 border-b border-border">
          <div className="flex justify-between items-start">
            <h3 className="text-xs font-extrabold text-primary tracking-tight group-hover:text-muted transition">{strategy.strategy_name}</h3>
            <span className="text-[10px] bg-background text-muted px-2 py-0.5 rounded font-mono border border-border">
              {strategy.strategy_id}
            </span>
          </div>
          
          <div className="flex items-center space-x-2 mt-3 text-[10px] font-bold tracking-wider uppercase text-muted">
            <span>Engine: <span className="text-primary">{strategy.execution_engine}</span></span>
            <span>•</span>
            <span className={strategy.validation_status === 'LIVE_APPROVED' ? 'text-success' : 'text-warning'}>
              {strategy.validation_status.replace('_', ' ')}
            </span>
          </div>
          
          <div className="flex flex-wrap gap-1.5 mt-4">
            {strategy.asset_class.map((asset, i) => (
              <span key={i} className="text-[10px] bg-background border border-border px-2 py-0.5 rounded text-muted font-semibold">
                {asset}
              </span>
            ))}
          </div>
        </div>
        <div className="p-4 bg-background/30 grid grid-cols-2 gap-4 text-center">
          <div className="text-left">
            <div className="text-[10px] text-muted uppercase font-bold tracking-wider">Allocation</div>
            <div className="text-sm font-black text-primary mt-0.5">
              ${strategy.live_metrics.currentAllocation.toLocaleString(undefined, {minimumFractionDigits: 2})}
            </div>
          </div>
          <div className="text-right">
            <div className="text-[10px] text-muted uppercase font-bold tracking-wider">Session PnL</div>
            <div className={`text-sm font-black mt-0.5 ${isPositive ? 'text-success' : 'text-danger'}`}>
              {isPositive ? '+' : ''}${pnl.toLocaleString(undefined, {minimumFractionDigits: 2})}
            </div>
          </div>
        </div>
      </div>

      {showWorkbench && (
        <StrategyWorkbench strategy={strategy} onClose={() => setShowWorkbench(false)} />
      )}
    </>
  );
}
