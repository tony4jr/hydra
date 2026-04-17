import { useEffect, useState } from 'react'
import { Plus, Pause, Play, Lock, Monitor } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { useCountUp } from '@/hooks/use-count-up'
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
  const [workers, setWorkers] = useState<Worker[]>([])
  const [loading, setLoading] = useState(true)

  const loadWorkers = () => {
    setLoading(true)
    fetchApi<Worker[]>('/api/workers/')
      .then(data => setWorkers(Array.isArray(data) ? data : []))
      .catch(() => setWorkers([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadWorkers() }, [])

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
                    {isOffline ? (
                      <p className='text-muted-foreground text-[12px]'>워커가 오프라인입니다. PC 연결을 확인하세요.</p>
                    ) : (
                      <div>
                        {worker.status === 'online' && (
                          <Button variant='outline' size='sm' className='w-full hydra-btn-press' onClick={() => handlePause(worker.id)}>
                            <Pause className='mr-1 h-3 w-3' /> 일시정지
                          </Button>
                        )}
                        {worker.status === 'paused' && (
                          <Button variant='outline' size='sm' className='w-full hydra-btn-press' onClick={() => handleResume(worker.id)}>
                            <Play className='mr-1 h-3 w-3' /> 재개
                          </Button>
                        )}
                      </div>
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
    </>
  )
}
