import axios from "axios";
import { KpiCards } from "@/components/dashboard/kpi-cards";
import { BenchmarkMetrics } from "@/components/dashboard/benchmark-metrics";
import { PerformanceChart } from "@/components/dashboard/performance-chart";
import { TradesTable } from "@/components/dashboard/trades-table";
import { ApiResponse } from "@/types/api";

export const dynamic = "force-dynamic";

async function fetchDashboardData(): Promise<ApiResponse> {
  const { data } = await axios.get<ApiResponse>("http://localhost:8000/api/portfolio/metrics", {
    headers: { "Cache-Control": "no-cache" }
  });

  if (!data?.metrics || !Array.isArray(data?.recent_trades)) {
    throw new Error("Invalid payload contract");
  }
  return data;
}

export default async function DashboardPage() {
  const data = await fetchDashboardData();

  return (
    <main className="min-h-screen p-8 bg-zinc-950 text-zinc-50">
      <div className="max-w-7xl mx-auto space-y-8">
        <header className="flex items-center justify-between border-b border-zinc-800 pb-4">
          <div>
            <h1 className="text-3xl font-bold tracking-tight text-zinc-100">MIT-Loop Terminal</h1>
            <p className="text-sm text-zinc-400 mt-1">Live Quantitative Engine</p>
          </div>
          <div className="flex items-center space-x-2">
            <span className="relative flex h-3 w-3">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-3 w-3 bg-emerald-500"></span>
            </span>
            <span className="text-sm text-zinc-400 font-mono">Connected</span>
          </div>
        </header>

        <KpiCards metrics={data.metrics} />

        <BenchmarkMetrics />

        <PerformanceChart trades={data.recent_trades} />

        <TradesTable trades={data.recent_trades} />
      </div>
    </main>
  );
}
