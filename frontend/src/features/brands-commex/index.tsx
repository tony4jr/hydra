import { useState } from 'react'
import {
  Plus,
  Edit3,
  Puzzle,
  Video,
  Zap,
  RefreshCw,
  X,
  AlertCircle,
  Trash2,
} from 'lucide-react'
import { useNavigate } from '@tanstack/react-router'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { useCommexStore } from '../_commex-store'
import { GLOBAL_PRESETS, type Niche } from '../_commex-mock'

// 결정적 hash 로 키워드별 7일 영상 수 시뮬레이션
function keywordEffect(brand: string, keyword: string): number {
  const s = brand + keyword
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  return Math.abs(h) % 80
}

// 7일 sparkline 데이터 (수집·완료)
function nicheTrend(brand: string, nicheId: string): number[] {
  const s = brand + nicheId
  let h = 0
  for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) | 0
  const seed = Math.abs(h)
  return Array.from({ length: 7 }, (_, i) => {
    const v = ((seed * (i + 7)) % 50) + 10 + (i === 6 ? 8 : 0)
    return v
  })
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  const max = Math.max(...data, 1)
  const w = 110
  const h = 32
  const points = data
    .map((v, i) => {
      const x = (i / (data.length - 1)) * w
      const y = h - (v / max) * h
      return `${x.toFixed(1)},${y.toFixed(1)}`
    })
    .join(' ')
  return (
    <svg width={w} height={h} style={{ display: 'block' }}>
      <polyline
        fill='none'
        stroke={color}
        strokeWidth={2}
        strokeLinecap='round'
        strokeLinejoin='round'
        points={points}
      />
      <circle
        cx={w}
        cy={h - (data[data.length - 1] / max) * h}
        r={3}
        fill={color}
      />
    </svg>
  )
}

