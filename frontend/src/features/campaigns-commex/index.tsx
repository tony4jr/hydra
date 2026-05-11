import { useEffect, useMemo, useState } from 'react'
import { Plus, Edit3, Copy } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { useCommexStore } from '../_commex-store'
import type { AutoJob } from '../_commex-mock'

type JobForm = {
  id?: string
  brand: string
  niche: string
  active: boolean
  keywords: string
  // 객관식 필드 — 저장 시 문자열 직렬화
  limit_per_day: number
  schedule_days: '매일' | '평일' | '주말'
  schedule_start: number // 0~23
  schedule_end: number   // 0~23 (exclusive)
}

export function CampaignsCommex() {
  const jobs = useCommexStore((s) => s.autoJobs)
  const queue = useCommexStore((s) => s.queue)
  const videos = useCommexStore((s) => s.videos)
  const brands = useCommexStore((s) => s.brands)
  const toggleStore = useCommexStore((s) => s.toggleAutoJob)
  const upsertAutoJob = useCommexStore((s) => s.upsertAutoJob)
  const duplicateAutoJob = useCommexStore((s) => s.duplicateAutoJob)
  const deleteAutoJobStore = useCommexStore((s) => s.deleteAutoJob)
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState<JobForm>(() => emptyForm())
  const newAutoJobIntent = useCommexStore((s) => s.newAutoJobIntent)
  const setNewAutoJobIntent = useCommexStore((s) => s.setNewAutoJobIntent)

  // 브랜드/니치 페이지에서 '+ 자동 작업 만들기' 진입 시 폼 자동 오픈 + 미리 입력
  useEffect(() => {
    if (!newAutoJobIntent) return
    setForm(emptyForm(newAutoJobIntent.brandName, newAutoJobIntent.nicheName))
    setFormOpen(true)
    setNewAutoJobIntent(null)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const active = jobs.filter((j) => j.active).length
  const todayDrafts = queue.filter((q) => q.status === 'draft').length
  const todayCollected = videos.length
  const selectedBrand = brands.find((b) => b.name === form.brand) ?? brands[0]
  const niches = selectedBrand?.niches ?? []
  const nextRun = useMemo(
    () =>
      jobs
        .filter((j) => j.active)
        .map((j) => j.nextRun)
        .sort()[0] ?? '—',
    [jobs]
  )

  const toggle = (id: string) => {
    toggleStore(id)
  }
  const openNew = () => {
    const firstBrand = brands[0]
    const firstNiche = firstBrand?.niches[0]
    setForm(emptyForm(firstBrand?.name, firstNiche?.name))
    setFormOpen(true)
  }
  const openEdit = (job: AutoJob) => {
    setForm({
      id: job.id,
      brand: job.brand,
      niche: job.niche,
      active: job.active,
      keywords: job.keywords.join(', '),
      ...parseJobToForm(job),
    })
    setFormOpen(true)
  }
  const submitJob = () => {
    if (!form.brand || !form.niche) {
      toast.warning('브랜드와 니치를 선택하세요')
      return
    }
    if (form.schedule_end <= form.schedule_start) {
      toast.warning('종료 시각이 시작 시각보다 늦어야 합니다')
      return
    }
    if (form.limit_per_day < 1 || form.limit_per_day > 50) {
      toast.warning('하루 한도는 1~50 사이여야 합니다')
      return
    }
    upsertAutoJob({
      id: form.id,
      brand: form.brand,
      niche: form.niche,
      active: form.active,
      keywords: form.keywords
        .split(',')
        .map((k) => k.trim())
        .filter(Boolean),
      limit: formatLimit(form.limit_per_day),
      time: formatTime(form.schedule_days, form.schedule_start, form.schedule_end),
      // nextRun 은 사용자가 직접 입력 X — scheduler 가 자동 계산. mock 에서는 시작 시각으로
      nextRun: `오늘 ${hh(form.schedule_start)}`,
    })
    setFormOpen(false)
    toast.success(form.id ? '자동 작업을 수정했습니다' : '자동 작업을 만들었습니다')
  }
  const cloneTemplate = () => {
    const target = jobs[0]
    if (!target) {
      toast.warning('복제할 자동 작업이 없습니다')
      return
    }
    duplicateAutoJob(target.id)
    toast.success(`${target.brand} · ${target.niche} 템플릿을 복제했습니다`)
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
              <button className='cx-btn-soft' onClick={cloneTemplate}>
                <Copy className='inline h-4 w-4 mr-1.5' />
                템플릿 복제
              </button>
              <button className='cx-btn-primary' onClick={openNew}>
                <Plus className='inline h-4 w-4 mr-1' />새 자동 작업
              </button>
            </div>
          </div>

          {/* Stats */}
          <div className='cx-kpi-strip four'>
            <MiniStat label='활성 자동 작업' value={active} />
            <MiniStat label='오늘 수집 영상' value={todayCollected} />
            <MiniStat label='오늘 생성 초안' value={todayDrafts} />
            <MiniStat label='다음 예약 실행' value={nextRun} />
          </div>

          {/* Workload distribution dashboard */}
          <WorkloadDashboard jobs={jobs} />

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
                  <button
                    className='cx-btn-soft'
                    style={{ height: 38 }}
                    onClick={() => openEdit(j)}
                  >
                    <Edit3 className='inline h-4 w-4 mr-1.5' />
                    편집
                  </button>
                </div>
              </div>
            ))}
          </div>
          {formOpen && (
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
              onClick={() => setFormOpen(false)}
            >
              <div
                className='cx-card cx-card-pad'
                style={{ width: 'min(560px, 100%)', display: 'flex', flexDirection: 'column', gap: 14 }}
                onClick={(e) => e.stopPropagation()}
              >
                <div className='cx-section-head'>
                  <div className='cx-section-title'>
                    {form.id ? '자동 작업 편집' : '새 자동 작업'}
                  </div>
                  <button className='cx-btn-mini' onClick={() => setFormOpen(false)}>
                    닫기
                  </button>
                </div>
                <Field label='브랜드'>
                  <select
                    className='cx-input'
                    value={form.brand}
                    onChange={(e) => {
                      const nextBrand = brands.find((b) => b.name === e.target.value)
                      setForm((f) => ({
                        ...f,
                        brand: e.target.value,
                        niche: nextBrand?.niches[0]?.name ?? '',
                      }))
                    }}
                  >
                    {brands.map((b) => (
                      <option key={b.id} value={b.name}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label='니치'>
                  <select
                    className='cx-input'
                    value={form.niche}
                    onChange={(e) => setForm((f) => ({ ...f, niche: e.target.value }))}
                  >
                    {niches.map((n) => (
                      <option key={n.id} value={n.name}>
                        {n.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label='키워드'>
                  <input
                    className='cx-input'
                    value={form.keywords}
                    onChange={(e) => setForm((f) => ({ ...f, keywords: e.target.value }))}
                    placeholder='쉼표로 구분'
                  />
                </Field>
                <Field label={`하루 한도 — ${form.limit_per_day}건`}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <input
                      type='range'
                      min={1}
                      max={50}
                      step={1}
                      value={form.limit_per_day}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, limit_per_day: Number(e.target.value) }))
                      }
                      style={{ flex: 1, accentColor: 'var(--cx-primary)' }}
                    />
                    <input
                      type='number'
                      className='cx-input'
                      min={1}
                      max={50}
                      style={{ width: 80, height: 36, textAlign: 'center', fontSize: 13 }}
                      value={form.limit_per_day}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          limit_per_day: Math.max(1, Math.min(50, Number(e.target.value) || 0)),
                        }))
                      }
                    />
                  </div>
                </Field>
                <Field label='실행 시간대'>
                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '110px 1fr 14px 1fr',
                      gap: 8,
                      alignItems: 'center',
                    }}
                  >
                    <select
                      className='cx-input'
                      style={{ height: 36, fontSize: 13 }}
                      value={form.schedule_days}
                      onChange={(e) =>
                        setForm((f) => ({
                          ...f,
                          schedule_days: e.target.value as JobForm['schedule_days'],
                        }))
                      }
                    >
                      <option value='매일'>매일</option>
                      <option value='평일'>평일 (월~금)</option>
                      <option value='주말'>주말 (토~일)</option>
                    </select>
                    <select
                      className='cx-input'
                      style={{ height: 36, fontSize: 13 }}
                      value={form.schedule_start}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, schedule_start: Number(e.target.value) }))
                      }
                    >
                      {Array.from({ length: 24 }, (_, h) => (
                        <option key={h} value={h}>
                          {hh(h)}
                        </option>
                      ))}
                    </select>
                    <span
                      style={{
                        textAlign: 'center',
                        color: 'var(--cx-sub)',
                        fontWeight: 800,
                      }}
                    >
                      ~
                    </span>
                    <select
                      className='cx-input'
                      style={{ height: 36, fontSize: 13 }}
                      value={form.schedule_end}
                      onChange={(e) =>
                        setForm((f) => ({ ...f, schedule_end: Number(e.target.value) }))
                      }
                    >
                      {Array.from({ length: 24 }, (_, h) => (
                        <option key={h} value={h}>
                          {hh(h)}
                        </option>
                      ))}
                    </select>
                  </div>
                </Field>

                {/* 분산 미리보기 */}
                <div
                  style={{
                    padding: 10,
                    borderRadius: 12,
                    background: '#f6f8ff',
                    border: '1px solid #d9dffd',
                    fontSize: 12,
                    color: 'var(--cx-primary)',
                    lineHeight: 1.55,
                  }}
                >
                  📊 <b>예상 분산:</b> {form.schedule_days} {hh(form.schedule_start)}~
                  {hh(form.schedule_end)} (
                  {Math.max(0, form.schedule_end - form.schedule_start)}시간) 안에 {form.limit_per_day}
                  건 발행 → 약 {form.schedule_end > form.schedule_start && form.limit_per_day > 0
                    ? Math.round(
                        ((form.schedule_end - form.schedule_start) * 60) / form.limit_per_day
                      )
                    : 0}{' '}
                  분마다 1건
                  <br />
                  <span style={{ color: 'var(--cx-sub)', fontSize: 11 }}>
                    💡 다음 실행 시각은 backend scheduler 가 자동 계산합니다 (사용자 지정 X)
                  </span>
                </div>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 800 }}>
                  <input
                    type='checkbox'
                    checked={form.active}
                    onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
                  />
                  생성 후 활성화
                </label>
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  {/* 편집 모드일 때만 좌측에 삭제 버튼 */}
                  {form.id ? (
                    <button
                      className='cx-btn-soft'
                      style={{
                        color: '#d2554c',
                        borderColor: '#f4cccb',
                        background: '#fff',
                      }}
                      onClick={() => {
                        if (
                          !confirm(
                            `${form.brand} · ${form.niche} 자동 작업을 삭제할까요?\n\n되돌릴 수 없습니다.`
                          )
                        )
                          return
                        deleteAutoJobStore(form.id!)
                        toast.success('자동 작업 삭제됨', {
                          description: `${form.brand} · ${form.niche}`,
                        })
                        setFormOpen(false)
                      }}
                    >
                      삭제
                    </button>
                  ) : (
                    <span />
                  )}
                  <div style={{ display: 'flex', gap: 8 }}>
                    <button className='cx-btn-soft' onClick={() => setFormOpen(false)}>
                      취소
                    </button>
                    <button className='cx-btn-primary' onClick={submitJob}>
                      저장
                    </button>
                  </div>
                </div>
              </div>
            </div>
          )}
        </div>
      </Main>
    </>
  )
}

