import { useState } from 'react'
import { Plus, Activity } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { WORKERS, type WorkerInfo } from '../_commex-mock'

const STORAGE_KEY = 'commex-workers-v1'

const PILL = {
  online: { cls: 'cx-pill-done', label: 'online' },
  paused: { cls: 'cx-pill-pending', label: 'paused' },
  offline: { cls: 'cx-pill-failed', label: 'offline' },
} as const

export function WorkersCommex() {
  const [workers, setWorkers] = useState<WorkerInfo[]>(loadWorkers)
  const [registerOpen, setRegisterOpen] = useState(false)
  const [workerName, setWorkerName] = useState('')
  const online = workers.filter((w) => w.status === 'online').length

  const persist = (next: WorkerInfo[]) => {
    setWorkers(next)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }
  const dryRun = () => {
    const next = workers.map((w, i) =>
      i === 0
        ? {
            ...w,
            status: 'online' as const,
            currentTask: 'dry-run 점검 완료',
            heartbeat: '방금 전',
          }
        : w
    )
    persist(next)
    toast.success('dry-run 상태를 워커 목록에 반영했습니다')
  }
  const registerWorker = () => {
    const name = workerName.trim()
    if (!name) {
      toast.warning('워커 이름을 입력하세요')
      return
    }
    persist([
      {
        id: Date.now(),
        name,
        status: 'paused',
        currentTask: '등록 대기',
        heartbeat: '방금 전',
        version: 'v2.2.1',
        os: 'mac',
      },
      ...workers,
    ])
    setWorkerName('')
    setRegisterOpen(false)
    toast.success(`${name} 워커를 등록했습니다`)
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
        <div
          className='hydra-page'
          style={{ display: 'flex', flexDirection: 'column', gap: 18 }}
        >
          <div className='flex items-end justify-between flex-wrap gap-3'>
            <div>
              <h1 className='cx-page-h'>워커</h1>
              <p className='cx-page-sub'>
                워커 heartbeat, 현재 작업, 버전 상태를 확인합니다.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className='cx-btn-soft' onClick={dryRun}>
                <Activity className='inline h-4 w-4 mr-1.5' />
                dry-run
              </button>
              <button className='cx-btn-primary' onClick={() => setRegisterOpen(true)}>
                <Plus className='inline h-4 w-4 mr-1' />
                워커 등록
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className='cx-kpi-strip four'>
            <Stat label='전체 워커' value={workers.length} />
            <Stat label='온라인' value={online} accent='green' />
            <Stat label='일시정지' value={workers.filter((w) => w.status === 'paused').length} accent='orange' />
            <Stat label='오프라인' value={workers.filter((w) => w.status === 'offline').length} accent='red' />
          </div>

          <div className='cx-card' style={{ overflow: 'hidden' }}>
            <table className='cx-table'>
              <thead>
                <tr>
                  <th style={{ paddingLeft: 18 }}>워커</th>
                  <th>상태</th>
                  <th>현재 작업</th>
                  <th>최근 heartbeat</th>
                  <th>OS</th>
                  <th style={{ paddingRight: 18 }}>버전</th>
                </tr>
              </thead>
              <tbody>
                {workers.map((w) => (
                  <tr key={w.id}>
                    <td style={{ paddingLeft: 18, fontWeight: 800, fontFamily: 'monospace', fontSize: 13 }}>
                      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                        <span
                          className={`hydra-led-${w.status === 'online' ? 'online' : w.status === 'paused' ? 'paused' : 'offline'}`}
                        />
                        {w.name}
                      </span>
                    </td>
                    <td>
                      <span className={`cx-pill ${PILL[w.status].cls}`}>
                        {PILL[w.status].label}
                      </span>
                    </td>
                    <td style={{ color: 'var(--cx-sub)' }}>{w.currentTask ?? '—'}</td>
                    <td style={{ color: 'var(--cx-sub)' }}>{w.heartbeat}</td>
                    <td style={{ color: 'var(--cx-sub)', textTransform: 'uppercase', fontSize: 12, fontWeight: 700 }}>
                      {w.os}
                    </td>
                    <td style={{ paddingRight: 18, fontFamily: 'monospace', fontSize: 12, color: 'var(--cx-sub)' }}>
                      {w.version}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {registerOpen && (
            <div
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 60,
                background: 'rgba(15,23,42,0.35)',
                display: 'grid',
                placeItems: 'center',
                padding: 20,
              }}
              onClick={() => setRegisterOpen(false)}
            >
              <div
                className='cx-card cx-card-pad'
                style={{ width: 'min(420px, 100%)', display: 'flex', flexDirection: 'column', gap: 14 }}
                onClick={(e) => e.stopPropagation()}
              >
                <div className='cx-section-head'>
                  <div className='cx-section-title'>워커 등록</div>
                  <button className='cx-btn-mini' onClick={() => setRegisterOpen(false)}>
                    닫기
                  </button>
                </div>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--cx-sub)', fontWeight: 800 }}>
                    워커 이름
                  </span>
                  <input
                    className='cx-input'
                    value={workerName}
                    onChange={(e) => setWorkerName(e.target.value)}
                    autoFocus
                    placeholder='예: worker-06'
                  />
                </label>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button className='cx-btn-soft' onClick={() => setRegisterOpen(false)}>
                    취소
                  </button>
                  <button className='cx-btn-primary' onClick={registerWorker}>
                    등록
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Main>
    </>
  )
}

function loadWorkers(): WorkerInfo[] {
  if (typeof window === 'undefined') return WORKERS
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return WORKERS
  try {
    return JSON.parse(raw) as WorkerInfo[]
  } catch {
    return WORKERS
  }
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string
  value: number
  accent?: 'green' | 'orange' | 'red'
}) {
  const color = accent === 'green' ? 'var(--cx-green)' : accent === 'orange' ? '#ff9f43' : accent === 'red' ? 'var(--cx-red)' : 'var(--cx-text)'
  return (
    <div className='cx-kpi'>
      <span className='cx-kpi-label'>{label}</span>
      <div className='cx-kpi-value' style={{ color }}>
        {value}
      </div>
    </div>
  )
}

export default WorkersCommex
