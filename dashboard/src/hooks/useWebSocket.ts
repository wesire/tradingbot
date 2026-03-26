import { useCallback, useEffect, useRef, useState } from 'react'

const WS_BASE_URL = (() => {
  const api = import.meta.env.VITE_API_URL ?? ''
  if (api) {
    // Convert http:// → ws:// and https:// → wss://
    return api.replace(/^http/, 'ws')
  }
  // Relative path — use the same host, correct protocol
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}`
})()

const RECONNECT_DELAYS = [1000, 2000, 4000, 8000, 16000, 30000]

export type ConnectionState = 'connecting' | 'connected' | 'reconnecting' | 'disconnected'

export interface WSMessage {
  type: 'update' | 'ping' | 'subscribe_ack' | 'error'
  channel?: string
  data?: unknown
  timestamp?: string
  message?: string
  channels?: string[]
}

export interface UseWebSocketResult {
  connected: boolean
  connectionState: ConnectionState
  /** Latest data keyed by channel name */
  data: Record<string, unknown>
  lastUpdate: Date | null
  reconnecting: boolean
  error: string | null
  activeSubscriptions: string[]
}

/**
 * Custom hook that opens a WebSocket to /ws, subscribes to the specified
 * channels, and returns the latest data for each channel.
 *
 * Auto-reconnects with exponential back-off (1 s → 30 s).
 * Responds to server pings with pong messages.
 */
export function useWebSocket(channels: string[]): UseWebSocketResult {
  const [connectionState, setConnectionState] = useState<ConnectionState>('connecting')
  const [data, setData] = useState<Record<string, unknown>>({})
  const [lastUpdate, setLastUpdate] = useState<Date | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeSubscriptions, setActiveSubscriptions] = useState<string[]>([])

  const wsRef = useRef<WebSocket | null>(null)
  const attemptRef = useRef(0)
  const mountedRef = useRef(true)
  const channelsRef = useRef(channels)
  channelsRef.current = channels

  const connect = useCallback(() => {
    if (!mountedRef.current) return

    setConnectionState(attemptRef.current === 0 ? 'connecting' : 'reconnecting')

    const ws = new WebSocket(`${WS_BASE_URL}/ws`)
    wsRef.current = ws

    ws.onopen = () => {
      if (!mountedRef.current) return
      attemptRef.current = 0
      setConnectionState('connected')
      setError(null)

      // Subscribe to requested channels
      if (channelsRef.current.length > 0) {
        ws.send(JSON.stringify({ type: 'subscribe', channels: channelsRef.current }))
      }
    }

    ws.onmessage = (event: MessageEvent) => {
      if (!mountedRef.current) return
      try {
        const msg: WSMessage = JSON.parse(event.data as string)

        if (msg.type === 'ping') {
          ws.send(JSON.stringify({ type: 'pong' }))
          return
        }

        if (msg.type === 'subscribe_ack' && msg.channels) {
          setActiveSubscriptions(prev => [...new Set([...prev, ...msg.channels!])])
          return
        }

        if (msg.type === 'update' && msg.channel) {
          setData(prev => ({ ...prev, [msg.channel!]: msg.data }))
          setLastUpdate(new Date())
          return
        }

        if (msg.type === 'error') {
          setError(msg.message ?? 'WebSocket error')
        }
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      if (!mountedRef.current) return
      setConnectionState('disconnected')
      setActiveSubscriptions([])

      const delay =
        RECONNECT_DELAYS[Math.min(attemptRef.current, RECONNECT_DELAYS.length - 1)]
      attemptRef.current += 1
      setTimeout(connect, delay)
    }

    ws.onerror = () => {
      if (!mountedRef.current) return
      setError('WebSocket connection error')
      // onclose will fire after onerror, which triggers reconnect
    }
  }, []) // `connect` closes over stable refs (mountedRef, wsRef, attemptRef, channelsRef)

  useEffect(() => {
    mountedRef.current = true
    connect()

    return () => {
      mountedRef.current = false
      if (wsRef.current) {
        wsRef.current.onclose = null // Prevent reconnect on intentional close
        wsRef.current.close()
        wsRef.current = null
      }
    }
  }, [connect])

  return {
    connected: connectionState === 'connected',
    connectionState,
    data,
    lastUpdate,
    reconnecting: connectionState === 'reconnecting',
    error,
    activeSubscriptions,
  }
}
