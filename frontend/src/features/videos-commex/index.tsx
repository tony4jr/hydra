import { useMemo, useState } from 'react'
import { Plus, Play, X } from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { BRANDS, type Video, type VideoStatus } from '../_commex-mock'
import { useCommexStore } from '../_commex-store'

const STATUS_LIST: VideoStatus[] = ['후보', '수집완료', '보류', '제외']

const statusClass = (s: VideoStatus) => {
  switch (s) {
    case '후보':
    case '수집완료':
      return { bg: '#f1eeff', color: '#6758ff', border: '#d9d1ff' }
    case '보류':
      return { bg: '#fff4df', color: '#ba8115', border: '#f0d18f' }
    case '제외':
      return { bg: '#fff1f0', color: '#d35c55', border: '#f2c4c1' }
  }
}

export function VideosCommex() {
  const videos = useCommexStore((s) => s.videos)
  const excludeStore = useCommexStore((s) => s.excludeVideo)
  const addManualStore = useCommexStore((s) => s.addManualVideos)
  const [brand, setBrand] = useState('전체')
  const [status, setStatus] = useState<'전체' | VideoStatus>('전체')
  const [modalOpen, setModalOpen] = useState(false)
  const [mBrand, setMBrand] = useState(BRANDS[0].name)
  const [mNiche, setMNiche] = useState(BRANDS[0].niches[0].name)
  const [mUrls, setMUrls] = useState('')
  const navigate = useNavigate()

  const rows = useMemo(
    () =>
      videos.filter(
        (v) =>
          (brand === '전체' || v.brand === brand) &&
          (status === '전체' || v.status === status)
      ),
    [videos, brand, status]
  )

  const exclude = (id: string) => {
    excludeStore(id)
    toast.info('영상이 제외 상태로 변경되었습니다')
  }

  const goQuick = (v: Video) => {
    toast.success(`${v.title} 컨텍스트로 빠른 작업 진입`)
    navigate({ to: '/quick' })
  }

  const niches = BRANDS.find((b) => b.name === mBrand)?.niches ?? []

  const submitManual = () => {
    const urls = mUrls
      .split('\n')
      .map((u) => u.trim())
      .filter(Boolean)
    if (!urls.length) {
      toast.warning('URL을 한 줄에 하나씩 입력하세요')
      return
    }
    const n = addManualStore({ brand: mBrand, niche: mNiche, urls })
    setModalOpen(false)
    setMUrls('')
    toast.success(`${n}개 영상이 추가됐습니다`)
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
              <h1 className='cx-page-h'>영상 풀</h1>
              <p className='cx-page-sub'>
                자동 수집 / 수동 추가된 영상을 브랜드와 상태 기준으로 관리합니다.
              </p>
            </div>
            <button className='cx-btn-primary' onClick={() => setModalOpen(true)}>
              <Plus className='inline h-4 w-4 mr-1' />수동 추가
            </button>
          </div>

          {/* Filters */}
          <div className='cx-card cx-card-pad'>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: 14,
              }}
            >
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 800, color: '#44506a' }}>
                  브랜드 필터
                </label>
                <select
                  className='cx-input'
                  value={brand}
                  onChange={(e) => setBrand(e.target.value)}
                >
                  <option value='전체'>전체</option>
                  {BRANDS.map((b) => (
                    <option key={b.id} value={b.name}>
                      {b.name}
                    </option>
                  ))}
                </select>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                <label style={{ fontSize: 13, fontWeight: 800, color: '#44506a' }}>
                  상태 필터
                </label>
                <select
                  className='cx-input'
                  value={status}
                  onChange={(e) => setStatus(e.target.value as VideoStatus | '전체')}
                >
                  <option value='전체'>전체</option>
                  {STATUS_LIST.map((s) => (
                    <option key={s}>{s}</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Table */}
            <div
              style={{
                marginTop: 14,
                border: '1px solid var(--cx-line-2)',
                borderRadius: 18,
                overflow: 'hidden',
                background: '#fff',
              }}
            >
              <table className='cx-table'>
                <thead>
                  <tr style={{ background: '#fafbff' }}>
                    <th style={{ paddingLeft: 18 }}>영상</th>
                    <th>브랜드 / 니치</th>
                    <th>지표</th>
                    <th>관련성</th>
                    <th>상태</th>
                    <th style={{ paddingRight: 18 }}>작업</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((v) => {
                    const sc = statusClass(v.status)
                    return (
                      <tr key={v.id}>
                        <td style={{ paddingLeft: 18, maxWidth: 320 }}>
                          <div
                            style={{
                              fontSize: 14,
                              fontWeight: 800,
                              color: 'var(--cx-text)',
                              lineHeight: 1.35,
                            }}
                          >
                            {v.title}
                          </div>
                          <div style={{ fontSize: 12, color: 'var(--cx-sub)', marginTop: 2 }}>
                            {v.source} · {v.date} · {v.lang}
                          </div>
                        </td>
                        <td>
                          <div style={{ fontSize: 13, fontWeight: 800 }}>{v.brand}</div>
                          <div style={{ fontSize: 12, color: 'var(--cx-sub)' }}>{v.niche}</div>
                        </td>
                        <td>
                          <div style={{ fontSize: 13, fontWeight: 800 }}>조회 {v.views}</div>
                          <div style={{ fontSize: 12, color: 'var(--cx-sub)' }}>댓글 {v.comments}</div>
                        </td>
                        <td>
                          <div
                            style={{
                              width: 80,
                              height: 8,
                              borderRadius: 999,
                              background: '#e7eaf7',
                              overflow: 'hidden',
                              marginBottom: 4,
                            }}
                          >
                            <div
                              style={{
                                height: '100%',
                                width: `${Math.max(15, Math.min(100, v.relevance))}%`,
                                background: 'linear-gradient(90deg,#7f7cff,#6f5dff)',
                              }}
                            />
                          </div>
                          <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--cx-sub)' }}>
                            {v.relevance}점
                          </div>
                        </td>
                        <td>
                          <span
                            style={{
                              display: 'inline-flex',
                              padding: '6px 12px',
                              borderRadius: 999,
                              fontSize: 12,
                              fontWeight: 800,
                              border: `1px solid ${sc.border}`,
                              background: sc.bg,
                              color: sc.color,
                            }}
                          >
                            {v.status}
                          </span>
                        </td>
                        <td style={{ paddingRight: 18, whiteSpace: 'nowrap' }}>
                          <button
                            className='cx-btn-mini'
                            style={{ marginRight: 6 }}
                            onClick={() => goQuick(v)}
                          >
                            <Play className='inline h-3 w-3 mr-1' />빠른 작업
                          </button>
                          <button
                            className='cx-btn-mini'
                            style={{ borderColor: '#f1c8c6', color: '#d2554c' }}
                            onClick={() => exclude(v.id)}
                          >
                            제외
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                  {rows.length === 0 && (
                    <tr>
                      <td colSpan={6} style={{ padding: 40, textAlign: 'center', color: 'var(--cx-sub)' }}>
                        조건에 맞는 영상이 없습니다.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Manual add modal */}
        {modalOpen && (
          <div
            onClick={() => setModalOpen(false)}
            style={{
              position: 'fixed',
              inset: 0,
              background: 'rgba(12,18,34,0.52)',
              backdropFilter: 'blur(5px)',
              zIndex: 60,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: 20,
            }}
          >
            <div
              onClick={(e) => e.stopPropagation()}
              style={{
                width: 'min(620px,100%)',
                background: '#fff',
                borderRadius: 22,
                overflow: 'hidden',
                boxShadow: '0 40px 90px rgba(12,18,34,0.28)',
              }}
            >
              <div
                style={{
                  padding: '20px 24px',
                  borderBottom: '1px solid var(--cx-line)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                }}
              >
                <div>
                  <div style={{ fontSize: 20, fontWeight: 900 }}>영상 수동 추가</div>
                  <div style={{ fontSize: 13, color: 'var(--cx-sub)', marginTop: 4 }}>
                    여러 URL을 한 줄에 하나씩 입력. 제목은 자동 추출됩니다.
                  </div>
                </div>
                <button className='cx-icon-btn' onClick={() => setModalOpen(false)}>
                  <X className='h-4 w-4' />
                </button>
              </div>
              <div style={{ padding: 24, display: 'flex', flexDirection: 'column', gap: 14 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <label style={{ fontSize: 13, fontWeight: 800, color: '#44506a' }}>브랜드</label>
                    <select
                      className='cx-input'
                      value={mBrand}
                      onChange={(e) => {
                        setMBrand(e.target.value)
                        const b = BRANDS.find((bb) => bb.name === e.target.value)
                        if (b) setMNiche(b.niches[0].name)
                      }}
                    >
                      {BRANDS.map((b) => (
                        <option key={b.id}>{b.name}</option>
                      ))}
                    </select>
                  </div>
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    <label style={{ fontSize: 13, fontWeight: 800, color: '#44506a' }}>니치</label>
                    <select
                      className='cx-input'
                      value={mNiche}
                      onChange={(e) => setMNiche(e.target.value)}
                    >
                      {niches.map((n) => (
                        <option key={n.id}>{n.name}</option>
                      ))}
                    </select>
                  </div>
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  <label style={{ fontSize: 13, fontWeight: 800, color: '#44506a' }}>영상 URL</label>
                  <textarea
                    className='cx-input'
                    style={{ minHeight: 130, resize: 'vertical', lineHeight: 1.55, fontFamily: 'monospace' }}
                    placeholder={`https://youtube.com/watch?v=abc123\nhttps://youtube.com/watch?v=def456`}
                    value={mUrls}
                    onChange={(e) => setMUrls(e.target.value)}
                  />
                  <div style={{ fontSize: 11, color: 'var(--cx-sub)' }}>
                    제목 입력 필드는 없습니다. 추가 후 자동 추출되어 표시됩니다.
                  </div>
                </div>
              </div>
              <div
                style={{
                  padding: '16px 24px',
                  borderTop: '1px solid var(--cx-line)',
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: 8,
                }}
              >
                <button className='cx-btn-soft' onClick={() => setModalOpen(false)}>
                  취소
                </button>
                <button className='cx-btn-primary' onClick={submitManual}>
                  추가하기
                </button>
              </div>
            </div>
          </div>
        )}
      </Main>
    </>
  )
}

export default VideosCommex
