import { Link } from '@tanstack/react-router'
import {
  Zap,
  Plus,
  ListTodo,
  MessageSquare,
  ThumbsUp,
  Layers,
  CheckCircle2,
  AlertTriangle,
  Sparkles,
  Video,
  Puzzle,
} from 'lucide-react'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { useCountUp } from '@/hooks/use-count-up'
import { PipelineFlow } from './components/PipelineFlow'
import { ActivityStream } from './components/activity-stream'
import {
  STATS,
  WORKERS as MOCK_WORKERS_FULL,
  AUTO_JOBS as MOCK_AUTO_JOBS,
  GLOBAL_PRESETS as MOCK_PRESETS_FULL,
  VIDEOS as MOCK_VIDEOS_FULL,
} from '../_commex-mock'

interface ActiveCampaign {
  id: number
  video_title: string
  brand_name: string
  scenario: string
  campaign_type: string
  status: string
  total_tasks: number
  completed_tasks: number
  worker_name?: string
}

type KpiTone = 'blue' | 'orange' | 'purple' | 'green' | 'red'

function Kpi({
  label,
  value,
  icon: Icon,
  tone,
  sub,
}: {
  label: string
  value: number
  icon: React.ElementType
  tone: KpiTone
  sub?: string
}) {
  const animated = useCountUp(value)
  return (
    <div className='cx-kpi'>
      <div className='cx-kpi-row'>
        <span className='cx-kpi-label'>{label}</span>
        <span className={`cx-kpi-circle cx-bg-${tone}`}>
          <Icon className='h-4 w-4' />
        </span>
      </div>
      <div className='cx-kpi-value'>{animated}</div>
      {sub && <div className='cx-kpi-delta'>{sub}</div>}
    </div>
  )
}

function ActionCard({
  to,
  icon: Icon,
  variant,
  title,
  desc,
}: {
  to: string
  icon: React.ElementType
  variant?: 'purple' | 'blue'
  title: string
  desc: string
}) {
  return (
    <Link to={to} className='cx-action-card'>
      <span className={`cx-action-icon ${variant ?? ''}`}>
        <Icon className='h-5 w-5' strokeWidth={2.4} />
      </span>
      <div className='cx-action-meta'>
        <h4>{title}</h4>
        <p>{desc}</p>
      </div>
    </Link>
  )
}

function SkeletonBlock({ className }: { className?: string }) {
  return <div className={`hydra-skeleton ${className || ''}`} />
}

// 공유 mock 사용 (`_commex-mock.ts`)
const MOCK_CAMPAIGNS: ActiveCampaign[] = MOCK_AUTO_JOBS.filter((j) => j.active)
  .slice(0, 4)
  .map((j, i) => {
    const total = [30, 24, 18, 32, 22][i] ?? 20
    const done = [22, 18, 18, 9, 14][i] ?? 10
    return {
      id: 100 + i,
      video_title: `${j.niche} — 자동 캠페인`,
      brand_name: j.brand,
      scenario: ['A', 'B', 'A', 'C'][i] ?? 'A',
      campaign_type: i % 2 === 0 ? 'preset' : 'direct',
      status: 'running',
      total_tasks: total,
      completed_tasks: done,
      worker_name: `worker-0${(i % 5) + 1}`,
    }
  })

const MOCK_VIDEOS = MOCK_VIDEOS_FULL.slice(0, 3).map((v, i) => ({
  id: i,
  title: v.title,
  source: v.source,
  uploaded: v.date,
  score: v.relevance,
}))

const MOCK_PRESETS = MOCK_PRESETS_FULL.slice(0, 4)

