import { useEffect, useState } from 'react'
import { AlertTriangle, MessageSquare, ThumbsUp, Users, Monitor, Plus } from 'lucide-react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { useCountUp } from '@/hooks/use-count-up'
import type { DashboardStats, WorkerInfo } from './types'

interface ActiveCampaign {
  id: number
  video_title: string
  brand_name: string
  scenario: string
  campaign_type: string
  status: string
  total_tasks: number
  completed_tasks: number
  worker_name?: string
}

function StatCard({ label, value, icon: Icon, sub, danger }: {
  label: string
  value: number
  icon: React.ElementType
  sub?: string
  danger?: boolean
}) {
  const animated = useCountUp(value)
  return (
    <div
      className={`rounded-xl p-5 transition-colors ${danger ? 'border border-destructive/40' : 'border border-white/10'}`}
      style={{ background: 'rgba(255,255,255,0.03)' }}
    >
      <div className='flex items-center justify-between mb-3'>
        <span className='text-muted-foreground text-xs tracking-wide'>{label}</span>
        <Icon className='h-4 w-4 text-muted-foreground/50' />
      </div>
      <div className={`text-3xl font-bold tracking-tight ${danger ? 'text-destructive' : 'text-foreground'}`}>
        {animated}
      </div>
      {sub && <div className={`text-xs mt-2 ${danger ? 'text-destructive/80' : 'text-muted-foreground/70'}`}>{sub}</div>}
    </div>
  )
}

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={`hydra-skeleton ${className || ''}`} />
}

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [workers, setWorkers] = useState<WorkerInfo[]>([])
  const [campaigns, setCampaigns] = useState<ActiveCampaign[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function load() {
      try {
        const [s, w, c] = await Promise.all([
          fetchApi<DashboardStats>('/api/stats'),
          fetchApi<WorkerInfo[]>('/api/workers/'),
          fetchApi<{ items: ActiveCampaign[] }>('/campaigns/api/list?status=in_progress').catch(() => ({ items: [] })),
        ])
        setStats(s)
        setWorkers(w)
        setCampaigns(c.items || [])
      } catch { /* API not available */ }
      setLoading(false)
    }
    load()
    const interval = setInterval(load, 30_000)
    return () => clearInterval(interval)
  }, [])

  const onlineWorkers = workers.filter(w => w.status === 'online').length
  const errorCount = stats?.errors?.unresolved ?? 0
  const systemStatus = errorCount > 0 ? 'error' : onlineWorkers > 0 ? 'ok' : 'warn'

  if (loading) {
    return (
      <>
        <Header fixed>
          <div className='ml-auto flex items-center space-x-4'>
            <ThemeSwitch />
            <ProfileDropdown />
          </div>
        </Header>
        <Main>
          <div className='space-y-5'>
            <SkeletonBlock className='h-20 w-full rounded-xl' />
            <div className='grid grid-cols-2 lg:grid-cols-4 gap-3'>
              <SkeletonBlock className='h-24 rounded-xl' />
              <SkeletonBlock className='h-24 rounded-xl' />
              <SkeletonBlock className='h-24 rounded-xl' />
              <SkeletonBlock className='h-24 rounded-xl' />
            </div>
            <div className='grid grid-cols-1 lg:grid-cols-[5fr_3fr] gap-4'>
              <SkeletonBlock className='h-64 rounded-xl' />
              <div className='space-y-4'>
                <SkeletonBlock className='h-28 rounded-xl' />
                <SkeletonBlock className='h-28 rounded-xl' />
              </div>
            </div>
          </div>
        </Main>
      </>
    )
  }

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='space-y-5'>

          {/* === System Status Banner === */}
          <div className={`rounded-xl p-5 flex items-center justify-between ${
            systemStatus === 'ok' ? 'hydra-status-ok' :
            systemStatus === 'warn' ? 'hydra-status-warn' : 'hydra-status-error'
          }`}>
            <div>
              <div className='flex items-center gap-3 mb-1'>
                <div className={`hydra-led-${systemStatus === 'ok' ? 'online' : systemStatus === 'warn' ? 'paused' : 'offline'}`}
                     style={systemStatus === 'error' ? { background: '#ef4444' } : undefined} />
                <span className='text-foreground text-lg font-bold'>
                  {systemStatus === 'ok' ? '시스템 정상 운영 중' :
                   systemStatus === 'warn' ? '워커 연결을 확인하세요' :
                   `주의가 필요해요 — 미해결 오류 ${errorCount}건`}
                </span>
              </div>
              <span className='text-muted-foreground text-[13px]'>
                Worker {onlineWorkers}대 온라인 · 캠페인 {campaigns.length}개 진행 중
                {errorCount > 0 && ` · 오류 ${errorCount}건`}
              </span>
            </div>
            <div className='text-muted-foreground text-[12px] text-right'>
              마지막 업데이트<br />
              <span className='text-foreground/70'>방금 전</span>
            </div>
          </div>

          {/* === Stat Cards === */}
          <div className='grid grid-cols-2 lg:grid-cols-4 gap-3'>
            <StatCard
              label='오늘 댓글'
              value={stats?.today?.comments ?? 0}
              icon={MessageSquare}
              sub='목표 대비 작업량'
            />
            <StatCard
              label='오늘 좋아요'
              value={stats?.today?.likes ?? 0}
              icon={ThumbsUp}
              sub='부스트 포함'
            />
            <StatCard
              label='활성 계정'
              value={Number(Object.values(stats?.accounts ?? {}).reduce((a: number, b: unknown) => a + (typeof b === 'number' ? b : 0), 0)) || 0}
              icon={Users}
              sub={`${workers.length}대 Worker 연결`}
            />
            <StatCard
              label='주의 필요'
              value={errorCount}
              icon={AlertTriangle}
              sub={errorCount > 0 ? '클릭해서 확인' : '문제 없음'}
              danger={errorCount > 0}
            />
          </div>

          {/* === Middle: Campaigns + Workers + Alerts === */}
          <div className='grid grid-cols-1 lg:grid-cols-[5fr_3fr] gap-4'>

            {/* Campaign Progress */}
            <div className='rounded-xl border border-white/10 overflow-hidden'>
              <div className='px-5 py-4 border-b border-border flex items-center justify-between'>
                <span className='text-foreground font-semibold text-[15px]'>진행 중인 캠페인</span>
                <a href='/campaigns' className='text-primary text-[12px] hover:underline'>전체보기</a>
              </div>
              <div className='px-5 py-4'>
                {campaigns.length > 0 ? campaigns.map(c => {
                  const progress = c.total_tasks > 0 ? Math.round(c.completed_tasks / c.total_tasks * 100) : 0
                  return (
                    <div key={c.id} className='py-3 border-b border-border/50 last:border-0'>
                      <div className='flex items-center justify-between mb-2'>
                        <div className='flex items-center gap-2'>
                          <span className='text-foreground font-medium text-[14px] truncate max-w-[300px]'>
                            {c.brand_name} — {c.video_title || `캠페인 #${c.id}`}
                          </span>
                          <span className={`hydra-tag ${c.campaign_type === 'direct' ? 'hydra-tag-warning' : 'hydra-tag-primary'}`}
                                style={{ fontSize: '10px', padding: '1px 8px' }}>
                            {c.campaign_type === 'direct' ? '다이렉트' : `프리셋 ${c.scenario}`}
                          </span>
                        </div>
                        <span className={`text-[13px] font-semibold ${progress >= 100 ? 'text-green-500' : 'text-foreground'}`}>
                          {progress}%
                        </span>
                      </div>
                      <div className='hydra-progress-bar mb-1.5'>
                        <div className='hydra-progress-fill bg-gradient-to-r from-primary to-green-500' style={{ width: `${progress}%` }} />
                      </div>
                      <div className='flex items-center justify-between text-muted-foreground text-[11px]'>
                        <span>{c.completed_tasks}/{c.total_tasks} 태스크</span>
                        {c.worker_name && <span className='text-primary'>{c.worker_name}</span>}
                      </div>
                    </div>
                  )
                }) : (
                  <div className='py-10 text-center'>
                    <p className='text-muted-foreground text-sm mb-1'>진행 중인 캠페인이 없어요</p>
                    <p className='text-muted-foreground/60 text-xs mb-4'>캠페인 페이지에서 새 캠페인을 만들어보세요</p>
                    <a href='/campaigns'
                       className='inline-flex items-center gap-2 px-5 py-2.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium hover:opacity-90 transition-opacity'>
                      <Plus className='h-4 w-4' /> 캠페인 만들기
                    </a>
                  </div>
                )}
              </div>
            </div>

            {/* Right column */}
            <div className='space-y-4'>

              {/* Workers */}
              <div className='rounded-xl border border-white/10 overflow-hidden'>
                <div className='px-4 py-3 border-b border-border flex items-center justify-between'>
                  <span className='text-foreground font-semibold text-[15px]'>워커</span>
                  <a href='/workers' className='text-primary text-[12px] hover:underline'>관리</a>
                </div>
                <div className='px-4 py-3'>
                  {workers.length > 0 ? workers.map(w => (
                    <div key={w.id} className='flex items-center justify-between py-2 border-b border-border/30 last:border-0'>
                      <div className='flex items-center gap-2.5'>
                        <div className={`hydra-led-${w.status === 'online' ? 'online' : w.status === 'paused' ? 'paused' : 'offline'}`} />
                        <span className={`text-[13px] ${w.status === 'online' ? 'text-foreground' : 'text-muted-foreground'}`}>
                          {w.name}
                        </span>
                      </div>
                      <span className={`text-[12px] ${w.status === 'online' ? 'text-green-500' : 'text-muted-foreground'}`}>
                        {w.status === 'online' ? '온라인' : w.status === 'paused' ? '일시정지' : '오프라인'}
                      </span>
                    </div>
                  )) : (
                    <div className='py-6 text-center'>
                      <Monitor className='h-8 w-8 text-muted-foreground/30 mx-auto mb-2' />
                      <p className='text-muted-foreground text-sm mb-1'>연결된 워커가 없어요</p>
                      <p className='text-muted-foreground/60 text-xs mb-3'>워커 PC를 연결해보세요</p>
                      <a href='/workers'
                         className='inline-flex items-center gap-2 px-4 py-2 border border-white/20 rounded-lg text-sm text-foreground hover:bg-white/5 transition-colors'>
                        <Plus className='h-4 w-4' /> 워커 추가
                      </a>
                    </div>
                  )}
                </div>
              </div>

              {/* Alerts */}
              <div className='rounded-xl border border-white/10 overflow-hidden'>
                <div className='px-4 py-3 border-b border-border flex items-center justify-between'>
                  <span className='text-foreground font-semibold text-[15px]'>알림</span>
                  {errorCount > 0 && (
                    <span className='bg-destructive text-destructive-foreground w-5 h-5 rounded-full flex items-center justify-center text-[11px]'>
                      {errorCount}
                    </span>
                  )}
                </div>
                <div className='px-4 py-3 text-[12px]'>
                  {stats?.tasks?.today_failed ? (
                    <div className='py-2 border-b border-border/30'>
                      <div className='text-destructive'>오늘 {stats.tasks.today_failed}건 실패</div>
                      <div className='text-muted-foreground/60 text-[11px]'>로그에서 확인하세요</div>
                    </div>
                  ) : null}
                  {stats?.tasks?.today_completed ? (
                    <div className='py-2'>
                      <div className='text-green-500'>오늘 {stats.tasks.today_completed}건 완료</div>
                    </div>
                  ) : (
                    <div className='py-4 text-center'>
                      <p className='text-muted-foreground'>새 알림이 없어요</p>
                      <p className='text-muted-foreground/60 text-[11px] mt-1'>시스템 이벤트가 여기에 표시됩니다</p>
                    </div>
                  )}
                </div>
              </div>

            </div>
          </div>

        </div>
      </Main>
    </>
  )
}