export function BrandsCommex() {
  const brands = useCommexStore((s) => s.brands)
  const queue = useCommexStore((s) => s.queue)
  const videos = useCommexStore((s) => s.videos)
  const autoJobs = useCommexStore((s) => s.autoJobs)
  const updateKeywords = useCommexStore((s) => s.updateNicheKeywords)
  const toggleAutoJob = useCommexStore((s) => s.toggleAutoJob)
  const setNicheContext = useCommexStore((s) => s.setNicheContext)
  const addBrand = useCommexStore((s) => s.addBrand)
  const addNiche = useCommexStore((s) => s.addNiche)
  const updateNichePresets = useCommexStore((s) => s.updateNichePresets)
  const deleteBrand = useCommexStore((s) => s.deleteBrand)
  const deleteNiche = useCommexStore((s) => s.deleteNiche)
  const navigate = useNavigate()

  const [selectedId, setSelectedId] = useState(brands[0]?.id ?? '')
  const [brandModal, setBrandModal] = useState(false)
  const [nicheModal, setNicheModal] = useState(false)
  const [presetEditing, setPresetEditing] = useState<{
    brandId: string
    nicheId: string
    nicheName: string
    presets: string[]
  } | null>(null)
  const [brandForm, setBrandForm] = useState({ name: '', summary: '' })
  const [nicheForm, setNicheForm] = useState({
    name: '',
    desc: '',
    keywords: '',
  })
  const brand = brands.find((b) => b.id === selectedId) ?? brands[0]

  const submitBrand = () => {
    const name = brandForm.name.trim()
    if (!name) {
      toast.warning('브랜드 이름을 입력하세요')
      return
    }
    if (brands.some((b) => b.name === name)) {
      toast.warning('이미 있는 브랜드입니다')
      return
    }
    const id = addBrand({
      name,
      summary: brandForm.summary.trim() || '새 운영 브랜드',
    })
    setSelectedId(id)
    setBrandForm({ name: '', summary: '' })
    setBrandModal(false)
    toast.success(`${name} 브랜드를 추가했습니다`)
  }

  const submitNiche = () => {
    if (!brand) return
    const name = nicheForm.name.trim()
    if (!name) {
      toast.warning('니치 이름을 입력하세요')
      return
    }
    if (brand.niches.some((n) => n.name === name)) {
      toast.warning('이미 있는 니치입니다')
      return
    }
    addNiche(brand.id, {
      name,
      desc: nicheForm.desc.trim() || '새 니치 운영 방향을 입력하세요.',
      keywords: nicheForm.keywords
        .split(',')
        .map((k) => k.trim())
        .filter(Boolean),
    })
    setNicheForm({ name: '', desc: '', keywords: '' })
    setNicheModal(false)
    toast.success(`${brand.name}에 ${name} 니치를 추가했습니다`)
  }

  if (!brand) {
    return null
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
              <h1 className='cx-page-h'>브랜드 / 니치</h1>
              <p className='cx-page-sub'>
                브랜드를 선택하고, 니치 카드에서 영상 수집·작업·프리셋·자동
                작업까지 한 곳에서 분기합니다.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button className='cx-btn-soft' onClick={() => setBrandModal(true)}>
                <Plus className='inline h-4 w-4 mr-1' />브랜드 추가
              </button>
              <button
                className='cx-btn-primary'
                onClick={() => setNicheModal(true)}
                disabled={!brand}
              >
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
                {brands.map((b) => {
                  const totalVideos = b.niches.reduce((a, n) => a + n.videos, 0)
                  const isActive = b.id === selectedId
                  const pendingCount = queue.filter(
                    (q) =>
                      q.brand === b.name &&
                      (q.status === 'pending' || q.status === 'failed')
                  ).length
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
                        position: 'relative',
                      }}
                    >
                      <div
                        style={{
                          position: 'absolute',
                          top: 8,
                          right: 8,
                          display: 'flex',
                          alignItems: 'center',
                          gap: 4,
                        }}
                      >
                        {pendingCount > 0 && (
                          <span
                            style={{
                              padding: '2px 8px',
                              borderRadius: 999,
                              background: '#fff0ef',
                              color: '#d2554c',
                              fontSize: 10,
                              fontWeight: 900,
                              border: '1px solid #f4cccb',
                            }}
                          >
                            ⚠ {pendingCount}
                          </span>
                        )}
                        <span
                          onClick={(e) => {
                            e.stopPropagation()
                            const totalVideos = b.niches.reduce(
                              (a, n) => a + n.videos,
                              0
                            )
                            if (
                              !confirm(
                                `${b.name} 브랜드를 삭제할까요?\n\n니치 ${b.niches.length}개, 누적 영상 ${totalVideos}개와 함께 제거됩니다. 되돌릴 수 없습니다.`
                              )
                            )
                              return
                            deleteBrand(b.id)
                            if (selectedId === b.id) {
                              const next = brands.find((x) => x.id !== b.id)
                              setSelectedId(next?.id ?? '')
                            }
                            toast.success(`${b.name} 삭제됨`)
                          }}
                          title='브랜드 삭제'
                          role='button'
                          style={{
                            width: 24,
                            height: 24,
                            borderRadius: 8,
                            display: 'grid',
                            placeItems: 'center',
                            color: '#d2554c',
                            cursor: 'pointer',
                            transition: 'background 0.14s ease',
                          }}
                          onMouseEnter={(e) => {
                            e.currentTarget.style.background = '#fff0ef'
                          }}
                          onMouseLeave={(e) => {
                            e.currentTarget.style.background = ''
                          }}
                        >
                          <Trash2 className='h-3.5 w-3.5' />
                        </span>
                      </div>
                      <h4
                        style={{
                          margin: '0 0 4px',
                          fontSize: 15,
                          fontWeight: 800,
                          color: 'var(--cx-text)',
                          paddingRight: 40,
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
                        <span>니치 {b.niches.length}</span>
                        <span>· 영상 {totalVideos}</span>
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
                  <div className='cx-section-title'>{brand?.name ?? '브랜드'} · 니치</div>
                  <div style={{ fontSize: 12, color: 'var(--cx-sub)', marginTop: 4 }}>
                    각 니치 카드는 영상 수집·작업·자동작업의 시작점입니다.
                  </div>
                </div>
              </div>

              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))',
                  gap: 14,
                }}
              >
                {(brand?.niches ?? []).map((n) => (
                  <NicheCard
                    key={n.id}
                    brandId={brand.id}
                    brandName={brand.name}
                    niche={n}
                    pending={
                      queue.filter(
                        (q) =>
                          q.brand === brand.name &&
                          q.niche === n.name &&
                          q.status === 'pending'
                      ).length
                    }
                    drafts={
                      queue.filter(
                        (q) =>
                          q.brand === brand.name &&
                          q.niche === n.name &&
                          q.status === 'draft'
                      ).length
                    }
                    todayCollected={
                      videos.filter(
                        (v) => v.brand === brand.name && v.niche === n.name
                      ).length
                    }
                    autoJob={autoJobs.find(
                      (j) => j.brand === brand.name && j.niche === n.name
                    )}
                    onUpdateKeywords={(keywords) =>
                      updateKeywords(brand.id, n.id, keywords)
                    }
                    onToggleAuto={(jobId) => toggleAutoJob(jobId)}
                    onDelete={() => {
                      deleteNiche(brand.id, n.id)
                      toast.success(`${n.name} 니치 삭제됨`)
                    }}
                    onAction={(action) => {
                      if (action === 'preset') {
                        // 니치 카드 안에서 모달로 프리셋 편집 (이 니치 전용 선택)
                        setPresetEditing({
                          brandId: brand.id,
                          nicheId: n.id,
                          nicheName: n.name,
                          presets: [...n.presets],
                        })
                        return
                      }
                      setNicheContext({
                        brandName: brand.name,
                        nicheName: n.name,
                      })
                      const dest = {
                        videos: '/videos' as const,
                        quick: '/quick' as const,
                        auto: '/campaigns' as const,
                      }[action]
                      navigate({ to: dest })
                      toast.success(`${n.name} 컨텍스트 적용`, {
                        description: `${brand.name} · ${n.name}`,
                      })
                    }}
                  />
                ))}
              </div>
            </div>
          </div>
          {brandModal && (
            <InlineModal
              title='브랜드 추가'
              onClose={() => setBrandModal(false)}
              onSubmit={submitBrand}
              submitLabel='추가'
            >
              <FormLine label='브랜드명'>
                <input
                  className='cx-input'
                  value={brandForm.name}
                  onChange={(e) =>
                    setBrandForm((f) => ({ ...f, name: e.target.value }))
                  }
                  autoFocus
                  placeholder='예: 새 브랜드'
                />
              </FormLine>
              <FormLine label='요약'>
                <input
                  className='cx-input'
                  value={brandForm.summary}
                  onChange={(e) =>
                    setBrandForm((f) => ({ ...f, summary: e.target.value }))
                  }
                  placeholder='운영 목적이나 제품군'
                />
              </FormLine>
            </InlineModal>
          )}
          {nicheModal && brand && (
            <InlineModal
              title={`${brand.name} 니치 추가`}
              onClose={() => setNicheModal(false)}
              onSubmit={submitNiche}
              submitLabel='추가'
            >
              <FormLine label='니치명'>
                <input
                  className='cx-input'
                  value={nicheForm.name}
                  onChange={(e) =>
                    setNicheForm((f) => ({ ...f, name: e.target.value }))
                  }
                  autoFocus
                  placeholder='예: 피부 진정 루틴'
                />
              </FormLine>
              <FormLine label='설명'>
                <input
                  className='cx-input'
                  value={nicheForm.desc}
                  onChange={(e) =>
                    setNicheForm((f) => ({ ...f, desc: e.target.value }))
                  }
                  placeholder='운영 방향'
                />
              </FormLine>
              <FormLine label='초기 키워드'>
                <input
                  className='cx-input'
                  value={nicheForm.keywords}
                  onChange={(e) =>
                    setNicheForm((f) => ({ ...f, keywords: e.target.value }))
                  }
                  placeholder='쉼표로 구분'
                />
              </FormLine>
            </InlineModal>
          )}

          {presetEditing && (
            <PresetEditorModal
              data={presetEditing}
              onClose={() => setPresetEditing(null)}
              onSave={(presets) => {
                updateNichePresets(
                  presetEditing.brandId,
                  presetEditing.nicheId,
                  presets
                )
                toast.success(
                  `${presetEditing.nicheName} 프리셋 ${presets.length}개 저장됨`
                )
                setPresetEditing(null)
              }}
            />
          )}
        </div>
      </Main>
    </>
  )
}

