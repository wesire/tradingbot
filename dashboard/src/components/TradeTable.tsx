import type { Trade } from "@/api/client"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"

interface TradeTableProps {
  trades: Trade[];
  loading?: boolean;
  /** Explicit data source to display. Falls back to the first trade's source field. */
  source?: 'exchange' | 'alerts';
}

export function TradeTable({ trades, loading = false, source }: TradeTableProps) {
  // Prefer the explicit source prop; fall back to inspecting trade entries.
  const dataSource: 'exchange' | 'alerts' | undefined =
    source ?? (trades.length > 0 ? trades[0].source : undefined)

  return (
    <div className="space-y-2">
      {dataSource && (
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span>Data source:</span>
          {dataSource === 'exchange' ? (
            <Badge variant="success" className="text-xs">Live Exchange</Badge>
          ) : (
            <Badge variant="secondary" className="text-xs">Alert Storage (cached)</Badge>
          )}
        </div>
      )}
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Time</TableHead>
            <TableHead>Symbol</TableHead>
            <TableHead>Side</TableHead>
            <TableHead>Size</TableHead>
            <TableHead>Price</TableHead>
            <TableHead>PnL</TableHead>
            <TableHead>Status</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {loading ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-muted-foreground">
                Loading trades…
              </TableCell>
            </TableRow>
          ) : trades.length === 0 ? (
            <TableRow>
              <TableCell colSpan={7} className="text-center text-muted-foreground py-6">
                No trades yet — executed trades will appear here once the bot is active.
              </TableCell>
            </TableRow>
          ) : (
            trades.map((trade) => (
              <TableRow key={trade.id}>
                <TableCell className="font-mono text-sm">
                  {new Date(trade.timestamp).toLocaleString()}
                </TableCell>
                <TableCell className="font-medium">{trade.symbol}</TableCell>
                <TableCell>
                  <Badge variant={trade.side === 'buy' ? 'success' : 'destructive'}>
                    {trade.side.toUpperCase()}
                  </Badge>
                </TableCell>
                <TableCell>{trade.size.toFixed(4)}</TableCell>
                <TableCell>${trade.price.toFixed(2)}</TableCell>
                <TableCell>
                  {trade.pnl !== undefined ? (
                    <span className={trade.pnl >= 0 ? 'text-green-500' : 'text-red-500'}>
                      ${trade.pnl.toFixed(2)}
                    </span>
                  ) : (
                    '-'
                  )}
                </TableCell>
                <TableCell>
                  <Badge variant={trade.status === 'open' ? 'warning' : 'secondary'}>
                    {trade.status}
                  </Badge>
                </TableCell>
              </TableRow>
            ))
          )}
        </TableBody>
      </Table>
    </div>
  )
}
