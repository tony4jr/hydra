import { Plus, Activity } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { WORKERS } from '../_commex-mock'

const PILL = {
  online: { cls: 'cx-pill-done', label: 'online' },
  paused: { cls: 'cx-pill-pending', label: 'paused' },
  offline: { cls: 'cx-pill-failed', label: 'offline' },
} as const

export function WorkersCommex() {
  const online = WORKERS.filter((w) => w.status === 'online').length

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
              <button className='cx-btn-soft' onClick={() => toast.info('dry-run 시작 (예정)')}>
                <Activity className='inline h-4 w-4 mr-1.5' />
                dry-run
              </button>
              <button className='cx-btn-primary' onClick={() => toast.success('워커 등록 (예정)')}>
                <Plus className='inline h-4 w-4 mr-1' />
                워커 등록
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className='cx-kpi-strip four'>
            <Stat label='전체 워커' value={WORKERS.length} />
            <Stat label='온라인' value={online} accent='green' />
            <Stat label='일시정지' value={WORKERS.filter((w) => w.status === 'paused').length} accent='orange' />
            <Stat label='오프라인' value={WORKERS.filter((w) => w.status === 'offline').length} accent='red' />
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
                {WORKERS.map((w) => (
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
        </div>
      </Main>
    </>
  )
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