// =================================================================
// Preset Editor Modal — 니치에 포함할 글로벌 프리셋 선택
// =================================================================

function PresetEditorModal({
  data,
  onClose,
  onSave,
}: {
  data: { brandId: string; nicheId: string; nicheName: string; presets: string[] }
  onClose: () => void
  onSave: (presets: string[]) => void
}) {
  const [selected, setSelected] = useState<Set<string>>(new Set(data.presets))
  const toggle = (name: string) => {
    const next = new Set(selected)
    if (next.has(name)) next.delete(name); else next.add(name)
    setSelected(next)
  }
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed', inset: 0,
        background: 'rgba(12,18,34,0.52)',
        backdropFilter: 'blur(5px)',
        zIndex: 60,
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        padding: 20,
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(640px, 100%)',
          background: '#fff',
          borderRadius: 22,
          overflow: 'hidden',
          boxShadow: '0 40px 90px rgba(12,18,34,0.28)',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '85vh',
        }}
      >
        <div style={{ padding: '18px 22px', borderBottom: '1px solid var(--cx-line)' }}>
          <div style={{ fontSize: 18, fontWeight: 900 }}>
            {data.nicheName} — 프리셋 편집
          </div>
          <div style={{ fontSize: 12, color: 'var(--cx-sub)', marginTop: 4 }}>
            이 니치에 포함할 글로벌 프리셋을 선택하세요. 선택된 프리셋들 중에서
            슬롯 엔진이 가중치에 따라 하나를 골라 댓글을 생성합니다.
          </div>
        </div>

        <div style={{ padding: 18, overflow: 'auto', flex: 1 }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {GLOBAL_PRESETS.map((p) => {
              const isOn = selected.has(p.name)
              return (
                <label
                  key={p.id}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 12,
                    padding: 12,
                    borderRadius: 14,
                    border: `1px solid ${isOn ? '#c7d0ff' : 'var(--cx-line)'}`,
                    background: isOn ? '#f6f8ff' : '#fff',
                    cursor: 'pointer',
                    transition: 'all 0.14s ease',
                  }}
                >
                  <input
                    type='checkbox'
                    checked={isOn}
                    onChange={() => toggle(p.name)}
                    style={{
                      width: 16, height: 16,
                      accentColor: 'var(--cx-primary)',
                      flexShrink: 0,
                    }}
                  />
                  <Puzzle
                    className='h-4 w-4'
                    style={{ color: isOn ? 'var(--cx-primary)' : 'var(--cx-sub)', flexShrink: 0 }}
                  />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div style={{ fontSize: 14, fontWeight: 800, color: 'var(--cx-text)' }}>
                      {p.name}
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--cx-sub)', lineHeight: 1.4, marginTop: 2 }}>
                      {p.desc}
                    </div>
                  </div>
                  <span style={{ fontSize: 11, color: 'var(--cx-sub)', fontWeight: 700, flexShrink: 0 }}>
                    {p.version}
                  </span>
                </label>
              )
            })}
          </div>
        </div>

        <div
          style={{
            padding: '14px 22px',
            borderTop: '1px solid var(--cx-line)',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 8,
          }}
        >
          <span style={{ fontSize: 12, color: 'var(--cx-sub)' }}>
            {selected.size}개 선택됨 / 전체 {GLOBAL_PRESETS.length}개
          </span>
          <div style={{ display: 'flex', gap: 8 }}>
            <button className='cx-btn-soft' onClick={onClose}>취소</button>
            <button
              className='cx-btn-primary'
              onClick={() => onSave(Array.from(selected))}
            >
              저장
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}

