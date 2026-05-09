import { useMemo, useState } from 'react'
import { Plus, CheckCheck, Clock } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { STATUS_LABEL, STATUS_PILL, type QueueStatus } from '../_commex-mock'
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
  const retryStore = useCommexStore((s) => s.retryQueue)
  const [filter, setFilter] = useState<'all' | QueueStatus>('all')
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const navigate = useNavigate()

  const counts = useMemo(() => {
    const c: Record<string, number> = { all: items.length }
    for (const it of items) c[it.status] = (c[it.status] || 0) + 1
    return c
  }, [items])

  const rows = useMemo(
    () => (filter === 'all' ? items : items.filter((q) => q.status === filter)),
    [items, filter]
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
              <button className='cx-btn-soft'>
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
        </div>
      </Main>
    </>
  )
}

export default QueueCommex