function emptyForm(brand = '', niche = ''): JobForm {
  return {
    brand,
    niche,
    active: true,
    keywords: '',
    limit_per_day: 6,
    schedule_days: '평일',
    schedule_start: 10,
    schedule_end: 18,
  }
}

const hh = (h: number) => `${String(h).padStart(2, '0')}:00`
const formatLimit = (n: number) => `하루 ${n}건`
const formatTime = (days: JobForm['schedule_days'], s: number, e: number) =>
  `${days} ${hh(s)} ~ ${hh(e)}`

// AutoJob 의 문자열 한도/시간을 폼 필드로 파싱
function parseJobToForm(job: AutoJob): Omit<JobForm, 'id' | 'brand' | 'niche' | 'active' | 'keywords'> {
  const limitMatch = job.limit.match(/(\d+)/)
  const limit_per_day = limitMatch ? Number(limitMatch[1]) : 6
  let schedule_days: JobForm['schedule_days'] = '평일'
  if (job.time.includes('매일')) schedule_days = '매일'
  else if (job.time.includes('주말')) schedule_days = '주말'
  else if (job.time.includes('주중')) schedule_days = '평일'
  const range = job.time.match(/(\d{1,2}):\d{2}\s*~\s*(\d{1,2}):\d{2}/)
  const schedule_start = range ? Number(range[1]) : 10
  const schedule_end = range ? Number(range[2]) : 18
  return { limit_per_day, schedule_days, schedule_start, schedule_end }
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 12, color: 'var(--cx-sub)', fontWeight: 800 }}>
        {label}
      </span>
      {children}
    </label>
  )
}

