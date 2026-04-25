import { useEffect, useState } from 'react'
import { Plus, Pause, Play, Lock, Monitor, Pencil, MoreVertical } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuTrigger, DropdownMenuSeparator, DropdownMenuLabel,
} from '@/components/ui/dropdown-menu'
import { toast } from 'sonner'
import { Skeleton } from '@/components/ui/skeleton'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { useCountUp } from '@/hooks/use-count-up'
import { WorkerAddDialog } from './worker-add-dialog'
import { WorkerEditDialog } from './worker-edit-dialog'

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
  allowed_task_types?: string[]
  paused_reason?: string | null
  consecutive_failures?: number
  current_task?: {
    id: number
    task_type: string
    started_at?: string | null
  } | null
}

function SummaryCard({ label, value, sub }: { label: string; value: number; sub?: string }) {
  const animated = useCountUp(value)
  return (
    <div className='bg-card rounded-xl border border-border p-4'>
      <span className='text-muted-foreground text-[12px]'>{label}</span>
      <div className='text-[28px] font-bold'>{animated}</div>
      {sub && <span className='text-muted-foreground text-[11px]'>{sub}</span>}
    </div>
  )
}

export default function WorkersPage() {
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [editWorker, setEditWorker] = useState<Worker | null>(null)
  const [workers, setWorkers] = useState<Worker[]>([])
  const [loading, setLoading] = useState(true)

  const loadWorkers = () => {
    setLoading(true)
    // Task 39: /api/admin/workers/ 가 allowed_task_types 포함. 기존 legacy 는
    // running_tasks/locked_profiles 를 조인해서 주니 둘 다 받아 병합.
    Promise.all([
      fetchApi<Worker[]>('/api/admin/workers/').catch(() => []),
      fetchApi<Worker[]>('/api/workers/').catch(() => []),
    ])
      .then(([adminList, legacyList]) => {
        const byId = new Map<number, Worker>()
        for (const w of adminList) byId.set(w.id, { ...w, locked_profiles: 0, running_tasks: 0 })
        for (const w of legacyList) {
          const existing = byId.get(w.id) || w
          byId.set(w.id, { ...existing, ...w, allowed_task_types: existing.allowed_task_types })
        }
        setWorkers(Array.from(byId.values()).sort((a, b) => a.id - b.id))
      })
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadWorkers()
    const id = setInterval(loadWorkers, 3_000)
    return () => clearInterval(id)
  }, [])

  const onlineCount = workers.filter(w => w.status === 'online').length
  const totalTasks = workers.reduce((sum, w) => sum + (w.running_tasks || 0), 0)

  const handlePause = async (id: number) => {
    try {
      await fetchApi(`/api/workers/${id}/pause`, { method: 'POST' })
      loadWorkers()
    } catch { /* error */ }
  }

  const handleResume = async (id: number) => {
    try {
      await fetchApi(`/api/workers/${id}/resume`, { method: 'POST' })
      loadWorkers()
    } catch { /* error */ }
  }

  const sendCommand = async (workerId: number, command: string) => {
    try {
      await fetchApi(`/api/admin/workers/${workerId}/command`, {
        method: 'POST',
        body: JSON.stringify({ command }),
        headers: { 'Content-Type': 'application/json' },
      })
      toast.success(`명령 발행: ${command}`, {
        description: '워커 다음 heartbeat 시 실행됩니다.',
      })
    } catch (e) {
      toast.error('명령 발행 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    }
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
        <div >
          <div className='mb-5 flex flex-wrap items-center justify-between gap-2'>
            <div>
              <h2 className='text-[22px] font-bold'>워커</h2>
              <p className='text-muted-foreground text-[13px]'>Worker PC 상태 관제 및 관리</p>
            </div>
            <Button onClick={() => setAddDialogOpen(true)} className='hydra-btn-press'>
              <Plus className='mr-2 h-4 w-4' /> 워커 추가
            </Button>
          </div>

          {/* Summary */}
          {loading ? (
            <div className='grid grid-cols-3 gap-3 mb-5'>
              {[1, 2, 3].map(i => <Skeleton key={i} className='h-24 rounded-xl' />)}
            </div>
          ) : (
            <div className='grid grid-cols-3 gap-3 mb-5'>
              <SummaryCard label='온라인' value={onlineCount} sub={`전체 ${workers.length}대`} />
              <SummaryCard label='실행중 태스크' value={totalTasks} />
              <SummaryCard label='등록된 워커' value={workers.length} />
            </div>
          )}

          {/* Worker cards */}
          {loading ? (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {[1, 2].map(i => <Skeleton key={i} className='h-48 rounded-xl' />)}
            </div>
          ) : workers.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <Monitor className='h-10 w-10 text-muted-foreground/30 mx-auto mb-3' />
              <p className='text-muted-foreground text-[14px] mb-1'>등록된 워커가 없어요</p>
              <p className='text-muted-foreground/60 text-[12px] mb-4'>워커 PC를 연결해서 작업을 시작하세요</p>
              <Button onClick={() => setAddDialogOpen(true)} variant='outline' className='hydra-btn-press'>
                <Plus className='mr-2 h-4 w-4' /> 워커 추가
              </Button>
            </div>
          ) : (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {workers.map(worker => {
                const isOffline = worker.status === 'offline'
                return (
                  <div
                    key={worker.id}
                    className={`bg-card border border-border rounded-xl p-5 hydra-card-hover ${isOffline ? 'opacity-50' : ''}`}
                  >
                    {/* Header */}
                    <div className='flex items-center justify-between mb-3'>
                      <div className='flex items-center gap-2.5'>
                        <div className={`hydra-led-${worker.status === 'online' ? 'online' : worker.status === 'paused' ? 'paused' : 'offline'}`} />
                        <span className='text-foreground font-semibold text-[15px]'>{worker.name}</span>
                      </div>
                      <span className={`hydra-tag ${
                        worker.status === 'online' ? 'hydra-tag-success' :
                        worker.status === 'paused' ? 'hydra-tag-warning' : 'hydra-tag-muted'
                      }`}>
                        {worker.status === 'online' ? '온라인' : worker.status === 'paused' ? '일시정지' : '오프라인'}
                      </span>
                    </div>

                    {/* Info rows */}
                    <div className='space-y-1.5 text-[13px] mb-3'>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>OS / 버전</span>
                        <span>{worker.os_type || '-'} / {worker.version || '-'}</span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>현재 태스크</span>
                        <span className='font-mono text-[12px]'>
                          {worker.current_task
                            ? `#${worker.current_task.id} · ${worker.current_task.task_type}`
                            : '-'}
                        </span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>실행중 태스크</span>
                        <span className='font-medium'>{worker.running_tasks}</span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>
                          <Lock className='inline h-3 w-3 mr-0.5' />프로필 잠금
                        </span>
                        <span>{worker.locked_profiles}개</span>
                      </div>
                      <div className='flex justify-between'>
                        <span className='text-muted-foreground'>마지막 통신</span>
                        <span className='text-[12px]'>
                          {worker.last_heartbeat ? new Date(worker.last_heartbeat).toLocaleString('ko') : '-'}
                        </span>
                      </div>
                    </div>

                    {/* Role badges */}
                    <div className='flex items-center gap-1.5 mb-3'>
                      {worker.allow_preparation && <span className='hydra-tag hydra-tag-blue'>준비</span>}
                      {worker.allow_campaign && <span className='hydra-tag hydra-tag-primary'>캠페인</span>}
                      {!worker.allow_preparation && !worker.allow_campaign && (
                        <span className='hydra-tag hydra-tag-muted'>역할 미지정</span>
                      )}
                    </div>

                    {/* Actions */}
                    <div className='flex gap-2'>
                      <Button
                        variant='outline'
                        size='sm'
                        className='flex-1 hydra-btn-press'
                        onClick={() => setEditWorker(worker)}
                      >
                        <Pencil className='mr-1 h-3 w-3' /> 편집
                      </Button>
                      {!isOffline && worker.status === 'online' && (
                        <Button variant='outline' size='sm' className='flex-1 hydra-btn-press' onClick={() => handlePause(worker.id)}>
                          <Pause className='mr-1 h-3 w-3' /> 일시정지
                        </Button>
                      )}
                      {!isOffline && worker.status === 'paused' && (
                        <Button variant='outline' size='sm' className='flex-1 hydra-btn-press' onClick={() => handleResume(worker.id)}>
                          <Play className='mr-1 h-3 w-3' /> 재개
                        </Button>
                      )}
                      <DropdownMenu>
                        <DropdownMenuTrigger asChild>
                          <Button variant='outline' size='sm' className='hydra-btn-press' aria-label='원격 명령'>
                            <MoreVertical className='h-3 w-3' />
                          </Button>
                        </DropdownMenuTrigger>
                        <DropdownMenuContent align='end'>
                          <DropdownMenuLabel>원격 명령</DropdownMenuLabel>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => sendCommand(worker.id, 'restart')}>재시작</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => sendCommand(worker.id, 'update_now')}>최신 코드로 업데이트</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => sendCommand(worker.id, 'run_diag')}>진단 실행</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => sendCommand(worker.id, 'screenshot_now')}>스크린샷 캡처</DropdownMenuItem>
                          <DropdownMenuSeparator />
                          <DropdownMenuItem onClick={() => sendCommand(worker.id, 'stop_all_browsers')}>모든 브라우저 종료</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => sendCommand(worker.id, 'update_adspower_patch')}>AdsPower 패치 업데이트</DropdownMenuItem>
                          <DropdownMenuItem onClick={() => sendCommand(worker.id, 'refresh_fingerprint')}>FP 재생성</DropdownMenuItem>
                        </DropdownMenuContent>
                      </DropdownMenu>
                    </div>
                    {isOffline && (
                      <p className='text-muted-foreground text-[11px] mt-2'>오프라인 — PC 연결을 확인하세요</p>
                    )}
                    {worker.status === 'paused' && worker.paused_reason && (
                      <p className='text-yellow-600 dark:text-yellow-400 text-[11px] mt-2'>
                        ⚠️ {worker.paused_reason}
                      </p>
                    )}
                    {(worker.consecutive_failures || 0) > 0 && (
                      <p className='text-orange-600 dark:text-orange-400 text-[11px] mt-1'>
                        연속 실패 {worker.consecutive_failures}회
                      </p>
                    )}
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </Main>

      <WorkerAddDialog
        open={addDialogOpen}
        onOpenChange={setAddDialogOpen}
        onCreated={loadWorkers}
      />
      <WorkerEditDialog
        open={editWorker !== null}
        onOpenChange={(v) => !v && setEditWorker(null)}
        worker={
          editWorker
            ? {
                id: editWorker.id,
                name: editWorker.name,
                allowed_task_types: editWorker.allowed_task_types || ['*'],
                allow_preparation: editWorker.allow_preparation,
                allow_campaign: editWorker.allow_campaign,
              }
            : null
        }
        onSaved={loadWorkers}
      />
    </>
  )
}
