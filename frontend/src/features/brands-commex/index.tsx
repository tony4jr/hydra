import { useState } from 'react'
import { Plus, Edit3, Puzzle } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { BRANDS } from '../_commex-mock'

export function BrandsCommex() {
  const [selectedId, setSelectedId] = useState(BRANDS[0].id)
  const brand = BRANDS.find((b) => b.id === selectedId) ?? BRANDS[0]

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
              <h1 className='cx-page-h'>브랜드 / 니치</h1>
              <p className='cx-page-sub'>
                왼쪽에서 브랜드를 고르면 오른쪽에서 니치 구성과 포함된 프리셋을 확인할 수 있어요.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className='cx-btn-soft'>
                <Plus className='inline h-4 w-4 mr-1' />브랜드 추가
              </button>
              <button className='cx-btn-primary'>
                <Plus className='inline h-4 w-4 mr-1' />니치 추가
              </button>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '320px 1fr',
              gap: 18,
            }}
            className='cx-brand-grid'
          >
            {/* Left: brand list */}
            <div className='cx-card cx-card-pad'>
              <div className='cx-section-head'>
                <div className='cx-section-title'>브랜드</div>
              </div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                {BRANDS.map((b) => {
                  const totalVideos = b.niches.reduce((a, n) => a + n.videos, 0)
                  const isActive = b.id === selectedId
                  return (
                    <button
                      key={b.id}
                      onClick={() => setSelectedId(b.id)}
                      style={{
                        textAlign: 'left',
                        padding: 14,
                        borderRadius: 16,
                        border: `1px solid ${isActive ? '#ccd6ff' : 'var(--cx-line)'}`,
                        background: isActive ? '#f8faff' : '#fff',
                        boxShadow: isActive
                          ? '0 8px 18px rgba(76,99,255,0.08)'
                          : 'var(--cx-shadow-soft)',
                        cursor: 'pointer',
                        transition: 'all 0.16s ease',
                      }}
                    >
                      <h4
                        style={{
                          margin: '0 0 4px',
                          fontSize: 15,
                          fontWeight: 800,
                          color: 'var(--cx-text)',
                        }}
                      >
                        {b.name}
                      </h4>
                      <p
                        style={{
                          margin: '0 0 8px',
                          fontSize: 12,
                          color: 'var(--cx-sub)',
                          lineHeight: 1.4,
                        }}
                      >
                        {b.summary}
                      </p>
                      <div
                        style={{
                          display: 'flex',
                          gap: 10,
                          fontSize: 11,
                          color: 'var(--cx-sub)',
                          fontWeight: 700,
                        }}
                      >
                        <span>니치 {b.niches.length}개</span>
                        <span>· 영상 {totalVideos}개</span>
                      </div>
                    </button>
                  )
                })}
              </div>
            </div>

            {/* Right: niche cards */}
            <div className='cx-card cx-card-pad'>
              <div className='cx-section-head'>
                <div>
                  <div className='cx-section-title'>{brand.name} · 니치</div>
                  <div style={{ fontSize: 12, color: 'var(--cx-sub)', marginTop: 4 }}>
                    니치 카드의 <b>프리셋 수정</b> 으로 진입해 슬롯을 편집하세요.
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(2, 1fr)',
                  gap: 14,
                }}
                className='cx-niche-grid'
              >
                {brand.niches.map((n) => (
                  <div
                    key={n.id}
                    style={{
                      padding: 16,
                      border: '1px solid var(--cx-line)',
                      borderRadius: 18,
                      background: '#fff',
                      boxShadow: 'var(--cx-shadow-soft)',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 12,
                    }}
                  >
                    {/* Top */}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'flex-start',
                        gap: 10,
                      }}
                    >
                      <div style={{ minWidth: 0 }}>
                        <h4
                          style={{
                            margin: '0 0 4px',
                            fontSize: 16,
                            fontWeight: 800,
                            color: 'var(--cx-text)',
                          }}
                        >
                          {n.name}
                        </h4>
                        <p
                          style={{
                            margin: 0,
                            fontSize: 12,
                            color: 'var(--cx-sub)',
                            lineHeight: 1.4,
                          }}
                        >
                          {n.desc}
                        </p>
                      </div>
                      <span
                        style={{
                          padding: '4px 10px',
                          borderRadius: 999,
                          background: '#f6f8fd',
                          color: '#56607c',
                          fontSize: 11,
                          fontWeight: 800,
                          flexShrink: 0,
                        }}
                      >
                        영상 {n.videos}개
                      </span>
                    </div>

                    {/* Keywords */}
                    <div>
                      <div
                        style={{
                          fontSize: 11,
                          color: 'var(--cx-sub)',
                          fontWeight: 800,
                          marginBottom: 6,
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                        }}
                      >
                        키워드
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {n.keywords.map((k) => (
                          <span
                            key={k}
                            style={{
                              padding: '4px 10px',
                              borderRadius: 999,
                              background: '#f6f8fd',
                              border: '1px solid var(--cx-line-2)',
                              color: '#5f6983',
                              fontSize: 11,
                              fontWeight: 700,
                            }}
                          >
                            #{k}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Presets — name only, no weight */}
                    <div>
                      <div
                        style={{
                          fontSize: 11,
                          color: 'var(--cx-sub)',
                          fontWeight: 800,
                          marginBottom: 6,
                          textTransform: 'uppercase',
                          letterSpacing: '0.04em',
                        }}
                      >
                        포함 프리셋
                      </div>
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                        {n.presets.map((p) => (
                          <span
                            key={p}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: 4,
                              padding: '4px 10px',
                              borderRadius: 999,
                              background: '#f3efff',
                              color: '#6758ff',
                              fontSize: 11,
                              fontWeight: 700,
                            }}
                          >
                            <Puzzle className='h-3 w-3' />
                            {p}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* Footer */}
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginTop: 4,
                        paddingTop: 10,
                        borderTop: '1px solid var(--cx-line-2)',
                      }}
                    >
                      <span style={{ fontSize: 12, color: 'var(--cx-sub)', fontWeight: 700 }}>
                        프리셋 {n.presets.length}개
                      </span>
                      <button
                        className='cx-btn-primary'
                        style={{ height: 36, padding: '0 14px', fontSize: 13 }}
                        onClick={() =>
                          toast.success(
                            `${n.name} 프리셋 수정 페이지로 이동 (다음 단계에 연결)`
                          )
                        }
                      >
                        <Edit3 className='inline h-3.5 w-3.5 mr-1' />
                        프리셋 수정
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </Main>
    </>
  )
}

export default BrandsCommex
