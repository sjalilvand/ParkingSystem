import { useEffect, useRef, useState } from 'react'
import { tokens } from './client'

export interface LiveEvent {
  event: string
  event_id: string
  occurred_at: string
  data: Record<string, unknown>
}

export function useLiveEvents(max = 30) {
  const [events, setEvents] = useState<LiveEvent[]>([])
  const [connected, setConnected] = useState(false)
  const retry = useRef(0)

  useEffect(() => {
    if (!tokens.access) return
    let closed = false
    let timer: ReturnType<typeof setTimeout>
    let ws: WebSocket | null = null

    const connect = () => {
      if (closed) return
      const proto = location.protocol === 'https:' ? 'wss' : 'ws'
      ws = new WebSocket(`${proto}://${location.host}/ws/v1/events?token=${tokens.access}`)
      ws.onopen = () => { setConnected(true); retry.current = 0 }
      ws.onclose = () => {
        setConnected(false)
        timer = setTimeout(connect, Math.min(1000 * 2 ** retry.current++, 15000))
      }
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data) as LiveEvent
          if (msg.event === 'pong') return
          setEvents((prev) => [msg, ...prev].slice(0, max))
        } catch { /* ignore */ }
      }
    }
    connect()
    const ping = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'ping' }))
    }, 25000)

    return () => { closed = true; clearInterval(ping); clearTimeout(timer); ws?.close() }
  }, [max])

  return { events, connected }
}