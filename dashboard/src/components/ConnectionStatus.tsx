import type { ConnectionState } from '@/hooks/useWebSocket'
import { cn } from '@/lib/utils'

interface ConnectionStatusProps {
  connectionState: ConnectionState
  lastUpdate: Date | null
  activeSubscriptions: string[]
}

/**
 * Small nav-bar indicator showing WebSocket connection state,
 * last data timestamp, and number of active channel subscriptions.
 */
export function ConnectionStatus({
  connectionState,
  lastUpdate,
  activeSubscriptions,
}: ConnectionStatusProps) {
  const dotColor =
    connectionState === 'connected'
      ? 'bg-green-500'
      : connectionState === 'reconnecting'
        ? 'bg-yellow-500 animate-pulse'
        : 'bg-red-500'

  const label =
    connectionState === 'connected'
      ? 'Live'
      : connectionState === 'reconnecting'
        ? 'Reconnecting…'
        : 'Offline (polling)'

  const labelColor =
    connectionState === 'connected'
      ? 'text-green-500'
      : connectionState === 'reconnecting'
        ? 'text-yellow-500'
        : 'text-red-500'

  const title = [
    `State: ${connectionState}`,
    lastUpdate ? `Last update: ${lastUpdate.toLocaleTimeString()}` : 'No data yet',
    `Subscriptions: ${activeSubscriptions.join(', ') || 'none'}`,
  ].join('\n')

  return (
    <div
      className="flex items-center gap-1.5 text-xs cursor-default"
      title={title}
    >
      <span
        className={cn('h-2 w-2 rounded-full shrink-0', dotColor)}
        aria-hidden="true"
      />
      <span className={cn('hidden sm:inline font-medium', labelColor)}>
        {label}
      </span>
    </div>
  )
}
