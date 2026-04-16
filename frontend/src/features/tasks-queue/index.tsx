import { useEffect, useState } from 'react'
import {
  Clock,
  Loader2,
  CheckCircle2,
  XCircle,
  Pause,
  Ban,
} from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'

interface Task {
  id: number
  task_type: string
  priority: string
  status: string
  worker_name: string | null
  scheduled_at: string | null
  created_at: string
}

interface TaskStats {
  pending: number
  running: number
  completed: number
  failed: number
}

const priorityColor = (p: string) => {
  switch (p) {
    case 'urgent':
      return 'destructive' as const
    case 'high':
      return 'default' as const
    case 'normal':
      return 'secondary' as const
    case 'low':
      return 'outline' as const
    default:
      return 'secondary' as const
  }
}

const statusColor = (s: string) => {
  switch (s) {
    case 'pending':
      return 'outline' as const
    case 'running':
      return 'default' as const
    case 'completed':
      return 'secondary' as const
    case 'failed':
      return 'destructive' as const
    default:
      return 'secondary' as const
  }
}

const statusLabel = (s: string) => {
  switch (s) {
    case 'pending':
      return '대기'
    case 'running':
      return '진행중'
    case 'completed':
      return '완료'
    case 'failed':
      return '실패'
    default:
      return s
  }
}

export default function TasksQueuePage() {
  const [tasks, setTasks] = useState<Task[]>([])
  const [stats, setStats] = useState<TaskStats>({
    pending: 0,
    running: 0,
    completed: 0,
    failed: 0,
  })

  useEffect(() => {
    fetchApi<{ items: Task[]; stats: TaskStats }>('/api/tasks/queue')
      .then((data) => {
        setTasks(data.items || [])
        setStats(
          data.stats || { pending: 0, running: 0, completed: 0, failed: 0 }
        )
      })
      .catch(() => {})
  }, [])

  const statCards = [
    {
      title: '대기',
      value: stats.pending,
      icon: Clock,
      color: 'text-muted-foreground',
    },
    {
      title: '진행중',
      value: stats.running,
      icon: Loader2,
      color: 'text-blue-500',
    },
    {
      title: '완료',
      value: stats.completed,
      icon: CheckCircle2,
      color: 'text-green-500',
    },
    {
      title: '실패',
      value: stats.failed,
      icon: XCircle,
      color: 'text-red-500',
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
            <h2 className='text-2xl font-bold tracking-tight'>작업 큐</h2>
            <p className='text-muted-foreground'>
              실시간 작업 대기열 및 진행 상태
            </p>
          </div>
          <div className='flex gap-2'>
            <Button variant='outline'>
              <Pause className='mr-2 h-4 w-4' /> 일시정지
            </Button>
            <Button variant='outline'>
              <Ban className='mr-2 h-4 w-4' /> 전체 취소
            </Button>
          </div>
        </div>

        {/* Stat cards */}
        <div className='mb-6 grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
          {statCards.map((card) => (
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

        {/* Task table */}
        <Card>
          <CardContent className='p-0'>
            <div className='overflow-auto'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='border-b bg-muted/50'>
                    <th className='p-3 text-left font-medium'>ID</th>
                    <th className='p-3 text-left font-medium'>유형</th>
                    <th className='p-3 text-center font-medium'>우선순위</th>
                    <th className='p-3 text-center font-medium'>상태</th>
                    <th className='p-3 text-left font-medium'>Worker</th>
                    <th className='p-3 text-right font-medium'>생성시간</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        className='p-10 text-center text-muted-foreground'
                      >
                        대기 중인 작업이 없습니다. 서버 연결 후 표시됩니다.
                      </td>
                    </tr>
                  ) : (
                    tasks.map((task) => (
                      <tr
                        key={task.id}
                        className='cursor-pointer border-b hover:bg-muted/50'
                      >
                        <td className='p-3 font-mono text-xs'>#{task.id}</td>
                        <td className='p-3'>{task.task_type}</td>
                        <td className='p-3 text-center'>
                          <Badge variant={priorityColor(task.priority)}>
                            {task.priority}
                          </Badge>
                        </td>
                        <td className='p-3 text-center'>
                          <Badge variant={statusColor(task.status)}>
                            {statusLabel(task.status)}
                          </Badge>
                        </td>
                        <td className='p-3'>
                          {task.worker_name || (
                            <span className='text-muted-foreground'>-</span>
                          )}
                        </td>
                        <td className='p-3 text-right text-muted-foreground'>
                          {task.created_at
                            ? new Date(task.created_at).toLocaleString('ko')
                            : '-'}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
