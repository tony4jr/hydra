/**
 * Global WebSocket provider — single connection, multi-subscriber bus.
 *
 * Usage:
 *   const unsub = useWSEvent('task.completed', (data) => { ... })
 *
 * Connects to `<host>/ws` on mount, auto-reconnects with backoff, exposes a
 * pub/sub bus so any component can subscribe to event types without owning
 * the socket.
 */
import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'

interface WSMessage {
  type: string
  data: Record<string, unknown>
}

type Listener = (data: Record<string, unknown>) => void

interface WSBus {
  connected: boolean
  subscribe: (eventType: string, fn: Listener) => () => void
}

const WSContext = createContext<WSBus | null>(null)

export function WSProvider({ children }: { children: ReactNode }) {
  const [connected, setConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const listenersRef = useRef<Map<string, Set<Listener>>>(new Map())
  const reconnectTimerRef = useRef<number | null>(null)
  const backoffRef = useRef(1000)

  useEffect(() => {
    let alive = true

    const connect = () => {
      if (!alive) return
      const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
      // Vite dev server proxies /ws to backend (configure in vite.config); in
      // prod the same origin serves both.
      const url = `${proto}//${window.location.host}/ws`
      let ws: WebSocket
      try {
        ws = new WebSocket(url)
      } catch {
        scheduleReconnect()
        return
      }
      wsRef.current = ws
      ws.onopen = () => {
        backoffRef.current = 1000
        setConnected(true)
      }
      ws.onmessage = (ev) => {
        let msg: WSMessage
        try {
          msg = JSON.parse(ev.data) as WSMessage
        } catch {
          return
        }
        if (!msg?.type) return
        const set = listenersRef.current.get(msg.type)
        if (!set) return
        for (const fn of set) {
          try { fn(msg.data || {}) } catch { /* ignore listener errors */ }
        }
      }
      ws.onclose = () => {
        setConnected(false)
        scheduleReconnect()
      }
      ws.onerror = () => { ws.close() }
    }

    const scheduleReconnect = () => {
      if (!alive) return
      const delay = Math.min(backoffRef.current, 15000)
      reconnectTimerRef.current = window.setTimeout(connect, delay)
      backoffRef.current = Math.min(backoffRef.current * 2, 15000)
    }

    connect()
    return () => {
      alive = false
      if (reconnectTimerRef.current) window.clearTimeout(reconnectTimerRef.current)
      wsRef.current?.close()
    }
  }, [])

  const bus = useMemo<WSBus>(() => ({
    connected,
    subscribe: (eventType, fn) => {
      let set = listenersRef.current.get(eventType)
      if (!set) {
        set = new Set()
        listenersRef.current.set(eventType, set)
      }
      set.add(fn)
      return () => {
        set!.delete(fn)
        if (set!.size === 0) listenersRef.current.delete(eventType)
      }
    },
  }), [connected])

  return <WSContext.Provider value={bus}>{children}</WSContext.Provider>
}

export function useWSStatus(): boolean {
  const ctx = useContext(WSContext)
  return ctx?.connected ?? false
}

export function useWSEvent(
  eventType: string | string[],
  fn: Listener,
): void {
  const ctx = useContext(WSContext)
  // Stable callback ref so listener re-registration doesn't churn.
  const fnRef = useRef(fn)
  fnRef.current = fn

  useEffect(() => {
    if (!ctx) return
    const types = Array.isArray(eventType) ? eventType : [eventType]
    const wrapped: Listener = (data) => fnRef.current(data)
    const unsubs = types.map(t => ctx.subscribe(t, wrapped))
    return () => { unsubs.forEach(u => u()) }
  }, [ctx, Array.isArray(eventType) ? eventType.join(',') : eventType])
}
