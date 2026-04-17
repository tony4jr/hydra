import { useEffect, useState } from 'react'
import {
  AlertTriangle,
  Megaphone,
  MessageSquare,
  Monitor,
  ThumbsUp,
} from 'lucide-react'
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { ConfigDrawer } from '@/components/config-drawer'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { TopNav } from '@/components/layout/top-nav'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { Search } from '@/components/search'
import { ThemeSwitch } from '@/components/theme-switch'
import { Badge } from '@/components/ui/badge'
import { fetchApi } from '@/lib/api'
import type { DashboardStats, WorkerInfo } from './types'

interface ActiveCampaign {
  id: number
  video_title: string
  brand_name: string
  scenario: string
  status: string
  total_tasks: number
  completed_tasks: number
  worker_name?: string
}

export function Dashboard() {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [workers, setWorkers] = useState<WorkerInfo[]>([])
  const [activeCampaigns, setActiveCampaigns] = useState<ActiveCampaign[]>([])

  useEffect(() => {
    async function load() {
      try {
        const [s, w, c] = await Promise.all([
          fetchApi<DashboardStats>('/api/stats'),
          fetchApi<WorkerInfo[]>('/api/workers/'),
          fetchApi<{ items: ActiveCampaign[] }>(
            '/campaigns/api/list?status=in_progress'
          ).catch(() => ({ items: [] })),
        ])
        setStats(s)
        setWorkers(w)
        setActiveCampaigns(c.items || [])
      } catch {
        // API not available — use empty defaults
      }
    }
    load()
    const interval = setInterval(load, 30_000)
    return () => clearInterval(interval)
  }, [])

  return (
    <>
      {/* ===== Top Heading ===== */}
      <Header>
        <TopNav links={topNav} />
        <div className='ms-auto flex items-center space-x-4'>
          <Search />
          <ThemeSwitch />
          <ConfigDrawer />
          <ProfileDropdown />
        </div>
      </Header>

      {/* ===== Main ===== */}
      <Main>
        <div className='mb-2 flex items-center justify-between space-y-2'>
          <h1 className='text-2xl font-bold tracking-tight'>대시보드</h1>
        </div>

        <div className='space-y-4'>
          {/* ===== Top Row: 5 Stat Cards ===== */}
          <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-5'>
            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>
                  워커 온라인
                </CardTitle>
                <Monitor className='h-4 w-4 text-muted-foreground' />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>
                  {stats?.workers?.online ?? 0}
                  <span className='text-sm text-muted-foreground'>
                    /{stats?.workers?.total ?? 0}
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>
                  진행중 캠페인
                </CardTitle>
                <Megaphone className='h-4 w-4 text-muted-foreground' />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>
                  {stats?.campaigns?.active ?? 0}
                  <span className='text-sm text-muted-foreground'>
                    /{stats?.campaigns?.total ?? 0}
                  </span>
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>
                  오늘 댓글
                </CardTitle>
                <MessageSquare className='h-4 w-4 text-muted-foreground' />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>
                  {stats?.today?.comments ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>
                  오늘 좋아요
                </CardTitle>
                <ThumbsUp className='h-4 w-4 text-muted-foreground' />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>
                  {stats?.today?.likes ?? 0}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>
                  문제 계정
                </CardTitle>
                <AlertTriangle className='h-4 w-4 text-muted-foreground' />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>
                  {stats?.errors?.unresolved ?? 0}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* ===== Middle Row: Campaigns + Workers ===== */}
          <div className='grid grid-cols-1 gap-4 lg:grid-cols-3'>
            <Card className='col-span-1 lg:col-span-2'>
              <CardHeader>
                <CardTitle>진행중 캠페인</CardTitle>
              </CardHeader>
              <CardContent>
                <div className='space-y-4'>
                  {activeCampaigns.length > 0 ? (
                    activeCampaigns.map((c) => {
                      const progress =
                        c.total_tasks > 0
                          ? Math.round(
                              (c.completed_tasks / c.total_tasks) * 100
                            )
                          : 0
                      return (
                        <div key={c.id} className='space-y-1'>
                          <div className='flex items-center justify-between text-sm'>
                            <span className='font-medium truncate max-w-[60%]'>
                              {c.brand_name} - {c.video_title || `#${c.id}`}
                            </span>
                            <div className='flex items-center gap-2'>
                              <Badge variant='outline' className='text-xs'>
                                {c.scenario}
                              </Badge>
                              {c.worker_name && (
                                <span className='flex items-center gap-1 text-xs text-muted-foreground'>
                                  <Monitor className='h-3 w-3' />
                                  {c.worker_name}
                                </span>
                              )}
                            </div>
                          </div>
                          <div className='flex items-center gap-2'>
                            <div className='h-2 flex-1 rounded-full bg-muted'>
                              <div
                                className='h-2 rounded-full bg-primary transition-all'
                                style={{ width: `${progress}%` }}
                              />
                            </div>
                            <span className='text-xs text-muted-foreground whitespace-nowrap'>
                              {c.completed_tasks}/{c.total_tasks} ({progress}%)
                            </span>
                          </div>
                        </div>
                      )
                    })
                  ) : (
                    <p className='text-sm text-muted-foreground'>
                      진행중인 캠페인 없음
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card className='col-span-1'>
              <CardHeader>
                <CardTitle>워커 상태</CardTitle>
              </CardHeader>
              <CardContent>
                <div className='space-y-3'>
                  {workers.length > 0 ? (
                    workers.map((w) => (
                      <div
                        key={w.id}
                        className='flex items-center justify-between'
                      >
                        <div className='flex items-center gap-2'>
                          <span
                            className={`h-2 w-2 rounded-full ${
                              w.status === 'online'
                                ? 'bg-green-500'
                                : 'bg-gray-400'
                            }`}
                          />
                          <span className='text-sm'>{w.name}</span>
                        </div>
                        <span className='text-xs text-muted-foreground'>
                          {w.status}
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className='text-sm text-muted-foreground'>
                      연결된 워커 없음
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>

          {/* ===== Bottom Row: Recent Activity + Alerts ===== */}
          <div className='grid grid-cols-1 gap-4 lg:grid-cols-2'>
            <Card>
              <CardHeader>
                <CardTitle>최근 활동</CardTitle>
              </CardHeader>
              <CardContent>
                <div className='space-y-3'>
                  {stats?.tasks ? (
                    <>
                      <div className='flex items-center justify-between text-sm'>
                        <span>오늘 완료</span>
                        <span className='font-medium'>
                          {stats.tasks.today_completed}
                        </span>
                      </div>
                      <div className='flex items-center justify-between text-sm'>
                        <span>오늘 실패</span>
                        <span className='font-medium text-destructive'>
                          {stats.tasks.today_failed}
                        </span>
                      </div>
                      <div className='flex items-center justify-between text-sm'>
                        <span>대기중</span>
                        <span className='font-medium'>
                          {stats.tasks.pending}
                        </span>
                      </div>
                      <div className='flex items-center justify-between text-sm'>
                        <span>실행중</span>
                        <span className='font-medium'>
                          {stats.tasks.running}
                        </span>
                      </div>
                    </>
                  ) : (
                    <p className='text-sm text-muted-foreground'>
                      활동 데이터 없음
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>알림</CardTitle>
              </CardHeader>
              <CardContent>
                <div className='space-y-3'>
                  {stats?.errors?.unresolved ? (
                    <div className='flex items-center gap-2 text-sm'>
                      <AlertTriangle className='h-4 w-4 text-destructive' />
                      <span>
                        미해결 오류 {stats.errors.unresolved}건
                      </span>
                    </div>
                  ) : (
                    <p className='text-sm text-muted-foreground'>
                      새 알림 없음
                    </p>
                  )}
                </div>
              </CardContent>
            </Card>
          </div>
        </div>
      </Main>
    </>
  )
}

const topNav = [
  {
    title: '대시보드',
    href: 'dashboard/overview',
    isActive: true,
    disabled: false,
  },
  {
    title: '캠페인',
    href: 'dashboard/campaigns',
    isActive: false,
    disabled: true,
  },
  {
    title: '계정',
    href: 'dashboard/accounts',
    isActive: false,
    disabled: true,
  },
  {
    title: '설정',
    href: 'dashboard/settings',
    isActive: false,
    disabled: true,
  },
]
