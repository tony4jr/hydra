import { useEffect, useState } from 'react'
import {
  Monitor,
  Plus,
  Wifi,
  WifiOff,
  Pause,
  Lock,
  Activity,
  CheckCircle2,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { WorkerAddDialog } from './worker-add-dialog'

interface Worker {
  id: number
  name: string
  status: string
  last_heartbeat: string | null
  version: string | null
  os_type: string | null
  locked_profiles: number
  running_tasks: number
  allow_preparation?: boolean
  allow_campaign?: boolean
}

interface WorkerSummary {
  online: number
  total: number
  running_tasks: number
  completed_today: number
}

const statusIcon = (s: string) => {
  switch (s) {
    case 'online':
      return <Wifi className='h-4 w-4 text-green-500' />
    case 'offline':
      return <WifiOff className='h-4 w-4 text-muted-foreground' />
    case 'paused':
      return <Pause className='h-4 w-4 text-yellow-500' />
    default:
      return <WifiOff className='h-4 w-4 text-muted-foreground' />
  }
}

const statusBadgeVariant = (s: string) => {
  switch (s) {
    case 'online':
      return 'default' as const
    case 'offline':
      return 'secondary' as const
    case 'paused':
      return 'outline' as const
    default:
      return 'secondary' as const
  }
}

export default function WorkersPage() {
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [workers, setWorkers] = useState<Worker[]>([])
  const [summary, setSummary] = useState<WorkerSummary>({
    online: 0,
    total: 0,
    running_tasks: 0,
    completed_today: 0,
  })

  const loadWorkers = () => {
    fetchApi<Worker[]>('/api/workers/')
      .then((data) => {
        const workerList = Array.isArray(data) ? data : []
        setWorkers(workerList)
        setSummary({
            online: workerList.filter(w => w.status === 'online').length,
            total: workerList.length,
            running_tasks: 0,
            completed_today: 0,
          })
      })
      .catch(() => {})
  }

  useEffect(() => {
    loadWorkers()
  }, [])

  const summaryCards = [
    {
      title: '온라인',
      value: `${summary.online} / ${summary.total}`,
      icon: Wifi,
      color: 'text-green-500',
    },
    {
      title: '실행중 태스크',
      value: summary.running_tasks,
      icon: Activity,
      color: 'text-blue-500',
    },
    {
      title: '오늘 처리 완료',
      value: summary.completed_today,
      icon: CheckCircle2,
      color: 'text-emerald-500',
    },
  ]

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div className='mb-2 flex flex-wrap items-center justify-between space-y-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>워커</h2>
            <p className='text-muted-foreground'>
              워커 PC 상태 및 관리
            </p>
          </div>
          <Button onClick={() => setAddDialogOpen(true)}>
            <Plus className='mr-2 h-4 w-4' /> 워커 추가
          </Button>
          <WorkerAddDialog
            open={addDialogOpen}
            onOpenChange={setAddDialogOpen}
            onCreated={loadWorkers}
          />
        </div>

        {/* Summary cards */}
        <div className='mb-6 grid gap-4 sm:grid-cols-3'>
          {summaryCards.map((card) => (
            <Card key={card.title}>
              <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                <CardTitle className='text-sm font-medium'>
                  {card.title}
                </CardTitle>
                <card.icon className={`h-4 w-4 ${card.color}`} />
              </CardHeader>
              <CardContent>
                <div className='text-2xl font-bold'>{card.value}</div>
              </CardContent>
            </Card>
          ))}
        </div>

        {/* Worker cards */}
        {workers.length === 0 ? (
          <Card>
            <CardContent className='flex items-center justify-center py-10'>
              <p className='text-muted-foreground'>
                등록된 워커가 없습니다. 서버 연결 후 표시됩니다.
              </p>
            </CardContent>
          </Card>
        ) : (
          <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
            {workers.map((worker) => (
              <Card
                key={worker.id}
                className='cursor-pointer transition-colors hover:border-primary'
              >
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <div className='flex items-center gap-2'>
                    <Monitor className='h-5 w-5 text-muted-foreground' />
                    <CardTitle className='text-base'>{worker.name}</CardTitle>
                  </div>
                  <div className='flex items-center gap-2'>
                    {statusIcon(worker.status)}
                    <Badge variant={statusBadgeVariant(worker.status)}>
                      {worker.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent className='space-y-2'>
                  <div className='flex items-center justify-between text-sm'>
                    <span className='text-muted-foreground'>마지막 하트비트</span>
                    <span>
                      {worker.last_heartbeat
                        ? new Date(worker.last_heartbeat).toLocaleString('ko')
                        : '-'}
                    </span>
                  </div>
                  <div className='flex items-center justify-between text-sm'>
                    <span className='text-muted-foreground'>버전</span>
                    <span>{worker.version || '-'}</span>
                  </div>
                  <div className='flex items-center justify-between text-sm'>
                    <span className='text-muted-foreground'>OS</span>
                    <span>{worker.os_type || '-'}</span>
                  </div>
                  <div className='flex items-center justify-between text-sm'>
                    <span className='text-muted-foreground'>실행중 태스크</span>
                    <Badge variant='outline'>{worker.running_tasks}</Badge>
                  </div>
                  <div className='flex items-center justify-between text-sm'>
                    <span className='text-muted-foreground'>
                      <Lock className='mr-1 inline h-3 w-3' />
                      프로필 잠금
                    </span>
                    <Badge variant='outline'>{worker.locked_profiles}개</Badge>
                  </div>
                  <div className='flex items-center gap-1 pt-1'>
                    {worker.allow_preparation && (
                      <Badge variant='secondary' className='text-xs'>
                        준비
                      </Badge>
                    )}
                    {worker.allow_campaign && (
                      <Badge variant='secondary' className='text-xs'>
                        캠페인
                      </Badge>
                    )}
                  </div>
                  <div className='pt-2'>
                    {worker.status === 'online' && (
                      <Button
                        variant='outline'
                        size='sm'
                        className='w-full'
                        onClick={async (e) => {
                          e.stopPropagation()
                          try {
                            await fetchApi(
                              `/api/workers/${worker.id}/pause`,
                              { method: 'POST' }
                            )
                            loadWorkers()
                          } catch {
                            // silently handled
                          }
                        }}
                      >
                        <Pause className='mr-1 h-3 w-3' /> 일시정지
                      </Button>
                    )}
                    {worker.status === 'paused' && (
                      <Button
                        variant='outline'
                        size='sm'
                        className='w-full'
                        onClick={async (e) => {
                          e.stopPropagation()
                          try {
                            await fetchApi(
                              `/api/workers/${worker.id}/resume`,
                              { method: 'POST' }
                            )
                            loadWorkers()
                          } catch {
                            // silently handled
                          }
                        }}
                      >
                        <Wifi className='mr-1 h-3 w-3' /> 재개
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </Main>
    </>
  )
}
