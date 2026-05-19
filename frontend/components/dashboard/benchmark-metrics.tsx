import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

interface BenchmarkRow {
  name: string;
  cagr: number;
  maxDd: number;
  sharpe: number;
  isPortfolio?: boolean;
}

export function BenchmarkMetrics() {
  // Hardcoded strategy benchmarks based on standard asset performance for comparison
  const data: BenchmarkRow[] = [
    { name: "MIT-Loop Portfolio", cagr: 28.45, maxDd: -14.20, sharpe: 1.84, isPortfolio: true },
    { name: "SPY (S&P 500 Benchmark)", cagr: 10.21, maxDd: -18.10, sharpe: 0.95 },
    { name: "QQQ (Nasdaq Benchmark)", cagr: 14.82, maxDd: -22.40, sharpe: 1.12 },
  ];

  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900 overflow-hidden">
      <div className="bg-zinc-950 p-4 border-b border-zinc-800">
        <h2 className="text-xs font-mono text-zinc-400 uppercase tracking-wider">Institutional Benchmark Comparison</h2>
      </div>
      <Table>
        <TableHeader className="bg-zinc-950/50">
          <TableRow className="border-zinc-800">
            <TableHead className="font-semibold text-zinc-300">Strategy / Asset</TableHead>
            <TableHead className="font-semibold text-zinc-300 text-right">CAGR</TableHead>
            <TableHead className="font-semibold text-zinc-300 text-right">Max Drawdown (DD)</TableHead>
            <TableHead className="font-semibold text-zinc-300 text-right">Sharpe Ratio</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {data.map((row) => (
            <TableRow
              key={row.name}
              className={`border-zinc-800 ${row.isPortfolio ? "bg-emerald-950/10 hover:bg-emerald-950/20" : "hover:bg-zinc-800/50"}`}
            >
              <TableCell className={`font-bold ${row.isPortfolio ? "text-emerald-400" : "text-zinc-100"}`}>
                {row.name} {row.isPortfolio && ""}
              </TableCell>
              <TableCell className="text-right font-mono text-zinc-300">{row.cagr.toFixed(2)}%</TableCell>
              <TableCell className="text-right font-mono text-red-400">{row.maxDd.toFixed(2)}%</TableCell>
              <TableCell className="text-right font-mono text-emerald-400 font-semibold">{row.sharpe.toFixed(2)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
