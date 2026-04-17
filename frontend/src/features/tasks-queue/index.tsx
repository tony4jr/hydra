import { useEffect, useState } from 'react'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { useCountUp } from '@/hooks/use-count-up'

interface Task {
  id: number
  type: string
  status: string
  content?: string
  account_name?: string
  worker_name?: string
  campaign_id?: number
  campaign_name?: string
  scheduled_at?: string | null
  completed_at?: string | null
  created_at: string
  progress?: number
  progress_total?: number
}

const ledColor: Record<string, string> = {
  running: 'bg-[#6c5ce7]',
  pending: 'bg-[#71717a]',
  completed: 'bg-[#22c55e]',
  failed: 'bg-[#ef4444]',
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  const animated = useCountUp(value)
  return (
    <div className='bg-card rounded-xl border border-border p-4'>
      <div className='flex items-center gap-2 mb-1'>
        <div className={`w-2.5 h-2.5 rounded-full ${color}`} />
        <span className='text-muted-foreground text-[12px]'>{label}</span>
      </div>
      <div className='text-[28px] font-bold'>{animated}</div>
    </div>
  )
}

export default function TasksQueuePage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [loading, setLoading] = useState(true)
  const [campaignFilter, setCampaignFilter] = useState<string>('all')
  const [stats, setStats] = useState({ pending: 0, running: 0, completed: 0, failed: 0 })

  useEffect(() => {
    setLoading(true)
    fetchApi<{ stats: { pending: number; assigned: number; running: number; completed: number; failed: number }; items: any[] }>('/api/tasks/list')
      .then(data => {
        const items = (data.items || []).map((t: any): Task => ({
          id: t.id || 0,
          type: t.task_type || '',
          status: t.status || '',
          content: t.task_type || '',
          account_name: t.account_gmail || null,
          worker_name: t.worker_name || null,
          campaign_id: undefined,
          campaign_name: t.campaign_name || null,
          scheduled_at: t.scheduled_at || null,
          completed_at: t.completed_at || null,
          created_at: t.created_at || '',
          progress: undefined,
          progress_total: undefined,
        }))
        setTasks(items)
        const s = data.stats || { pending: 0, assigned: 0, running: 0, completed: 0, failed: 0 }
        setStats({
          pending: s.pending + s.assigned,
          running: s.running,
          completed: s.completed,
          failed: s.failed,
        })
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const filtered = campaignFilter === 'all' ? tasks : tasks.filter(t => String(t.campaign_id) === campaignFilter)
  const campaignIds = [...new Set(tasks.filter(t => t.campaign_id).map(t => ({
    id: String(t.campaign_id),
    name: t.campaign_name || `캠페인 #${t.campaign_id}`,
  })))]
  // Deduplicate
  const uniqueCampaigns = campaignIds.filter((v, i, self) => self.findIndex(c => c.id === v.id) === i)

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div >
          <div className='mb-5 flex flex-wrap items-center justify-between gap-2'>
            <div>
              <h2 className='text-[22px] font-bold'>작업 큐</h2>
              <p className='text-muted-foreground text-[13px]'>실시간 태스크 모니터링</p>
            </div>
            {uniqueCampaigns.length > 0 && (
              <Select value={campaignFilter} onValueChange={setCampaignFilter}>
                <SelectTrigger className='w-48'>
                  <SelectValue placeholder='캠페인 필터' />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value='all'>전체 캠페인</SelectItem>
                  {uniqueCampaigns.map(c => (
                    <SelectItem key={c.id} value={c.id}>{c.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          </div>

          {/* Stat cards */}
          {loading ? (
            <div className='grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5'>
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className='h-24 rounded-xl' />)}
            </div>
          ) : (
            <div className='grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5'>
              <StatCard label='대기' value={stats.pending} color='bg-[#71717a]' />
              <StatCard label='진행중' value={stats.running} color='bg-[#6c5ce7]' />
              <StatCard label='완료' value={stats.completed} color='bg-[#22c55e]' />
              <StatCard label='실패' value={stats.failed} color='bg-[#ef4444]' />
            </div>
          )}

          {/* Task list */}
          {loading ? (
            <div className='space-y-2'>
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className='h-16 rounded-xl' />)}
            </div>
          ) : filtered.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px] mb-1'>대기 중인 작업이 없어요</p>
              <p className='text-muted-foreground/60 text-[12px]'>캠페인이 실행되면 태스크가 여기에 표시됩니다</p>
            </div>
          ) : (
            <div className='space-y-2'>
              {filtered.map(task => (
                <div
                  key={task.id}
                  className={`bg-card border border-border rounded-xl p-4 ${
                    task.status === 'pending' || task.status === 'completed' ? 'opacity-60' : ''
                  }`}
                >
                  <div className='flex items-center justify-between'>
                    <div className='flex items-center gap-3'>
                      {/* LED */}
                      <div className={`w-2.5 h-2.5 rounded-full ${ledColor[task.status] || 'bg-gray-500'} ${
                        task.status === 'running' ? 'animate-pulse' : ''
                      }`} />

                      <div>
                        <div className='flex items-center gap-2'>
                          <span className='text-foreground font-medium text-[14px]'>
                            {task.type || '작업'}
                          </span>
                          {task.content && (
                            <span className='text-muted-foreground text-[12px] truncate max-w-[200px]'>
                              {task.content}
                            </span>
                          )}
                        </div>
                        <div className='flex items-center gap-3 text-muted-foreground text-[11px] mt-0.5'>
                          {task.account_name && <span>{task.account_name}</span>}
                          {task.worker_name && <span className='text-primary'>{task.worker_name}</span>}
                          {task.status === 'pending' && task.scheduled_at && (
                            <span>예정: {new Date(task.scheduled_at).toLocaleString('ko')}</span>
                          )}
                          {task.status === 'completed' && task.completed_at && (
                            <span>완료: {new Date(task.completed_at).toLocaleString('ko')}</span>
                          )}
                        </div>
                      </div>
                    </div>

                    <div className='flex items-center gap-2'>
                      {/* Progress bar for like boost */}
                      {task.progress != null && task.progress_total != null && task.progress_total > 0 && (
                        <div className='w-24'>
                          <div className='hydra-progress-bar'>
                            <div
                              className='hydra-progress-fill bg-primary'
                              style={{ width: `${Math.round(task.progress / task.progress_total * 100)}%` }}
                            />
                          </div>
                          <span className='text-muted-foreground text-[10px]'>{task.progress}/{task.progress_total}</span>
                        </div>
                      )}

                      {(task.status === 'pending' || task.status === 'running') && (
                        <Button variant='ghost' size='icon' className='h-7 w-7 text-muted-foreground hover:text-destructive hydra-btn-press'>
                          <X className='h-3.5 w-3.5' />
                        </Button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </Main>
    </>
  )
}
