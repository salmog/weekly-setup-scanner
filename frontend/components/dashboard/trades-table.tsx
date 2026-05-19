import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Trade } from "@/types/api";

const formatCurrency = (val: number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" }).format(val);
const formatDate = (dateStr: string) => new Intl.DateTimeFormat("en-US", { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(dateStr));

export function TradesTable({ trades }: { trades: Trade[] }) {
  return (
    <div className="rounded-md border border-zinc-800 bg-zinc-900 overflow-hidden">
      <Table>
        <TableHeader className="bg-zinc-950">
          <TableRow className="border-zinc-800">
            <TableHead className="font-semibold text-zinc-300">Symbol</TableHead>
            <TableHead className="font-semibold text-zinc-300">Dir</TableHead>
            <TableHead className="font-semibold text-zinc-300">Entry / Exit Time</TableHead>
            <TableHead className="font-semibold text-zinc-300 text-right">Entry / Exit Price</TableHead>
            <TableHead className="font-semibold text-zinc-300 text-right">PnL</TableHead>
            <TableHead className="font-semibold text-zinc-300 text-center">ML Score</TableHead>
            <TableHead className="font-semibold text-zinc-300">Reason</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {trades.map((trade, i) => {
            const isProfit = trade.PnL_Net >= 0;
            return (
              <TableRow key={`${trade.Symbol}-${i}`} className="border-zinc-800 hover:bg-zinc-800/50">
                <TableCell className="font-bold text-zinc-100">{trade.Symbol}</TableCell>
                <TableCell>
                  <Badge variant="outline" className={trade.Direction === "LONG" ? "text-emerald-400 border-emerald-900" : "text-red-400 border-red-900"}>
                    {trade.Direction}
                  </Badge>
                </TableCell>
                <TableCell className="text-zinc-400 text-xs font-mono">
                  <div>{formatDate(trade.Entry_Time)}</div>
                  <div>{formatDate(trade.Exit_Time)}</div>
                </TableCell>
                <TableCell className="text-right font-mono text-zinc-300 text-xs">
                  <div>{formatCurrency(trade.Entry_Price)}</div>
                  <div>{formatCurrency(trade.Exit_Price)}</div>
                </TableCell>
                <TableCell className={`text-right font-mono font-bold ${isProfit ? "text-emerald-500" : "text-red-500"}`}>
                  {isProfit ? "+" : ""}{formatCurrency(trade.PnL_Net)}
                </TableCell>
                <TableCell className="text-center font-mono text-zinc-300">{trade.ML_Score.toFixed(4)}</TableCell>
                <TableCell>
                  <Badge variant="outline" className="bg-zinc-950 text-zinc-400 border-zinc-700">
                    {trade.Exit_Reason}
                  </Badge>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </div>
  );
}
