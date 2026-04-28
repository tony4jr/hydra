import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { AlertTriangle, FileText, Play, Rocket } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog, DialogContent, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { cn } from '@/lib/utils'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

type ServerConfig = {
  current_version: string
  paused: boolean
  canary_worker_ids: number[]
}

// fetchApi 를 사용해야 axios 인스턴스 인터셉터로 JWT 가 자동 주입된다.
// 직접 axios.get() 쓰면 Authorization 헤더 없이 호출되어 401 → data 없어 바 숨겨짐 버그.
async function fetchServerConfig(): Promise<ServerConfig> {
  return fetchApi<ServerConfig>('/api/admin/server-config')
}

async function postPause() {
  return fetchApi<{ paused: boolean }>('/api/admin/pause', { method: 'POST' })
}
async function postUnpause() {
  return fetchApi<{ paused: boolean }>('/api/admin/unpause', { method: 'POST' })
}
async function postEmergencyStop() {
  return fetchApi<{ paused: boolean; emergency: boolean; workers_notified: number }>(
    '/api/admin/emergency-stop', { method: 'POST' },
  )
}
async function postDeploy() {
  return fetchApi<{ started: boolean; unit: string }>('/api/admin/deploy', {
    method: 'POST',
  })
}

type DeployStatus = {
  active: string
  result: string
  exit_code: string
  last_run_started: string
  last_run_ended: string
}

async function fetchDeployStatus(): Promise<DeployStatus> {
  return fetchApi<DeployStatus>('/api/admin/deploy/status')
}
async function fetchDeployLog(): Promise<{ source: string; lines: string }> {
  return fetchApi<{ source: string; lines: string }>('/api/admin/deploy/log?lines=300')
}

export function ServerStatusBar() {
  const qc = useQueryClient()
  const [logOpen, setLogOpen] = useState(false)
  const { data } = useQuery({
    queryKey: ['server-config'],
    queryFn: fetchServerConfig,
    refetchInterval: 10_000,
  })

  const { data: deployStatus, refetch: refetchStatus } = useQuery({
    queryKey: ['deploy-status'],
    queryFn: fetchDeployStatus,
    refetchInterval: logOpen ? 3_000 : false,
    enabled: logOpen,
  })
  const { data: deployLog, refetch: refetchLog } = useQuery({
    queryKey: ['deploy-log'],
    queryFn: fetchDeployLog,
    refetchInterval: logOpen ? 3_000 : false,
    enabled: logOpen,
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

  const emergency = useMutation({
    mutationFn: postEmergencyStop,
    onSuccess: (res) => {
      toast.warning(`🚨 비상정지 — ${res.workers_notified}대 워커 정지`, {
        description: '모든 브라우저 즉시 종료. 재개 시 수동 명령 필요.',
      })
      qc.invalidateQueries({ queryKey: ['server-config'] })
    },
    onError: () => toast.error('비상정지 실패'),
  })

  const deploy = useMutation({
    mutationFn: postDeploy,
    onSuccess: (res) => {
      toast.success(`배포 시작 — ${res.unit}`)
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
          <>
            <Button
              size='sm'
              variant='outline'
              onClick={() => pause.mutate()}
              disabled={pause.isPending}
              className='min-h-[40px]'
            >
              <AlertTriangle className='h-4 w-4' />
              일시정지
            </Button>
            <Button
              size='sm'
              variant='destructive'
              onClick={() => {
                if (window.confirm('🚨 비상정지: 모든 워커 + 브라우저 즉시 종료. 정말 진행?')) {
                  emergency.mutate()
                }
              }}
              disabled={emergency.isPending}
              className='min-h-[40px]'
            >
              <AlertTriangle className='h-4 w-4' />
              비상정지
            </Button>
          </>
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

        <Button
          size='sm'
          variant='outline'
          onClick={() => { setLogOpen(true); refetchStatus(); refetchLog() }}
          className='min-h-[40px]'
          title='배포 로그 보기'
        >
          <FileText className='h-4 w-4' />
          로그
        </Button>
      </div>

      <Dialog open={logOpen} onOpenChange={setLogOpen}>
        <DialogContent className='max-w-3xl'>
          <DialogHeader>
            <DialogTitle>배포 로그</DialogTitle>
          </DialogHeader>
          {deployStatus && (
            <div className='flex gap-3 text-xs flex-wrap mb-2'>
              <span className={cn(
                'px-2 py-1 rounded-md',
                deployStatus.active === 'active' || deployStatus.active === 'activating'
                  ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400'
                  : deployStatus.result === 'success'
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
                  : 'bg-red-500/15 text-red-600 dark:text-red-400'
              )}>
                상태: {deployStatus.active}
              </span>
              <span className='px-2 py-1 rounded-md bg-muted'>결과: {deployStatus.result || '—'}</span>
              <span className='px-2 py-1 rounded-md bg-muted'>exit: {deployStatus.exit_code || '—'}</span>
              {deployStatus.last_run_started && (
                <span className='px-2 py-1 rounded-md bg-muted'>
                  시작: {deployStatus.last_run_started.split(' ').slice(0, 2).join(' ')}
                </span>
              )}
            </div>
          )}
          <pre className='bg-zinc-950 text-zinc-100 text-[11px] leading-snug rounded-md p-3 overflow-auto max-h-[60vh] font-mono whitespace-pre-wrap'>
            {deployLog?.lines || '(로그 로딩 중…)'}
          </pre>
          <div className='flex justify-end gap-2'>
            <Button size='sm' variant='outline' onClick={() => { refetchStatus(); refetchLog() }}>
              새로고침
            </Button>
            <Button size='sm' variant='ghost' onClick={() => setLogOpen(false)}>
              닫기
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