// =================================================================
// Niche Card
// =================================================================

function NicheCard({
  brandId: _brandId,
  brandName,
  niche,
  pending,
  drafts,
  todayCollected,
  autoJob,
  onUpdateKeywords,
  onToggleAuto,
  onAction,
  onDelete,
}: {
  brandId: string
  brandName: string
  niche: Niche
  pending: number
  drafts: number
  todayCollected: number
  autoJob: { id: string; active: boolean; nextRun: string } | undefined
  onUpdateKeywords: (keywords: string[]) => void
  onToggleAuto: (jobId: string) => void
  onAction: (action: 'videos' | 'quick' | 'auto' | 'preset') => void
  onDelete: () => void
}) {
  const [adding, setAdding] = useState(false)
  const [newKw, setNewKw] = useState('')
  const trend = nicheTrend(brandName, niche.id)

  const removeKw = (kw: string) => {
    onUpdateKeywords(niche.keywords.filter((k) => k !== kw))
    toast.success(`#${kw} 제거됨`)
  }
  const addKw = () => {
    const t = newKw.trim()
    if (!t) return
    if (niche.keywords.includes(t)) {
      toast.warning('이미 있는 키워드')
      return
    }
    onUpdateKeywords([...niche.keywords, t])
    setNewKw('')
    setAdding(false)
    toast.success(`#${t} 추가됨`)
  }

  return (
    <div
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
      {/* Top: title + pending badge */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          gap: 10,
        }}
      >
        <div style={{ minWidth: 0, flex: 1 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 4 }}>
            <h4
              style={{
                margin: 0,
                fontSize: 16,
                fontWeight: 800,
                color: 'var(--cx-text)',
              }}
            >
              {niche.name}
            </h4>
            {pending > 0 && (
              <button
                onClick={() => onAction('quick')}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '3px 8px',
                  borderRadius: 999,
                  background: '#fff0ef',
                  color: '#d2554c',
                  border: '1px solid #f4cccb',
                  fontSize: 11,
                  fontWeight: 900,
                  cursor: 'pointer',
                }}
                title='큐로 이동'
              >
                <AlertCircle className='h-3 w-3' />
                승인 대기 {pending}
              </button>
            )}
            <button
              onClick={() => {
                if (
                  !confirm(
                    `${niche.name} 니치를 삭제할까요?\n\n포함된 프리셋 ${niche.presets.length}개, 키워드 ${niche.keywords.length}개와의 연결이 끊어지고 누적 영상 ${niche.videos}개의 니치 라벨이 사라집니다. 되돌릴 수 없습니다.`
                  )
                )
                  return
                onDelete()
              }}
              title='니치 삭제'
              style={{
                width: 24,
                height: 24,
                borderRadius: 8,
                border: 'none',
                background: 'transparent',
                color: '#d2554c',
                cursor: 'pointer',
                display: 'inline-grid',
                placeItems: 'center',
                marginLeft: 'auto',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#fff0ef'
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = 'transparent'
              }}
            >
              <Trash2 className='h-3.5 w-3.5' />
            </button>
          </div>
          <p
            style={{
              margin: 0,
              fontSize: 12,
              color: 'var(--cx-sub)',
              lineHeight: 1.4,
            }}
          >
            {niche.desc}
          </p>
        </div>
      </div>

      {/* Live status row */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: 10,
          padding: '10px 12px',
          borderRadius: 12,
          background: autoJob?.active ? '#f3fdf6' : '#fbfcff',
          border: `1px solid ${autoJob?.active ? '#bff0d3' : 'var(--cx-line-2)'}`,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, minWidth: 0 }}>
          {autoJob ? (
            <>
              <Toggle
                on={autoJob.active}
                onClick={() => onToggleAuto(autoJob.id)}
              />
              <div style={{ minWidth: 0 }}>
                <div
                  style={{
                    fontSize: 11,
                    fontWeight: 800,
                    color: autoJob.active ? '#16b364' : 'var(--cx-sub)',
                  }}
                >
                  자동 작업 {autoJob.active ? 'ON' : 'OFF'}
                </div>
                <div
                  style={{
                    fontSize: 11,
                    color: 'var(--cx-sub)',
                    marginTop: 1,
                  }}
                >
                  다음 실행 · {autoJob.nextRun}
                </div>
              </div>
            </>
          ) : (
            <span style={{ fontSize: 12, color: 'var(--cx-sub)' }}>
              자동 작업 미설정
            </span>
          )}
        </div>
        <div style={{ display: 'flex', gap: 12, fontSize: 11, fontWeight: 700 }}>
          <Mini label='수집' value={todayCollected} color='var(--cx-blue)' />
          <Mini label='초안' value={drafts} color='var(--cx-purple)' />
          <Mini label='영상' value={niche.videos} color='var(--cx-text)' />
        </div>
      </div>

      {/* Keywords with effect counts */}
      <div>
        <div
          style={{
            fontSize: 11,
            color: 'var(--cx-sub)',
            fontWeight: 800,
            marginBottom: 6,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            display: 'flex',
            justifyContent: 'space-between',
          }}
        >
          <span>키워드 · 7일 수집</span>
          {!adding && (
            <button
              onClick={() => setAdding(true)}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--cx-primary)',
                fontSize: 11,
                fontWeight: 800,
                cursor: 'pointer',
              }}
            >
              + 추가
            </button>
          )}
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
          {niche.keywords.map((k) => {
            const count = keywordEffect(brandName, k)
            const cold = count < 10
            return (
              <span
                key={k}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: '4px 4px 4px 10px',
                  borderRadius: 999,
                  background: cold ? '#fff8eb' : '#f6f8fd',
                  border: `1px solid ${cold ? '#f0d18f' : 'var(--cx-line-2)'}`,
                  color: cold ? '#9a6e1c' : '#5f6983',
                  fontSize: 11,
                  fontWeight: 700,
                }}
              >
                #{k}
                <span
                  style={{
                    fontSize: 10,
                    color: cold ? '#9a6e1c' : 'var(--cx-primary)',
                    fontWeight: 900,
                  }}
                >
                  {count}
                </span>
                <button
                  onClick={() => removeKw(k)}
                  title='키워드 제거'
                  style={{
                    width: 16,
                    height: 16,
                    borderRadius: 999,
                    border: 'none',
                    background: 'rgba(0,0,0,0.06)',
                    color: 'var(--cx-sub)',
                    cursor: 'pointer',
                    display: 'grid',
                    placeItems: 'center',
                    padding: 0,
                  }}
                >
                  <X className='h-3 w-3' />
                </button>
              </span>
            )
          })}
          {adding && (
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '2px 4px 2px 10px',
                borderRadius: 999,
                background: '#fff',
                border: '1px solid var(--cx-primary)',
              }}
            >
              <input
                autoFocus
                value={newKw}
                onChange={(e) => setNewKw(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') addKw()
                  if (e.key === 'Escape') {
                    setNewKw('')
                    setAdding(false)
                  }
                }}
                placeholder='키워드'
                style={{
                  border: 'none',
                  outline: 'none',
                  fontSize: 12,
                  width: 80,
                  background: 'transparent',
                }}
              />
              <button
                onClick={addKw}
                style={{
                  width: 20,
                  height: 20,
                  borderRadius: 999,
                  border: 'none',
                  background: 'var(--cx-primary)',
                  color: '#fff',
                  cursor: 'pointer',
                  fontSize: 11,
                  fontWeight: 900,
                }}
              >
                ✓
              </button>
            </span>
          )}
        </div>
      </div>

      {/* Sparkline (7-day collection trend) */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 12px',
          background: '#fbfcff',
          borderRadius: 12,
          border: '1px solid var(--cx-line-2)',
        }}
      >
        <div>
          <div style={{ fontSize: 11, fontWeight: 800, color: 'var(--cx-sub)' }}>
            7일 수집 추이
          </div>
          <div style={{ fontSize: 14, fontWeight: 900, color: 'var(--cx-text)', marginTop: 2 }}>
            {trend.reduce((a, b) => a + b, 0)}
            <span style={{ fontSize: 11, color: 'var(--cx-sub)', fontWeight: 700, marginLeft: 4 }}>
              건
            </span>
          </div>
        </div>
        <Sparkline data={trend} color='#5169ff' />
      </div>

      {/* Presets */}
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
          {niche.presets.map((p) => (
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

      {/* 4 entry actions */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(4, 1fr)',
          gap: 6,
          marginTop: 4,
          paddingTop: 10,
          borderTop: '1px solid var(--cx-line-2)',
        }}
      >
        <ActionBtn
          icon={Video}
          label='영상'
          onClick={() => onAction('videos')}
        />
        <ActionBtn
          icon={Zap}
          label='빠른 작업'
          onClick={() => onAction('quick')}
          accent
        />
        <ActionBtn
          icon={RefreshCw}
          label='자동 작업'
          onClick={() => onAction('auto')}
        />
        <ActionBtn
          icon={Edit3}
          label='프리셋'
          onClick={() => onAction('preset')}
        />
      </div>
    </div>
  )
}

