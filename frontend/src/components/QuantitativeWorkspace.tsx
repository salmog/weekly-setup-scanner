import React from 'react';
import StrategyCard from './StrategyCard';
import StrategicRadar from './StrategicRadar';
import AuditLog from './AuditLog';
import RiskController from './RiskController';
import { StrategyMetadata } from '../types/strategy';

interface Props {
  systemState: any;
  strategies: StrategyMetadata[];
  totalAllocation: number;
  commandQuery: string;
  setCommandQuery: (val: string) => void;
}

export default function QuantitativeWorkspace({ systemState, strategies, totalAllocation, commandQuery, setCommandQuery }: Props) {
  return (
    <div className="p-6 overflow-y-auto space-y-6 flex-1">
      {/* KPI Widgets */}
      <section className="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div className="bg-surface border border-border rounded p-4">
          <div className="text-[10px] text-muted font-bold tracking-wider uppercase">Global Regime Matrix</div>
          <div className="text-base font-extrabold mt-1 text-primary">BULLISH CONSOLIDATION</div>
          <div className="text-[11px] text-muted mt-2 flex items-center space-x-1"><span className="text-success font-bold">EMA20 &gt; SMA50</span><span>• Weekly Slope Up</span></div>
        </div>
        <div className="bg-surface border border-border rounded p-4">
          <div className="text-[10px] text-muted font-bold tracking-wider uppercase">Active Engine Scan</div>
          <div className="text-sm font-extrabold mt-1 text-primary">{systemState?.last_scan || "Never"}</div>
          <div className="text-[11px] text-muted mt-2">Local IBKR Pipeline</div>
        </div>
        <div className="bg-surface border border-border rounded p-4">
          <div className="text-[10px] text-muted font-bold tracking-wider uppercase">Core Scanner Status</div>
          <div className="text-sm font-extrabold mt-1 text-success">● {systemState?.scanner_status || "OPERATIONAL"}</div>
          <div className="text-[11px] text-muted mt-2">Scheduled: 16:15 US/Eastern</div>
        </div>
        <div className="bg-surface border border-border rounded p-4">
          <div className="text-[10px] text-muted font-bold tracking-wider uppercase">Total Asset Allocation</div>
          <div className="text-base font-extrabold mt-1 text-primary">${totalAllocation.toLocaleString(undefined, {minimumFractionDigits: 2})}</div>
          <div className="text-[11px] text-muted mt-2 text-success font-bold">Multi-Account Total</div>
        </div>
      </section>

      {/* Strategy Profiles */}
      <section>
        <div className="text-xs font-bold text-muted uppercase tracking-widest mb-3">Live Strategy Profiles</div>
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {strategies.map((strat) => (
            <StrategyCard key={strat.strategy_id} strategy={strat} />
          ))}
        </div>
      </section>

      {/* Orchestrated Lower Dashboard Grid */}
      <section className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        <StrategicRadar 
          pendingSetups={systemState?.pending_setups} 
          commandQuery={commandQuery} 
        />

        <div className="space-y-4">
          <RiskController 
            systemState={systemState} 
          />
          <AuditLog 
            recentActions={systemState?.recent_actions} 
          />
        </div>
      </section>
    </div>
  );
}
