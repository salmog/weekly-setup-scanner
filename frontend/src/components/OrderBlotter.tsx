import React from 'react';

interface OrderItem {
  id: string;
  strategy: string;
  symbol: string;
  qty: number;
  side: string;
  status: string;
  time: string;
}

interface Props {
  liveOrderBlotter: OrderItem[];
}

export default function OrderBlotter({ liveOrderBlotter }: Props) {
  return (
    <div className="bg-surface border border-border rounded flex flex-col">
      <div className="p-4 border-b border-border">
        <span className="text-xs font-bold uppercase text-primary">Live Institutional Order Blotter</span>
      </div>
      <div className="overflow-y-auto max-h-64 h-64">
        <table className="w-full text-left border-collapse text-[11px]">
          <thead>
            <tr className="border-b border-border bg-background/20 font-bold text-muted uppercase tracking-wider">
              <th className="p-2.5 pl-4">Order ID</th>
              <th className="p-2.5">Model</th>
              <th className="p-2.5">Asset</th>
              <th className="p-2.5">Side</th>
              <th className="p-2.5 text-end">Shares</th>
              <th className="p-2.5 pr-4 text-end">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-border/40 font-mono font-medium">
            {liveOrderBlotter?.map((order) => (
              <tr key={order.id} className="hover:bg-border/10 transition">
                <td className="p-2.5 pl-4 font-bold text-primary">{order.id}</td>
                <td className="p-2.5 text-muted">{order.strategy}</td>
                <td className="p-2.5 font-bold text-primary">{order.symbol}</td>
                <td className={`p-2.5 font-black ${order.side === 'BUY' ? 'text-success' : 'text-danger'}`}>
                  {order.side}
                </td>
                <td className="p-2.5 text-end text-muted font-bold">{order.qty}</td>
                <td className="p-2.5 pr-4 text-end font-sans font-black">
                  <span className={`text-[9px] px-1.5 py-0.5 rounded border ${
                    order.status === 'FILLED' 
                      ? 'bg-success/10 border-success/30 text-success' 
                      : 'bg-warning/10 border-warning/30 text-warning animate-pulse'
                  }`}>
                    {order.status}
                  </span>
                </td>
              </tr>
            ))}
            {(!liveOrderBlotter || liveOrderBlotter.length === 0) && (
              <tr>
                <td colSpan={6} className="text-center py-12 text-xs text-muted font-sans">
                  No execution tokens registered in live session buffer cache.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