export function Dashboard() {
  const stats = STATS
  const workers = MOCK_WORKERS_FULL
  const campaigns = MOCK_CAMPAIGNS
  const loading = false

  const onlineWorkers = workers.filter((w) => w.status === 'online').length
  const errorCount = stats?.errors?.unresolved ?? 0

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>

      <Main>
        <div className='cx-page hydra-page' style={{ padding: 0 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
            {/* Page title */}
            <div className='flex items-end justify-between flex-wrap gap-3'>
              <div>
                <h1 className='cx-page-h'>댓글 작업 운영 센터</h1>
                <p className='cx-page-sub'>
                  브랜드에 맞는 댓글을 더 빠르게, 더 정확하게 운영하세요.
                </p>
              </div>
              <div style={{ color: 'var(--cx-sub)', fontSize: 13 }}>
                Worker {onlineWorkers}대 온라인 · 캠페인 {campaigns.length}개 진행 중
                {errorCount > 0 && ` · 오류 ${errorCount}건`}
              </div>
            </div>

            {/* === Hero: 3 CTAs + illustration === */}
            <div className='cx-hero'>
              <div className='cx-hero-card'>
                <h2 className='cx-hero-title'>지금 무엇을 할까요?</h2>
                <div className='cx-hero-sub'>
                  자주 쓰는 작업으로 한 번에 진입할 수 있어요.
                </div>
                <div className='cx-hero-grid'>
                  <ActionCard
                    to='/quick'
                    icon={Zap}
                    title='빠른 작업'
                    desc='지금 바로 댓글 초안을 생성'
                  />
                  <ActionCard
                    to='/campaigns'
                    icon={Plus}
                    variant='purple'
                    title='자동 작업 만들기'
                    desc='반복 작업을 자동으로 실행'
                  />
                  <ActionCard
                    to='/queue'
                    icon={ListTodo}
                    variant='blue'
                    title='작업 큐 보기'
                    desc='모든 작업 진행 상황 확인'
                  />
                </div>
              </div>

              <div className='cx-hero-card cx-hero-illu'>
                <div style={{ display: 'flex', alignItems: 'center', gap: 16 }}>
                  <div className='cx-bubble-stack'>
                    <div className='cx-bubble-1' />
                    <div className='cx-bubble-2' />
                    <div className='cx-bubble-3' />
                  </div>
                  <div>
                    <div
                      className='cx-hero-title'
                      style={{ fontSize: 18, margin: '0 0 6px' }}
                    >
                      오늘 진행 상황
                    </div>
                    <div className='cx-hero-sub' style={{ margin: 0 }}>
                      초안 생성부터 예약, 승인까지 한 화면에서.
                    </div>
                  </div>
                </div>
                <Sparkles
                  className='h-6 w-6'
                  style={{ color: 'var(--cx-primary)' }}
                />
              </div>
            </div>

            {/* === KPI strip === */}
            {loading ? (
              <div className='cx-kpi-strip'>
                {[1, 2, 3, 4, 5].map((i) => (
                  <SkeletonBlock
                    key={i}
                    className='h-[112px] rounded-[20px]'
                  />
                ))}
              </div>
            ) : (
              <div className='cx-kpi-strip'>
                <Kpi
                  label='오늘 댓글'
                  value={stats?.today?.comments ?? 0}
                  icon={MessageSquare}
                  tone='blue'
                  sub='작성 완료 기준'
                />
                <Kpi
                  label='오늘 좋아요'
                  value={stats?.today?.likes ?? 0}
                  icon={ThumbsUp}
                  tone='orange'
                  sub='부스트 포함'
                />
                <Kpi
                  label='활성 캠페인'
                  value={stats?.campaigns?.active ?? 0}
                  icon={Layers}
                  tone='purple'
                  sub={`전체 ${stats?.campaigns?.total ?? 0}개`}
                />
                <Kpi
                  label='완료 작업'
                  value={stats?.tasks?.today_completed ?? 0}
                  icon={CheckCircle2}
                  tone='green'
                  sub='오늘'
                />
                <Kpi
                  label='실패 / 주의'
                  value={(stats?.tasks?.today_failed ?? 0) + errorCount}
                  icon={AlertTriangle}
                  tone='red'
                  sub={errorCount > 0 ? '클릭해서 확인' : '문제 없음'}
                />
              </div>
            )}

            {/* === Pipeline (24h funnel) — hydra 고유 자산 유지 === */}
            <PipelineFlow />

            {/* === Top 3-col grid === */}
            <div className='cx-dashboard-grid'>
              {/* 진행 중인 캠페인 */}
              <div className='cx-card cx-card-pad'>
                <div className='cx-section-head'>
                  <div className='cx-section-title'>진행 중인 캠페인</div>
                  <Link to='/campaigns' className='cx-section-link'>
                    전체 보기
                  </Link>
                </div>
                {campaigns.length > 0 ? (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
                    {campaigns.slice(0, 4).map((c) => {
                      const progress =
                        c.total_tasks > 0
                          ? Math.round((c.completed_tasks / c.total_tasks) * 100)
                          : 0
                      return (
                        <div key={c.id}>
                          <div
                            style={{
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              marginBottom: 6,
                            }}
                          >
                            <span
                              style={{
                                fontSize: 14,
                                fontWeight: 700,
                                color: 'var(--cx-text)',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                maxWidth: 220,
                              }}
                            >
                              {c.brand_name} — {c.video_title || `#${c.id}`}
                            </span>
                            <span
                              style={{
                                fontSize: 13,
                                fontWeight: 800,
                                color:
                                  progress >= 100
                                    ? 'var(--cx-green)'
                                    : 'var(--cx-text)',
                              }}
                            >
                              {progress}%
                            </span>
                          </div>
                          <div
                            style={{
                              height: 6,
                              borderRadius: 999,
                              background: 'var(--cx-line-2)',
                              overflow: 'hidden',
                            }}
                          >
                            <div
                              style={{
                                height: '100%',
                                width: `${progress}%`,
                                background:
                                  'linear-gradient(90deg,#5169ff,#6d5cff)',
                              }}
                            />
                          </div>
                          <div
                            style={{
                              fontSize: 11,
                              color: 'var(--cx-sub)',
                              marginTop: 4,
                              display: 'flex',
                              justifyContent: 'space-between',
                            }}
                          >
                            <span>
                              {c.completed_tasks}/{c.total_tasks} 태스크
                            </span>
                            {c.worker_name && (
                              <span style={{ color: 'var(--cx-primary)' }}>
                                {c.worker_name}
                              </span>
                            )}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                ) : (
                  <EmptyBlock
                    title='진행 중인 캠페인이 없어요'
                    desc='캠페인 페이지에서 새 캠페인을 만들어보세요'
                    cta={{ to: '/campaigns', label: '캠페인 만들기' }}
                  />
                )}
              </div>

              {/* 작업 큐 요약 */}
              <div className='cx-card cx-card-pad'>
                <div className='cx-section-head'>
                  <div className='cx-section-title'>작업 큐</div>
                  <Link to='/queue' className='cx-section-link'>
                    전체 보기
                  </Link>
                </div>
                <div className='cx-tabs' style={{ marginBottom: 12 }}>
                  <button className='cx-tab active'>전체</button>
                  <button className='cx-tab'>승인 대기</button>
                  <button className='cx-tab'>예약</button>
                  <button className='cx-tab'>실패</button>
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(2, 1fr)',
                    gap: 10,
                  }}
                >
                  <QueueStat
                    label='대기'
                    value={stats?.tasks?.pending ?? 0}
                    pill='cx-pill-pending'
                  />
                  <QueueStat
                    label='실행 중'
                    value={stats?.tasks?.running ?? 0}
                    pill='cx-pill-running'
                  />
                  <QueueStat
                    label='완료'
                    value={stats?.tasks?.today_completed ?? 0}
                    pill='cx-pill-done'
                  />
                  <QueueStat
                    label='실패'
                    value={stats?.tasks?.today_failed ?? 0}
                    pill='cx-pill-failed'
                  />
                </div>
              </div>

              {/* 영상 풀 요약 */}
              <div className='cx-card cx-card-pad'>
                <div className='cx-section-head'>
                  <div className='cx-section-title'>영상 풀</div>
                  <Link to='/videos' className='cx-section-link'>
                    전체 보기
                  </Link>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
                  {MOCK_VIDEOS.map((v) => (
                    <div
                      key={v.id}
                      style={{
                        display: 'flex',
                        gap: 12,
                        alignItems: 'flex-start',
                        paddingBottom: 10,
                        borderBottom: '1px solid var(--cx-line-2)',
                      }}
                    >
                      <div
                        style={{
                          width: 64,
                          height: 42,
                          borderRadius: 10,
                          background:
                            'linear-gradient(135deg,#384e70,#132135)',
                          flexShrink: 0,
                          position: 'relative',
                        }}
                      >
                        <Video
                          className='h-4 w-4'
                          style={{
                            position: 'absolute',
                            top: '50%',
                            left: '50%',
                            transform: 'translate(-50%,-50%)',
                            color: '#fff',
                            opacity: 0.7,
                          }}
                        />
                      </div>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 700,
                            color: 'var(--cx-text)',
                            lineHeight: 1.35,
                            display: '-webkit-box',
                            WebkitLineClamp: 2,
                            WebkitBoxOrient: 'vertical',
                            overflow: 'hidden',
                          }}
                        >
                          {v.title}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: 'var(--cx-sub)',
                            marginTop: 4,
                          }}
                        >
                          {v.source} · {v.uploaded}
                        </div>
                      </div>
                      <div
                        style={{
                          fontSize: 18,
                          fontWeight: 900,
                          color:
                            v.score >= 90
                              ? 'var(--cx-green)'
                              : 'var(--cx-primary)',
                        }}
                      >
                        {v.score}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* === Bottom 3-col grid === */}
            <div className='cx-dashboard-grid bottom'>
              {/* 글로벌 프리셋 */}
              <div className='cx-card cx-card-pad'>
                <div className='cx-section-head'>
                  <div className='cx-section-title'>글로벌 프리셋</div>
                  <Link to='/presets' className='cx-section-link'>
                    전체 보기
                  </Link>
                </div>
                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '1fr 1fr',
                    gap: 10,
                  }}
                >
                  {MOCK_PRESETS.map((p, i) => {
                    const tones = ['cx-bg-purple', 'cx-bg-blue', 'cx-bg-green', 'cx-bg-orange']
                    return (
                      <div
                        key={p.id}
                        style={{
                          padding: 12,
                          borderRadius: 14,
                          border: '1px solid var(--cx-line-2)',
                          background: '#fcfdff',
                          display: 'flex',
                          flexDirection: 'column',
                          gap: 6,
                        }}
                      >
                        <div
                          style={{
                            display: 'flex',
                            justifyContent: 'space-between',
                            alignItems: 'center',
                          }}
                        >
                          <span
                            className={`cx-kpi-circle ${tones[i % 4]}`}
                            style={{ width: 28, height: 28 }}
                          >
                            <Puzzle className='h-3.5 w-3.5' />
                          </span>
                          <span
                            style={{ fontSize: 11, color: 'var(--cx-sub)' }}
                          >
                            {p.version}
                          </span>
                        </div>
                        <div
                          style={{
                            fontSize: 13,
                            fontWeight: 800,
                            color: 'var(--cx-text)',
                          }}
                        >
                          {p.name}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: 'var(--cx-sub)',
                            lineHeight: 1.4,
                          }}
                        >
                          {p.desc}
                        </div>
                        <div
                          style={{
                            fontSize: 11,
                            color: 'var(--cx-primary)',
                            fontWeight: 800,
                            marginTop: 2,
                          }}
                        >
                          {p.used.toLocaleString()}회 사용
                        </div>
                      </div>
                    )
                  })}
                </div>
              </div>

              {/* 워커 */}
              <div className='cx-card cx-card-pad'>
                <div className='cx-section-head'>
                  <div className='cx-section-title'>워커 상태</div>
                  <Link to='/workers' className='cx-section-link'>
                    관리
                  </Link>
                </div>
                {workers.length > 0 ? (
                  <div
                    style={{ display: 'flex', flexDirection: 'column', gap: 10 }}
                  >
                    {workers.slice(0, 5).map((w) => (
                      <div
                        key={w.id}
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          padding: '8px 10px',
                          borderRadius: 12,
                          background: 'var(--cx-bg-2)',
                          border: '1px solid var(--cx-line-2)',
                        }}
                      >
                        <div
                          style={{ display: 'flex', alignItems: 'center', gap: 10 }}
                        >
                          <span
                            className={`hydra-led-${
                              w.status === 'online'
                                ? 'online'
                                : w.status === 'paused'
                                  ? 'paused'
                                  : 'offline'
                            }`}
                          />
                          <span style={{ fontWeight: 700, fontSize: 13 }}>
                            {w.name}
                          </span>
                        </div>
                        <span
                          className={`cx-pill ${
                            w.status === 'online'
                              ? 'cx-pill-done'
                              : w.status === 'paused'
                                ? 'cx-pill-pending'
                                : 'cx-pill-failed'
                          }`}
                        >
                          {w.status === 'online'
                            ? '온라인'
                            : w.status === 'paused'
                              ? '일시정지'
                              : '오프라인'}
                        </span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <EmptyBlock
                    title='연결된 워커가 없어요'
                    desc='워커 PC를 연결해보세요'
                    cta={{ to: '/workers', label: '워커 추가' }}
                  />
                )}
              </div>

              {/* 실시간 활동 */}
              <div className='cx-card cx-card-pad'>
                <div className='cx-section-head'>
                  <div className='cx-section-title'>실시간 활동</div>
                  <Link to='/queue' className='cx-section-link'>
                    전체 보기
                  </Link>
                </div>
                <ActivityStream />
              </div>
            </div>
          </div>
        </div>
      </Main>
    </>
  )
}

