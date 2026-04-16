import { useEffect, useRef, useCallback, useState } from 'react'

interface WebSocketMessage {
  type: string
  data: Record<string, unknown>
}

export function useWebSocket(onMessage?: (msg: WebSocketMessage) => void) {
  const ws = useRef<WebSocket | null>(null)
  const [connected, setConnected] = useState(false)

  const connect = useCallback(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const url = `${protocol}//${window.location.host}/ws`

    try {
      ws.current = new WebSocket(url)

      ws.current.onopen = () => {
        setConnected(true)
        console.log('[WS] Connected')
      }

      ws.current.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data) as WebSocketMessage
          onMessage?.(msg)
        } catch {}
      }

      ws.current.onclose = () => {
        setConnected(false)
        console.log('[WS] Disconnected, reconnecting in 5s...')
        setTimeout(connect, 5000)
      }

      ws.current.onerror = () => {
        ws.current?.close()
      }
    } catch {
      setTimeout(connect, 5000)
    }
  }, [onMessage])

  useEffect(() => {
    connect()
    return () => {
      ws.current?.close()
    }
  }, [connect])

  return { connected }
}
