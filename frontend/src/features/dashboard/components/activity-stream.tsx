/**
 * Activity Stream — live event log of recent fleet activity.
 *
 * Polls /api/admin/tasks/recent every 8s and renders the latest 12 events
 * as a Linear/Vercel-style timeline.
 */
import { useEffect, useState } from 'react'
import { Activity } from 'lucide-react'
import { fetchApi } from '@/lib/api'

interface RecentTask {
  id: number
  task_type: string
  status: string
  account_gmail?: string | null
  worker_name?: string | null
  created_at?: string | null
  completed_at?: string | null
}

const TYPE_LABEL: Record<string, string> = {
  comment: '댓글',
  reply: '대댓글',
  like: '좋아요',
  like_boost: '좋아요 부스트',
  subscribe: '구독',
  warmup: '워밍업',
  ghost_check: '고스트 체크',
  login: '로그인',
  channel_setup: '채널 셋업',
  onboard: '온보딩',
}

function dotVariant(status: string): 'ok' | 'warn' | 'fail' | 'info' {
  if (status === 'done') return 'ok'
  if (status === 'failed' || status === 'cancelled') return 'fail'
  if (status === 'running') return 'info'
  return 'warn'
}

function shortGmail(g?: string | null): string {
  if (!g) return ''
  return g.split('@')[0].slice(0, 14)
}

function relativeTime(iso?: string | null): string {
  if (!iso) return ''
  const t = new Date(iso).getTime()
  if (isNaN(t)) return ''
  const diff = (Date.now() - t) / 1000
  if (diff < 60) return `${Math.max(1, Math.round(diff))}초 전`
  if (diff < 3600) return `${Math.round(diff / 60)}분 전`
  if (diff < 86400) return `${Math.round(diff / 3600)}시간 전`
  return `${Math.round(diff / 86400)}일 전`
}

export function ActivityStream() {
  const [items, setItems] = useState<RecentTask[]>([])
  const [tick, setTick] = useState(0)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const res = await fetchApi<{ items: RecentTask[] }>('/api/admin/tasks/recent?limit=14').catch(() => null)
        if (!cancelled && res?.items) setItems(res.items)
      } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, 8_000)
    const tIntr = setInterval(() => setTick(x => x + 1), 30_000)
    return () => { cancelled = true; clearInterval(id); clearInterval(tIntr) }
  }, [])

  return (
    <div className='hydra-activity'>
      <div className='hydra-activity-head'>
        <div className='flex items-center gap-2'>
          <Activity className='size-4 text-muted-foreground' />
          <span className='hydra-activity-title'>실시간 활동</span>
        </div>
        <span className='text-[11px] text-muted-foreground/60' key={tick}>방금 업데이트</span>
      </div>
      <div className='hydra-activity-list'>
        {items.length === 0 ? (
          <div className='py-8 text-center text-muted-foreground text-[13px]'>
            아직 활동이 없어요
          </div>
        ) : (
          items.map(t => {
            const label = TYPE_LABEL[t.task_type] || t.task_type
            return (
              <div key={t.id} className='hydra-activity-item'>
                <div className={`hydra-activity-dot ${dotVariant(t.status)}`} />
                <div className='hydra-activity-body'>
                  <div className='hydra-activity-msg'>
                    <span className='font-semibold'>{label}</span>
                    <span className='text-muted-foreground'> · </span>
                    <span className='text-muted-foreground'>
                      {shortGmail(t.account_gmail) || `#${t.id}`}
                    </span>
                    <span className='text-muted-foreground/70 text-[11px]'> · {t.status}</span>
                  </div>
                  <div className='hydra-activity-meta'>
                    {t.worker_name ? `${t.worker_name} · ` : ''}{relativeTime(t.completed_at || t.created_at)}
                  </div>
                </div>
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}