function Mini({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div style={{ textAlign: 'right' }}>
      <div style={{ fontSize: 9, color: 'var(--cx-sub)', fontWeight: 800 }}>{label}</div>
      <div style={{ fontSize: 14, fontWeight: 900, color }}>{value}</div>
    </div>
  )
}

function ActionBtn({
  icon: Icon,
  label,
  onClick,
  accent,
}: {
  icon: React.ElementType
  label: string
  onClick: () => void
  accent?: boolean
}) {
  return (
    <button
      onClick={onClick}
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 4,
        padding: '8px 4px',
        borderRadius: 10,
        border: `1px solid ${accent ? '#d9dffd' : 'var(--cx-line-2)'}`,
        background: accent ? 'linear-gradient(180deg,#f6f8ff,#fff)' : '#fff',
        color: accent ? 'var(--cx-primary)' : '#4b5871',
        cursor: 'pointer',
        fontSize: 11,
        fontWeight: 800,
        transition: 'transform 0.14s ease, box-shadow 0.14s ease',
      }}
      onMouseEnter={(e) => {
        e.currentTarget.style.transform = 'translateY(-1px)'
        e.currentTarget.style.boxShadow = 'var(--cx-shadow-soft)'
      }}
      onMouseLeave={(e) => {
        e.currentTarget.style.transform = ''
        e.currentTarget.style.boxShadow = ''
      }}
    >
      <Icon className='h-4 w-4' />
      {label}
    </button>
  )
}

