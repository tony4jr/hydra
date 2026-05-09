import { useMemo, useState } from 'react'
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
  limit: string
  time: string
  nextRun: string
}

export function CampaignsCommex() {
  const jobs = useCommexStore((s) => s.autoJobs)
  const queue = useCommexStore((s) => s.queue)
  const videos = useCommexStore((s) => s.videos)
  const brands = useCommexStore((s) => s.brands)
  const toggleStore = useCommexStore((s) => s.toggleAutoJob)
  const upsertAutoJob = useCommexStore((s) => s.upsertAutoJob)
  const duplicateAutoJob = useCommexStore((s) => s.duplicateAutoJob)
  const [formOpen, setFormOpen] = useState(false)
  const [form, setForm] = useState<JobForm>(() => emptyForm())

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
      limit: job.limit,
      time: job.time,
      nextRun: job.nextRun,
    })
    setFormOpen(true)
  }
  const submitJob = () => {
    if (!form.brand || !form.niche) {
      toast.warning('브랜드와 니치를 선택하세요')
      return
    }
    upsertAutoJob({
      ...form,
      keywords: form.keywords
        .split(',')
        .map((k) => k.trim())
        .filter(Boolean),
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
                <Field label='한도'>
                  <input
                    className='cx-input'
                    value={form.limit}
                    onChange={(e) => setForm((f) => ({ ...f, limit: e.target.value }))}
                  />
                </Field>
                <Field label='실행 시간'>
                  <input
                    className='cx-input'
                    value={form.time}
                    onChange={(e) => setForm((f) => ({ ...f, time: e.target.value }))}
                  />
                </Field>
                <Field label='다음 실행'>
                  <input
                    className='cx-input'
                    value={form.nextRun}
                    onChange={(e) => setForm((f) => ({ ...f, nextRun: e.target.value }))}
                  />
                </Field>
                <label style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, fontWeight: 800 }}>
                  <input
                    type='checkbox'
                    checked={form.active}
                    onChange={(e) => setForm((f) => ({ ...f, active: e.target.checked }))}
                  />
                  생성 후 활성화
                </label>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button className='cx-btn-soft' onClick={() => setFormOpen(false)}>
                    취소
                  </button>
                  <button className='cx-btn-primary' onClick={submitJob}>
                    저장
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

function emptyForm(brand = '', niche = ''): JobForm {
  return {
    brand,
    niche,
    active: true,
    keywords: '',
    limit: '하루 6건',
    time: '평일 10:00 ~ 18:00',
    nextRun: '오늘 18:00',
  }
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
