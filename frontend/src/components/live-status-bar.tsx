/**
 * Live Status Bar — fleet operator's signal panel.
 *
 * Always-on top strip showing:
 *   • System pulse (green dot if healthy, amber/red otherwise)
 *   • Worker count + heartbeat
 *   • Active campaign count
 *   • Mobile IP indicator (anti-detection rotation)
 *   • Pending tasks counter
 *   • Last 24h posted comments
 *   • Time-since-last-activity
 *
 * Polls /api/stats + /api/workers/ every 5s.
 * Pulse animation + count-up + transitions.
 */
import { useEffect, useState } from 'react'
import { Activity, Cpu, Globe, MessageSquare, Pause, Wifi } from 'lucide-react'
import { fetchApi } from '@/lib/api'
import { cn } from '@/lib/utils'

interface LiveData {
  workers: { online: number; offline: number; paused: number }
  campaigns_active: number
  tasks_pending: number
  comments_today: number
  errors_unresolved: number
  last_activity_sec: number | null
}

interface PulseProps { variant: 'ok' | 'warn' | 'fail' }
function Pulse({ variant }: PulseProps) {
  const color = variant === 'ok' ? 'bg-emerald-500' : variant === 'warn' ? 'bg-amber-500' : 'bg-rose-500'
  return (
    <span className='relative inline-flex'>
      <span className={cn('size-2 rounded-full', color)} />
      <span className={cn('absolute inset-0 size-2 rounded-full opacity-50 animate-ping', color)} />
    </span>
  )
}

export function LiveStatusBar() {
  const [data, setData] = useState<LiveData | null>(null)
  const [now, setNow] = useState(Date.now())

  useEffect(() => {
    let cancelled = false
    async function tick() {
      try {
        const [stats, workers] = await Promise.all([
          fetchApi<{
            today: { comments?: number }
            errors: { unresolved?: number }
            tasks?: { pending?: number }
            campaigns_active?: number
            last_activity_sec?: number | null
          }>('/api/stats').catch(() => null),
          fetchApi<{ status: string }[]>('/api/workers/').catch(() => []),
        ])
        if (cancelled) return
        const ws = workers || []
        setData({
          workers: {
            online: ws.filter(w => w.status === 'online').length,
            offline: ws.filter(w => w.status === 'offline').length,
            paused: ws.filter(w => w.status === 'paused').length,
          },
          campaigns_active: stats?.campaigns_active ?? 0,
          tasks_pending: stats?.tasks?.pending ?? 0,
          comments_today: stats?.today?.comments ?? 0,
          errors_unresolved: stats?.errors?.unresolved ?? 0,
          last_activity_sec: stats?.last_activity_sec ?? null,
        })
      } catch {
        /* ignore */
      }
    }
    tick()
    const id = setInterval(tick, 5000)
    const tIntr = setInterval(() => setNow(Date.now()), 1000)
    return () => {
      cancelled = true
      clearInterval(id)
      clearInterval(tIntr)
    }
  }, [])

  const variant: 'ok' | 'warn' | 'fail' =
    !data ? 'warn'
      : data.errors_unresolved > 0 ? 'fail'
      : data.workers.online === 0 ? 'warn'
      : 'ok'

  const sysLabel =
    !data ? '연결 중'
      : variant === 'fail' ? `오류 ${data.errors_unresolved}건`
      : variant === 'warn' ? '워커 대기'
      : '정상 작동'

  return (
    <div className='hydra-livebar'>
      <div className='hydra-livebar-inner'>
        {/* System pulse */}
        <div className='hydra-livebar-cell'>
          <Pulse variant={variant} />
          <span className='hydra-livebar-label'>{sysLabel}</span>
        </div>

        <div className='hydra-livebar-divider' />

        {/* Workers */}
        <div className='hydra-livebar-cell'>
          <Cpu className='size-3.5 text-muted-foreground' />
          <span className='hydra-livebar-label'>
            워커 <span className='hydra-livebar-num'>{data?.workers.online ?? '·'}</span>
            {data && data.workers.offline > 0 && (
              <span className='text-muted-foreground/60 text-[11px] ml-0.5'>/{data.workers.offline + data.workers.online}</span>
            )}
          </span>
        </div>

        <div className='hydra-livebar-divider' />

        {/* Active campaigns */}
        <div className='hydra-livebar-cell'>
          <Activity className='size-3.5 text-muted-foreground' />
          <span className='hydra-livebar-label'>
            진행 <span className='hydra-livebar-num'>{data?.campaigns_active ?? '·'}</span>
          </span>
        </div>

        {/* Pending */}
        {data && data.tasks_pending > 0 && (
          <>
            <div className='hydra-livebar-divider' />
            <div className='hydra-livebar-cell'>
              <Pause className='size-3.5 text-muted-foreground' />
              <span className='hydra-livebar-label'>
                대기 <span className='hydra-livebar-num'>{data.tasks_pending}</span>
              </span>
            </div>
          </>
        )}

        <div className='hydra-livebar-divider' />

        {/* Today comments */}
        <div className='hydra-livebar-cell'>
          <MessageSquare className='size-3.5 text-muted-foreground' />
          <span className='hydra-livebar-label'>
            오늘 <span className='hydra-livebar-num'>{data?.comments_today ?? '·'}</span>
          </span>
        </div>

        <div className='hydra-livebar-spacer' />

        {/* Mobile IP */}
        <div className='hydra-livebar-cell'>
          <Globe className='size-3.5 text-muted-foreground' />
          <span className='hydra-livebar-label hidden sm:inline'>모바일 회전</span>
        </div>

        {/* Connection */}
        <div className='hydra-livebar-cell'>
          <Wifi className={cn('size-3.5', variant === 'fail' ? 'text-rose-500' : 'text-emerald-500')} />
        </div>

        {/* Now */}
        <div className='hydra-livebar-cell hidden md:flex'>
          <span className='hydra-livebar-time'>
            {new Date(now).toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false })}
          </span>
        </div>
      </div>
    </div>
  )
}
