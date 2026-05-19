import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { TrendingUp, TrendingDown, Activity, Target } from "lucide-react";
import { Metrics } from "@/types/api";

export function KpiCards({ metrics }: { metrics: Metrics }) {
  const isPnlPositive = metrics.total_pnl >= 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-zinc-400">Total Net PnL</CardTitle>
          {isPnlPositive ? (
            <TrendingUp className="h-4 w-4 text-emerald-500" />
          ) : (
            <TrendingDown className="h-4 w-4 text-red-500" />
          )}
        </CardHeader>
        <CardContent>
          <div className={`text-3xl font-bold font-mono ${isPnlPositive ? "text-emerald-500" : "text-red-500"}`}>
            {new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(metrics.total_pnl)}
          </div>
        </CardContent>
      </Card>

      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-zinc-400">Win Rate</CardTitle>
          <Target className="h-4 w-4 text-zinc-400" />
        </CardHeader>
        <CardContent>
          <div className="text-3xl font-bold font-mono text-zinc-100">
            {metrics.win_rate.toFixed(2)}%
          </div>
        </CardContent>
      </Card>

      <Card className="bg-zinc-900 border-zinc-800">
        <CardHeader className="flex flex-row items-center justify-between pb-2">
          <CardTitle className="text-sm font-medium text-zinc-400">Total Trades</CardTitle>
          <Activity className="h-4 w-4 text-zinc-400" />
        </CardHeader>
        <CardContent>
          <div className="text-3xl font-bold font-mono text-zinc-100">
            {metrics.total_trades}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