function QueueStat({
  label,
  value,
  pill,
}: {
  label: string
  value: number
  pill: string
}) {
  const animated = useCountUp(value)
  return (
    <div
      style={{
        padding: 14,
        borderRadius: 14,
        background: 'var(--cx-bg-2)',
        border: '1px solid var(--cx-line-2)',
      }}
    >
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          marginBottom: 6,
        }}
      >
        <span style={{ fontSize: 12, fontWeight: 800, color: 'var(--cx-sub)' }}>
          {label}
        </span>
        <span className={`cx-pill ${pill}`}>{value > 0 ? '진행' : '—'}</span>
      </div>
      <div
        style={{
          fontSize: 22,
          fontWeight: 900,
          letterSpacing: '-0.02em',
          color: 'var(--cx-text)',
        }}
      >
        {animated}
      </div>
    </div>
  )
}

function EmptyBlock({
  icon: Icon,
  title,
  desc,
  cta,
}: {
  icon?: React.ElementType
  title: string
  desc: string
  cta?: { to: string; label: string }
}) {
  return (
    <div
      style={{
        padding: 24,
        border: '1px dashed var(--cx-line)',
        borderRadius: 16,
        background: 'var(--cx-bg-2)',
        textAlign: 'center',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 8,
      }}
    >
      {Icon && (
        <Icon
          className='h-8 w-8'
          style={{ color: 'var(--cx-sub-2)', marginBottom: 4 }}
        />
      )}
      <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--cx-text)' }}>
        {title}
      </div>
      <div style={{ fontSize: 12, color: 'var(--cx-sub)' }}>{desc}</div>
      {cta && (
        <Link
          to={cta.to}
          style={{
            marginTop: 6,
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '8px 14px',
            background: 'var(--cx-primary-grad)',
            color: '#fff',
            borderRadius: 12,
            fontSize: 13,
            fontWeight: 800,
            textDecoration: 'none',
            boxShadow: '0 8px 18px rgba(75,99,255,0.24)',
          }}
        >
          <Plus className='h-3.5 w-3.5' /> {cta.label}
        </Link>
      )}
    </div>
  )
}