function Toggle({ on, onClick }: { on: boolean; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      style={{
        width: 36,
        height: 22,
        borderRadius: 999,
        border: 'none',
        cursor: 'pointer',
        position: 'relative',
        background: on ? 'linear-gradient(135deg,#5e74ff,#6d5cff)' : '#d7dff1',
        flexShrink: 0,
      }}
      aria-pressed={on}
    >
      <span
        style={{
          position: 'absolute',
          top: 3,
          left: on ? 17 : 3,
          width: 16,
          height: 16,
          borderRadius: '50%',
          background: '#fff',
          boxShadow: '0 2px 4px rgba(0,0,0,0.15)',
          transition: 'left 0.18s ease',
        }}
      />
    </button>
  )
}

function InlineModal({
  title,
  children,
  submitLabel,
  onSubmit,
  onClose,
}: {
  title: string
  children: React.ReactNode
  submitLabel: string
  onSubmit: () => void
  onClose: () => void
}) {
  return (
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
      onClick={onClose}
    >
      <div
        className='cx-card cx-card-pad'
        style={{ width: 'min(520px, 100%)', display: 'flex', flexDirection: 'column', gap: 14 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className='cx-section-head'>
          <div className='cx-section-title'>{title}</div>
          <button className='cx-btn-mini' onClick={onClose}>
            닫기
          </button>
        </div>
        {children}
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className='cx-btn-soft' onClick={onClose}>
            취소
          </button>
          <button className='cx-btn-primary' onClick={onSubmit}>
            {submitLabel}
          </button>
        </div>
      </div>
    </div>
  )
}

function FormLine({
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

export default BrandsCommex
