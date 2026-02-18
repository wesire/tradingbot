import type { Trade } from "@/api/client"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { Badge } from "@/components/ui/badge"

interface TradeTableProps {
  trades: Trade[];
}

export function TradeTable({ trades }: TradeTableProps) {
  return (
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
        {trades.length === 0 ? (
          <TableRow>
            <TableCell colSpan={7} className="text-center text-muted-foreground">
              No trades yet
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
  )
}
