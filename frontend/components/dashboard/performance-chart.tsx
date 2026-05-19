'use client';

import { useState, useEffect } from "react";
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, CartesianGrid } from "recharts";
import { Trade } from "@/types/api";

export function PerformanceChart({ trades }: { trades: Trade[] }) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  if (!mounted) {
    return (
      <div className="h-72 w-full rounded-md border border-zinc-800 bg-zinc-900 flex items-center justify-center text-xs font-mono text-zinc-500">
        Loading Performance Geometries...
      </div>
    );
  }

  const sortedTrades = [...trades].sort(
    (a, b) => new Date(a.Exit_Time).getTime() - new Date(b.Exit_Time).getTime()
  );

  let cumulativePnL = 0;
  const chartData = sortedTrades.map((trade) => {
    cumulativePnL += trade.PnL_Net;
    return {
      time: new Date(trade.Exit_Time).toLocaleDateString("en-US", { month: "short", day: "2-digit" }),
      pnl: cumulativePnL,
    };
  });

  return (
    <div className="h-72 w-full rounded-md border border-zinc-800 bg-zinc-900 p-4">
      <p className="text-xs font-mono text-zinc-400 mb-4 uppercase tracking-wider">Cumulative Equity Curve (PnL)</p>
      <div className="h-[200px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart data={chartData} margin={{ top: 10, right: 10, left: -10, bottom: 0 }}>
            <defs>
              <linearGradient id="pnlGradient" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor="#10b981" stopOpacity={0.2}/>
                <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
              </linearGradient>
            </defs>
            <CartesianGrid strokeDasharray="3 3" stroke="#27272a" vertical={false} />
            <XAxis dataKey="time" stroke="#71717a" fontSize={10} tickLine={false} />
            <YAxis
              stroke="#71717a"
              fontSize={10}
              tickLine={false}
              tickFormatter={(val) => new Intl.NumberFormat("en-US", { notation: "compact", style: "currency", currency: "USD" }).format(val)}
            />
            <Tooltip
              contentStyle={{ backgroundColor: "#09090b", borderColor: "#27272a" }}
              labelStyle={{ color: "#a1a1aa", fontFamily: "monospace", fontSize: "11px" }}
              itemStyle={{ color: "#10b981", fontFamily: "monospace", fontSize: "12px" }}
              formatter={(value: any) => [new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(value), "Cumulative PnL"]}
            />
            <Area type="monotone" dataKey="pnl" stroke="#10b981" strokeWidth={2} fillOpacity={1} fill="url(#pnlGradient)" />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
