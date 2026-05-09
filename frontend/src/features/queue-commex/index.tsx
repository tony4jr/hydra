import { useEffect, useMemo, useState } from 'react'
import { Plus, CheckCheck, Clock } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { BRANDS, STATUS_LABEL, STATUS_PILL, type QueueStatus } from '../_commex-mock'
import { useCommexStore } from '../_commex-store'

const FILTERS: { key: 'all' | QueueStatus; label: string }[] = [
  { key: 'all', label: '전체' },
  { key: 'draft', label: '초안' },
  { key: 'pending', label: '승인 대기' },
  { key: 'scheduled', label: '예약' },
  { key: 'running', label: '실행 중' },
  { key: 'done', label: '완료' },
  { key: 'failed', label: '실패' },
]

export function QueueCommex() {
  const items = useCommexStore((s) => s.queue)
  const approveOneStore = useCommexStore((s) => s.approveQueue)
  const approveManyStore = useCommexStore((s) => s.approveMany)
  const scheduleManyStore = useCommexStore((s) => s.scheduleMany)
  const retryStore = useCommexStore((s) => s.retryQueue)
  const [filter, setFilter] = useState<'all' | QueueStatus>('all')
  const [brandFilter, setBrandFilter] = useState<string>('전체')
  const [nicheFilter, setNicheFilter] = useState<string>('전체')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [scheduleOpen, setScheduleOpen] = useState(false)
  const [schedule, setSchedule] = useState('오늘 18:00')
  const navigate = useNavigate()
  const nicheContext = useCommexStore((s) => s.nicheContext)
  const clearCtx = useCommexStore((s) => s.clearNicheContext)
  useEffect(() => {
    if (!nicheContext) return
    setBrandFilter(nicheContext.brandName)
    setNicheFilter(nicheContext.nicheName)
    setFilter('pending')
    clearCtx()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: items.length }
    for (const it of items) c[it.status] = (c[it.status] || 0) + 1
    return c
  }, [items])

  const rows = useMemo(
    () =>
      items.filter(
        (q) =>
          (filter === 'all' || q.status === filter) &&
          (brandFilter === '전체' || q.brand === brandFilter) &&
          (nicheFilter === '전체' || q.niche === nicheFilter)
      ),
    [items, filter, brandFilter, nicheFilter]
  )

  const toggleSel = (id: string) => {
    const next = new Set(selected)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    setSelected(next)
  }
  const toggleAll = () => {
    if (selected.size === rows.length) setSelected(new Set())
    else setSelected(new Set(rows.map((r) => r.id)))
  }
  const bulkApprove = () => {
    const n = approveManyStore(Array.from(selected))
    setSelected(new Set())
    if (n) toast.success(`${n}건을 예약 상태로 변경했습니다`)
    else toast.warning('승인 대기 상태인 작업을 선택하세요')
  }
  const approveOne = (id: string) => {
    approveOneStore(id)
    toast.success('승인 완료')
  }
  const retry = (id: string) => {
    retryStore(id)
    toast.info('승인 대기로 되돌렸습니다')
  }
  const changeSchedule = () => {
    const ids = Array.from(selected)
    if (!ids.length) {
      toast.warning('예약을 변경할 작업을 선택하세요')
      return
    }
    const n = scheduleManyStore(ids, schedule.trim() || '오늘 18:00')
    setSelected(new Set())
    setScheduleOpen(false)
    if (n) toast.success(`${n}건의 예약을 변경했습니다`)
    else toast.warning('초안/승인 대기/예약 상태만 변경할 수 있습니다')
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
              <h1 className='cx-page-h'>작업 큐</h1>
              <p className='cx-page-sub'>
                초안 → 승인 대기 → 예약 → 실행 중 → 완료/실패 흐름을 한 곳에서 관리합니다.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className='cx-btn-soft' onClick={bulkApprove}>
                <CheckCheck className='inline h-4 w-4 mr-1.5' />선택 승인
              </button>
              <button
                className='cx-btn-soft'
                onClick={() => {
                  if (!selected.size) {
                    toast.warning('예약을 변경할 작업을 선택하세요')
                    return
                  }
                  setScheduleOpen(true)
                }}
              >
                <Clock className='inline h-4 w-4 mr-1.5' />예약 변경
              </button>
              <button className='cx-btn-primary' onClick={() => navigate({ to: '/quick' })}>
                <Plus className='inline h-4 w-4 mr-1' />새 초안 생성
              </button>
            </div>
          </div>

          {/* Filter tabs */}
          <div className='cx-tabs'>
            {FILTERS.map((f) => (
              <button
                key={f.key}
                className={`cx-tab ${filter === f.key ? 'active' : ''}`}
                onClick={() => setFilter(f.key)}
              >
                {f.label} {counts[f.key] ?? 0}
              </button>
            ))}
          </div>

          {/* Brand/Niche filter */}
          <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
            <span style={{ fontSize: 12, fontWeight: 800, color: 'var(--cx-sub)' }}>
              브랜드
            </span>
            <select
              className='cx-input'
              style={{ width: 160, height: 36, padding: '6px 30px 6px 12px', fontSize: 13 }}
              value={brandFilter}
              onChange={(e) => {
                setBrandFilter(e.target.value)
                setNicheFilter('전체')
              }}
            >
              <option value='전체'>전체</option>
              {BRANDS.map((b) => (
                <option key={b.id} value={b.name}>
                  {b.name}
                </option>
              ))}
            </select>
            <span style={{ fontSize: 12, fontWeight: 800, color: 'var(--cx-sub)' }}>
              니치
            </span>
            <select
              className='cx-input'
              style={{ width: 180, height: 36, padding: '6px 30px 6px 12px', fontSize: 13 }}
              value={nicheFilter}
              onChange={(e) => setNicheFilter(e.target.value)}
              disabled={brandFilter === '전체'}
            >
              <option value='전체'>전체</option>
              {(BRANDS.find((b) => b.name === brandFilter)?.niches ?? []).map((n) => (
                <option key={n.id} value={n.name}>
                  {n.name}
                </option>
              ))}
            </select>
            {(brandFilter !== '전체' || nicheFilter !== '전체') && (
              <button
                className='cx-btn-mini'
                onClick={() => {
                  setBrandFilter('전체')
                  setNicheFilter('전체')
                }}
              >
                필터 해제
              </button>
            )}
          </div>

          {/* Table */}
          <div className='cx-card' style={{ overflow: 'hidden' }}>
            <table className='cx-table'>
              <thead>
                <tr>
                  <th style={{ width: 36, paddingLeft: 18 }}>
                    <input
                      type='checkbox'
                      checked={selected.size === rows.length && rows.length > 0}
                      onChange={toggleAll}
                    />
                  </th>
                  <th>작업</th>
                  <th>브랜드</th>
                  <th>니치</th>
                  <th>생성</th>
                  <th>상태</th>
                  <th>워커</th>
                  <th style={{ paddingRight: 18 }}></th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td style={{ paddingLeft: 18 }}>
                      <input
                        type='checkbox'
                        checked={selected.has(r.id)}
                        onChange={() => toggleSel(r.id)}
                      />
                    </td>
                    <td style={{ fontWeight: 700 }}>▶ {r.title}</td>
                    <td>{r.brand}</td>
                    <td>{r.niche}</td>
                    <td style={{ color: 'var(--cx-sub)' }}>{r.createdAt}</td>
                    <td>
                      <span className={`cx-pill ${STATUS_PILL[r.status]}`}>
                        {STATUS_LABEL[r.status]}
                      </span>
                    </td>
                    <td style={{ color: 'var(--cx-sub)' }}>{r.worker}</td>
                    <td style={{ paddingRight: 18, textAlign: 'right' }}>
                      {r.status === 'pending' && (
                        <button
                          className='cx-btn-mini'
                          onClick={() => approveOne(r.id)}
                        >
                          승인
                        </button>
                      )}
                      {r.status === 'failed' && (
                        <button className='cx-btn-mini' onClick={() => retry(r.id)}>
                          재시도
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={8} style={{ padding: 40, textAlign: 'center', color: 'var(--cx-sub)' }}>
                      해당 상태의 작업이 없습니다.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {scheduleOpen && (
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
              onClick={() => setScheduleOpen(false)}
            >
              <div
                className='cx-card cx-card-pad'
                style={{ width: 'min(460px, 100%)', display: 'flex', flexDirection: 'column', gap: 14 }}
                onClick={(e) => e.stopPropagation()}
              >
                <div className='cx-section-head'>
                  <div className='cx-section-title'>예약 변경</div>
                  <span style={{ fontSize: 12, color: 'var(--cx-sub)', fontWeight: 800 }}>
                    선택 {selected.size}건
                  </span>
                </div>
                <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <span style={{ fontSize: 12, color: 'var(--cx-sub)', fontWeight: 800 }}>
                    예약 시간
                  </span>
                  <input
                    className='cx-input'
                    value={schedule}
                    onChange={(e) => setSchedule(e.target.value)}
                    autoFocus
                    placeholder='예: 오늘 18:00'
                  />
                </label>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button className='cx-btn-soft' onClick={() => setScheduleOpen(false)}>
                    취소
                  </button>
                  <button className='cx-btn-primary' onClick={changeSchedule}>
                    변경
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

export default QueueCommex