// =================================================================
// 통합 작업량 대시보드 — 시간대별 task 발행 분포 + 브랜드별 + 워커
// =================================================================

function WorkloadDashboard({ jobs }: { jobs: AutoJob[] }) {
  // 시간대 문자열에서 시작·끝 시간 파싱 (예: "평일 10:00 ~ 18:00" → [10, 18])
  const parseRange = (s: string): [number, number] | null => {
    const m = s.match(/(\d{1,2}):\d{2}\s*~\s*(\d{1,2}):\d{2}/)
    if (!m) return null
    return [Number(m[1]), Number(m[2])]
  }
  // 하루 한도에서 숫자만
  const parseLimit = (s: string): number => {
    const m = s.match(/(\d+)/)
    return m ? Number(m[1]) : 0
  }
  // 0~23 시간대별 발행 예정 task 누적
  const hourly = Array(24).fill(0)
  let todayTotalPredicted = 0
  const brandTotals: Record<string, number> = {}
  for (const j of jobs) {
    if (!j.active) continue
    const lim = parseLimit(j.limit)
    todayTotalPredicted += lim
    brandTotals[j.brand] = (brandTotals[j.brand] ?? 0) + lim
    const range = parseRange(j.time)
    if (!range) continue
    const [start, end] = range
    const hours = Math.max(1, end - start)
    const perHour = lim / hours
    for (let h = start; h < end; h++) hourly[h] += perHour
  }
  const maxHour = Math.max(...hourly, 1)
  const workersOnline = 6 // mock — 실제론 store.workers

  return (
    <div className='cx-card cx-card-pad' style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: 12,
        }}
      >
        <div>
          <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--cx-text)' }}>
            오늘 발행 예정 작업량
          </div>
          <div style={{ fontSize: 12, color: 'var(--cx-sub)', marginTop: 2 }}>
            활성 자동 작업의 시간대·한도 기준 예측 분포. 워커가 시간대 안에서 분산 처리.
          </div>
        </div>
        <div style={{ display: 'flex', gap: 14, alignItems: 'center' }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 11, color: 'var(--cx-sub)', fontWeight: 700 }}>
              오늘 총
            </div>
            <div
              style={{
                fontSize: 22,
                fontWeight: 900,
                color: 'var(--cx-primary)',
                letterSpacing: '-0.02em',
              }}
            >
              {todayTotalPredicted}
              <span style={{ fontSize: 12, color: 'var(--cx-sub)', fontWeight: 700, marginLeft: 4 }}>
                건
              </span>
            </div>
          </div>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 11, color: 'var(--cx-sub)', fontWeight: 700 }}>
              워커 온라인
            </div>
            <div
              style={{
                fontSize: 22,
                fontWeight: 900,
                color: 'var(--cx-green)',
                letterSpacing: '-0.02em',
              }}
            >
              {workersOnline}
            </div>
          </div>
        </div>
      </div>

      {/* 시간대 분포 막대 */}
      <div>
        <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--cx-sub)', marginBottom: 6 }}>
          시간대별 발행 예측 (0~24시)
        </div>
        <div
          style={{
            display: 'flex',
            alignItems: 'flex-end',
            gap: 2,
            height: 64,
            padding: 4,
            borderRadius: 10,
            background: '#fbfcff',
            border: '1px solid var(--cx-line-2)',
          }}
        >
          {hourly.map((v, h) => {
            const heightPct = (v / maxHour) * 100
            const business = h >= 9 && h <= 18
            return (
              <div
                key={h}
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  height: '100%',
                  justifyContent: 'flex-end',
                  gap: 2,
                }}
                title={`${h}:00 ~ ${h + 1}:00 · 예측 ${v.toFixed(1)}건`}
              >
                <div
                  style={{
                    width: '100%',
                    height: `${Math.max(2, heightPct)}%`,
                    background: business
                      ? 'linear-gradient(180deg,#7d8aff,#4b63ff)'
                      : 'linear-gradient(180deg,#d3dcfb,#a3b1ff)',
                    borderRadius: 2,
                    transition: 'height 0.3s ease',
                  }}
                />
                {h % 3 === 0 && (
                  <div style={{ fontSize: 9, color: 'var(--cx-sub)', fontWeight: 700 }}>
                    {h}
                  </div>
                )}
              </div>
            )
          })}
        </div>
      </div>

      {/* 브랜드별 분포 */}
      {Object.keys(brandTotals).length > 0 && (
        <div>
          <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--cx-sub)', marginBottom: 6 }}>
            브랜드별 분포
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
            {Object.entries(brandTotals)
              .sort(([, a], [, b]) => b - a)
              .map(([brand, count]) => (
                <span
                  key={brand}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 6,
                    padding: '6px 12px',
                    borderRadius: 999,
                    background: '#f6f8ff',
                    border: '1px solid #d9dffd',
                    fontSize: 12,
                    fontWeight: 800,
                    color: 'var(--cx-primary)',
                  }}
                >
                  {brand}
                  <span style={{ color: 'var(--cx-text)' }}>{count}건</span>
                </span>
              ))}
          </div>
        </div>
      )}
    </div>
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
