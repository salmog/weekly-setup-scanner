import React from 'react';

interface RadarItem {
  symbol: string;
  strategy: string;
  target: number;
  dist: number;
  weeks: number;
}

interface Props {
  pendingSetups: RadarItem[];
  commandQuery: string;
}

export default function StrategicRadar({ pendingSetups, commandQuery }: Props) {
  return (
    <div className="xl:col-span-2 bg-surface border border-border rounded flex flex-col">
      <div className="p-4 border-b border-border flex justify-between items-center">
        <span className="text-xs font-bold uppercase text-primary">Live Strategic Pullback Radar</span>
        <span className="text-[10px] text-muted">Agnostic Isolation Verification Rules Enforced</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse">
          <thead>
            <tr className="border-b border-border bg-background/20">
              <th className="p-3 text-[10px] text-muted uppercase font-bold tracking-wider pl-4">Asset</th>
              <th className="p-3 text-[10px] text-muted uppercase font-bold tracking-wider">Strategy Target</th>
              <th className="p-3 text-[10px] text-muted uppercase font-bold tracking-wider">Target Base</th>
              <th className="p-3 text-[10px] text-muted uppercase font-bold tracking-wider">Distance</th>
              <th className="p-3 text-[10px] text-muted uppercase font-bold tracking-wider">Age</th>
              <th className="p-3 text-[10px] text-muted uppercase font-bold tracking-wider pr-4 text-end">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border">
            {pendingSetups?.filter((item) => item.symbol.toLowerCase().includes(commandQuery.toLowerCase())).map((item, i) => (
              <tr key={i} className="hover:bg-border/20 transition">
                <td className="p-3 pl-4 text-xs font-black text-primary">{item.symbol}</td>
                <td className="p-3 text-xs text-muted font-medium">{item.strategy}</td>
                <td className="p-3 text-xs font-mono font-bold text-warning">${item.target.toFixed(2)}</td>
                <td className="p-3 text-xs font-bold text-success">+{item.dist.toFixed(2)}%</td>
                <td className="p-3 text-xs text-muted font-semibold">{item.weeks} W</td>
                <td className="p-3 pr-4 text-end">
                  <span className="text-[10px] bg-background text-muted px-2 py-0.5 rounded font-bold border border-border">
                    AWAITING RETEST
                  </span>
                </td>
              </tr>
            ))}
            {(!pendingSetups || pendingSetups.length === 0) && (
              <tr>
                <td colSpan={6} className="text-center py-6 text-xs text-muted">
                  No pending setups found in API data matrix layers.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
