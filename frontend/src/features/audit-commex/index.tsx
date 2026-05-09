import { useState } from 'react'
import { Search, Download } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { LOGS } from '../_commex-mock'

const eventColor = (event: string) => {
  if (event.includes('failed') || event.includes('error')) return 'cx-pill-failed'
  if (event.includes('completed') || event.includes('done')) return 'cx-pill-done'
  if (event.includes('created') || event.includes('imported')) return 'cx-pill-draft'
  if (event.includes('triggered') || event.includes('scheduled')) return 'cx-pill-scheduled'
  if (event.includes('published') || event.includes('preset')) return 'cx-pill-pending'
  return 'cx-pill-draft'
}

export function AuditCommex() {
  const [q, setQ] = useState('')
  const filtered = LOGS.filter(
    (l) =>
      !q ||
      l.event.toLowerCase().includes(q.toLowerCase()) ||
      l.meta.some((m) => m.toLowerCase().includes(q.toLowerCase()))
  )

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
              <h1 className='cx-page-h'>로그</h1>
              <p className='cx-page-sub'>
                작업 로그 · 워커 로그 · 감사 로그를 조회합니다.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  padding: '0 14px',
                  height: 46,
                  borderRadius: 14,
                  border: '1px solid var(--cx-line)',
                  background: '#fff',
                  boxShadow: 'var(--cx-shadow-soft)',
                }}
              >
                <Search className='h-4 w-4' style={{ color: 'var(--cx-sub)' }} />
                <input
                  placeholder='이벤트·메타 검색'
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  style={{
                    border: 'none',
                    outline: 'none',
                    width: 220,
                    fontSize: 13,
                    background: 'transparent',
                  }}
                />
              </div>
              <button className='cx-btn-soft' onClick={() => toast.info('CSV 다운로드 (예정)')}>
                <Download className='inline h-4 w-4 mr-1.5' />다운로드
              </button>
            </div>
          </div>

          <div className='cx-card cx-card-pad'>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
              {filtered.map((l, i) => (
                <div
                  key={i}
                  style={{
                    display: 'grid',
                    gridTemplateColumns: '180px 200px 1fr',
                    gap: 14,
                    padding: '12px 14px',
                    borderRadius: 12,
                    background: i % 2 === 0 ? '#fbfcff' : '#fff',
                    border: '1px solid var(--cx-line-2)',
                    alignItems: 'center',
                  }}
                >
                  <span
                    style={{
                      fontSize: 12,
                      fontFamily: 'monospace',
                      color: 'var(--cx-sub)',
                    }}
                  >
                    {l.time}
                  </span>
                  <span className={`cx-pill ${eventColor(l.event)}`} style={{ fontFamily: 'monospace', fontSize: 11 }}>
                    {l.event}
                  </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {l.meta.map((m, j) => (
                      <span
                        key={j}
                        style={{
                          padding: '3px 8px',
                          borderRadius: 6,
                          background: '#f6f8fd',
                          fontSize: 11,
                          color: '#5f6983',
                          fontWeight: 600,
                        }}
                      >
                        {m}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
              {filtered.length === 0 && (
                <div
                  style={{
                    padding: 40,
                    textAlign: 'center',
                    color: 'var(--cx-sub)',
                  }}
                >
                  검색 결과가 없습니다.
                </div>
              )}
            </div>
          </div>
        </div>
      </Main>
    </>
  )
}

export default AuditCommex
