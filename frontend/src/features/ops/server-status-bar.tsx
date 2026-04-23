import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Play, Rocket } from 'lucide-react'
import axios from 'axios'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

type ServerConfig = {
  current_version: string
  paused: boolean
  canary_worker_ids: number[]
}

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

function authed<T>(fn: () => Promise<T>) {
  return fn()
}

async function fetchServerConfig(): Promise<ServerConfig> {
  const r = await axios.get(`${API_BASE}/api/admin/server-config`)
  return r.data
}

async function postPause() {
  return (await axios.post(`${API_BASE}/api/admin/pause`)).data
}
async function postUnpause() {
  return (await axios.post(`${API_BASE}/api/admin/unpause`)).data
}
async function postDeploy() {
  return (await axios.post(`${API_BASE}/api/admin/deploy`)).data
}

export function ServerStatusBar() {
  const qc = useQueryClient()
  const { data } = useQuery({
    queryKey: ['server-config'],
    queryFn: () => authed(fetchServerConfig),
    refetchInterval: 10_000,
  })

  const pause = useMutation({
    mutationFn: postPause,
    onSuccess: () => {
      toast.success('긴급 정지 활성화')
      qc.invalidateQueries({ queryKey: ['server-config'] })
    },
    onError: () => toast.error('정지 실패'),
  })

  const unpause = useMutation({
    mutationFn: postUnpause,
    onSuccess: () => {
      toast.success('재개')
      qc.invalidateQueries({ queryKey: ['server-config'] })
    },
    onError: () => toast.error('재개 실패'),
  })

  const deploy = useMutation({
    mutationFn: postDeploy,
    onSuccess: (res) => {
      toast.success(`배포 시작 — pid=${res.pid}`)
      // 배포 완료까지 수 분. 몇 초 후 상태 한 번 갱신.
      setTimeout(
        () => qc.invalidateQueries({ queryKey: ['server-config'] }),
        8000,
      )
    },
    onError: () => toast.error('배포 시작 실패'),
  })

  if (!data) return null

  const paused = data.paused

  return (
    <div
      className={cn(
        'flex flex-col gap-3 rounded-lg border p-3 sm:flex-row sm:items-center sm:gap-4',
        paused
          ? 'border-destructive/40 bg-destructive/5'
          : 'border-border bg-card',
      )}
    >
      {paused ? (
        <div className='flex flex-1 items-center gap-2 text-destructive'>
          <AlertTriangle className='h-5 w-5 shrink-0' />
          <span className='font-medium'>전체 워커 일시정지 중</span>
        </div>
      ) : (
        <div className='flex-1 text-sm text-muted-foreground'>
          정상 운영 중 · 버전{' '}
          <span className='font-mono text-foreground'>
            {data.current_version || 'v0'}
          </span>
          {data.canary_worker_ids.length > 0 && (
            <span className='ml-2 text-xs'>
              · canary: {data.canary_worker_ids.join(', ')}
            </span>
          )}
        </div>
      )}

      <div className='flex gap-2'>
        {paused ? (
          <Button
            size='sm'
            onClick={() => unpause.mutate()}
            disabled={unpause.isPending}
            className='min-h-[40px]'
          >
            <Play className='h-4 w-4' />
            재개
          </Button>
        ) : (
          <Button
            size='sm'
            variant='destructive'
            onClick={() => pause.mutate()}
            disabled={pause.isPending}
            className='min-h-[40px]'
          >
            <AlertTriangle className='h-4 w-4' />
            긴급 정지
          </Button>
        )}

        <Button
          size='sm'
          variant='secondary'
          onClick={() => {
            if (
              window.confirm(
                '배포를 시작합니다 — git pull + 재시작. 계속할까요?',
              )
            ) {
              deploy.mutate()
            }
          }}
          disabled={deploy.isPending}
          className='min-h-[40px]'
        >
          <Rocket className='h-4 w-4' />
          {deploy.isPending ? '배포중…' : '배포'}
        </Button>
      </div>
    </div>
  )
}
