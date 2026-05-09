import { Plus, Edit3, Copy } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { useCommexStore } from '../_commex-store'

export function CampaignsCommex() {
  const jobs = useCommexStore((s) => s.autoJobs)
  const queue = useCommexStore((s) => s.queue)
  const videos = useCommexStore((s) => s.videos)
  const toggleStore = useCommexStore((s) => s.toggleAutoJob)

  const active = jobs.filter((j) => j.active).length
  const todayDrafts = queue.filter((q) => q.status === 'draft').length
  const todayCollected = videos.length

  const toggle = (id: string) => {
    toggleStore(id)
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
              <h1 className='cx-page-h'>자동 작업</h1>
              <p className='cx-page-sub'>
                브랜드와 니치 기준으로 수집부터 댓글 초안 생성까지 반복 작업을 자동화합니다.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className='cx-btn-soft' onClick={() => toast.info('템플릿 복제는 다음 단계에 연결됩니다')}>
                <Copy className='inline h-4 w-4 mr-1.5' />
                템플릿 복제
              </button>
              <button className='cx-btn-primary' onClick={() => toast.success('새 자동 작업 만들기 모달 (예정)')}>
                <Plus className='inline h-4 w-4 mr-1' />새 자동 작업
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className='cx-kpi-strip four'>
            <MiniStat label='활성 자동 작업' value={active} />
            <MiniStat label='오늘 수집 영상' value={todayCollected} />
            <MiniStat label='오늘 생성 초안' value={todayDrafts} />
            <MiniStat label='다음 예약 실행' value='14:00' />
          </div>

          {/* Auto job list */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            {jobs.map((j) => (
              <div
                key={j.id}
                className='cx-card cx-card-pad'
                style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 16 }}
              >
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 6 }}>
                    <h4 style={{ margin: 0, fontSize: 16, fontWeight: 800, color: 'var(--cx-text)' }}>
                      {j.brand} · {j.niche}
                    </h4>
                    {j.active && (
                      <span className='cx-pill cx-pill-done'>실행 중</span>
                    )}
                  </div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 14, fontSize: 12, color: 'var(--cx-sub)' }}>
                    <span>키워드: {j.keywords.join(', ')}</span>
                    <span>· {j.limit}</span>
                    <span>· {j.time}</span>
                    <span>· 다음 실행 <b style={{ color: 'var(--cx-primary)' }}>{j.nextRun}</b></span>
                    <span>· 마지막 {j.lastRun}</span>
                  </div>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
                  <Toggle on={j.active} onClick={() => toggle(j.id)} />
                  <button className='cx-btn-soft' style={{ height: 38 }}>
                    <Edit3 className='inline h-4 w-4 mr-1.5' />
                    편집
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </Main>
    </>
  )
}

function MiniStat({ label, value }: { label: string; value: number | string }) {
  return (
    <div className='cx-kpi'>
      <span className='cx-kpi-label'>{label}</span>
      <div className='cx-kpi-value'>{value}</div>
    </div>
  )
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: 44,
        height: 26,
        borderRadius: 999,
        border: 'none',
        cursor: 'pointer',
        position: 'relative',
        background: on
          ? 'linear-gradient(135deg,#5e74ff,#6d5cff)'
          : '#d7dff1',
        transition: 'background 0.18s ease',
      }}
      aria-pressed={on}
    >
      <span
        style={{
          position: 'absolute',
          top: 3,
          left: on ? 21 : 3,
          width: 20,
          height: 20,
          borderRadius: '50%',
          background: '#fff',
          boxShadow: '0 2px 6px rgba(0,0,0,0.15)',
          transition: 'left 0.18s ease',
        }}
      />
    </button>
  )
}

export default CampaignsCommex
