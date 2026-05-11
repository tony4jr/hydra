import { useMemo, useState, useEffect } from 'react'
import {
  ArrowLeft, Plus, Trash2, Copy, GitBranch, Save, Puzzle, Eye,
} from 'lucide-react'
import { useNavigate, useParams } from '@tanstack/react-router'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { useCommexStore } from '../_commex-store'
import { GLOBAL_PRESETS, type PresetSlot, type AccountKey } from '../_commex-mock'

const ACCOUNTS: AccountKey[] = ['A', 'B', 'C', 'D', 'E']

const accountColor = (a: AccountKey) =>
  ({
    A: 'linear-gradient(135deg,#ffb35a,#ff8b2f)',
    B: 'linear-gradient(135deg,#5b86ff,#3568ff)',
    C: 'linear-gradient(135deg,#30ca86,#16b364)',
    D: 'linear-gradient(135deg,#aa7cff,#7e63ff)',
    E: 'linear-gradient(135deg,#ff8a9d,#ff5879)',
  })[a]

export function NichePresetEdit() {
  const { brandId, nicheId } = useParams({
    from: '/_authenticated/brands/$brandId/niches/$nicheId/preset-edit',
  })
  const navigate = useNavigate()
  const brands = useCommexStore((s) => s.brands)
  const nichePresets = useCommexStore((s) => s.nichePresets)
  const fork = useCommexStore((s) => s.forkPresetToNiche)
  const createNP = useCommexStore((s) => s.createNichePreset)
  const updateNP = useCommexStore((s) => s.updateNichePreset)
  const deleteNP = useCommexStore((s) => s.deleteNichePreset)
  const addSlot = useCommexStore((s) => s.addSlotToNichePreset)
  const updateSlot = useCommexStore((s) => s.updateSlot)
  const deleteSlot = useCommexStore((s) => s.deleteSlot)
  const duplicateSlot = useCommexStore((s) => s.duplicateSlot)

  const brand = brands.find((b) => b.id === brandId)
  const niche = brand?.niches.find((n) => n.id === nicheId)

  const presets = nichePresets[nicheId] ?? []
  const [activePresetId, setActivePresetId] = useState<string | null>(
    presets[0]?.id ?? null
  )

  useEffect(() => {
    if (!activePresetId && presets[0]) setActivePresetId(presets[0].id)
  }, [presets, activePresetId])

  const activePreset = presets.find((p) => p.id === activePresetId)
  const [activeSlotUid, setActiveSlotUid] = useState<string | null>(
    activePreset?.slots[0]?.uid ?? null
  )
  useEffect(() => {
    if (activePreset && (!activeSlotUid || !activePreset.slots.find((s) => s.uid === activeSlotUid))) {
      setActiveSlotUid(activePreset.slots[0]?.uid ?? null)
    }
  }, [activePresetId, activePreset, activeSlotUid])

  const activeSlot = activePreset?.slots.find((s) => s.uid === activeSlotUid)

  const targetOptions = useMemo(() => {
    if (!activePreset) return ['메인 댓글']
    const labels = ['메인 댓글']
    activePreset.slots.forEach((s) => {
      if (s.target === '메인 댓글') labels.push(`${s.account}에게 답글`)
    })
    return Array.from(new Set(labels))
  }, [activePreset])

  if (!brand || !niche) {
    return (
      <>
        <Header fixed>
          <div className='ml-auto flex items-center space-x-4'>
            <ThemeSwitch />
            <ProfileDropdown />
          </div>
        </Header>
        <Main>
          <div className='hydra-page' style={{ padding: 40, textAlign: 'center' }}>
            브랜드 또는 니치를 찾을 수 없습니다.
            <div style={{ marginTop: 20 }}>
              <button className='cx-btn-soft' onClick={() => navigate({ to: '/brands' })}>
                브랜드/니치로 돌아가기
              </button>
            </div>
          </div>
        </Main>
      </>
    )
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
        <div className='hydra-page' style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
          {/* Header bar */}
          <div className='flex items-center justify-between flex-wrap gap-3'>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <button
                className='cx-icon-btn'
                onClick={() => navigate({ to: '/brands' })}
                title='브랜드/니치로'
              >
                <ArrowLeft className='h-4 w-4' />
              </button>
              <div>
                <h1 className='cx-page-h' style={{ fontSize: 18 }}>
                  {brand.name} <span style={{ color: 'var(--cx-sub)' }}>·</span> {niche.name}
                </h1>
                <p className='cx-page-sub' style={{ marginTop: 2 }}>
                  이 니치 전용 프리셋을 만들고 슬롯을 편집합니다. 글로벌은 복제해서 시작.
                </p>
              </div>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className='cx-btn-soft'
                onClick={() => toast.info('미리보기는 다음 PR — slot 편집은 이미 저장됩니다')}
              >
                <Eye className='inline h-4 w-4 mr-1.5' />미리보기
              </button>
              <button
                className='cx-btn-primary'
                onClick={() => toast.success('저장됨', { description: '자동 저장 — 변경 즉시 반영' })}
              >
                <Save className='inline h-4 w-4 mr-1.5' />저장
              </button>
            </div>
          </div>

          {/* 3-pane */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '300px 1fr 320px',
              gap: 14,
              minHeight: '70vh',
            }}
            className='cx-preset-edit-grid'
          >
            {/* LEFT: Preset pool */}
            <div className='cx-card cx-card-pad' style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              {/* Niche-specific presets */}
              <div>
                <div
                  style={{
                    fontSize: 11, fontWeight: 800, color: 'var(--cx-sub)',
                    textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8,
                  }}
                >
                  니치 전용 프리셋 ({presets.length})
                </div>
                {presets.length === 0 ? (
                  <div
                    style={{
                      padding: 14, borderRadius: 12, border: '1px dashed var(--cx-line)',
                      background: '#fbfcff', fontSize: 12, color: 'var(--cx-sub)', textAlign: 'center',
                    }}
                  >
                    아직 없음. 아래 글로벌에서 복제하거나<br />새로 만들기
                  </div>
                ) : (
                  <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                    {presets.map((np) => (
                      <button
                        key={np.id}
                        onClick={() => setActivePresetId(np.id)}
                        style={{
                          textAlign: 'left', padding: 10, borderRadius: 10,
                          border: `1px solid ${activePresetId === np.id ? '#ccd6ff' : 'var(--cx-line-2)'}`,
                          background: activePresetId === np.id ? '#f6f8ff' : '#fff',
                          cursor: 'pointer',
                        }}
                      >
                        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6 }}>
                          <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--cx-text)', minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {np.name}
                          </div>
                          <span
                            onClick={(e) => {
                              e.stopPropagation()
                              if (!confirm(`'${np.name}' 프리셋을 삭제할까요?`)) return
                              deleteNP(np.id)
                              if (activePresetId === np.id) setActivePresetId(null)
                              toast.success('프리셋 삭제됨')
                            }}
                            role='button'
                            title='삭제'
                            style={{
                              width: 20, height: 20, borderRadius: 6,
                              display: 'grid', placeItems: 'center',
                              color: '#d2554c', cursor: 'pointer', flexShrink: 0,
                            }}
                          >
                            <Trash2 className='h-3 w-3' />
                          </span>
                        </div>
                        <div style={{ fontSize: 11, color: 'var(--cx-sub)', marginTop: 2 }}>
                          {np.slots.length} 슬롯 · {np.forked_from ? '글로벌 복제' : '직접 작성'}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
                <button
                  className='cx-btn-soft'
                  style={{ width: '100%', height: 36, fontSize: 12, marginTop: 8 }}
                  onClick={() => {
                    const name = prompt('새 니치 전용 프리셋 이름?', `${niche.name} 프리셋`)
                    if (!name?.trim()) return
                    const id = createNP(nicheId, name.trim())
                    setActivePresetId(id)
                    toast.success(`${name} 생성됨`)
                  }}
                >
                  <Plus className='inline h-3 w-3 mr-1' />빈 프리셋 새로 만들기
                </button>
              </div>

              {/* Global preset pool */}
              <div style={{ borderTop: '1px solid var(--cx-line-2)', paddingTop: 12 }}>
                <div
                  style={{
                    fontSize: 11, fontWeight: 800, color: 'var(--cx-sub)',
                    textTransform: 'uppercase', letterSpacing: '0.04em', marginBottom: 8,
                  }}
                >
                  글로벌 프리셋 ({GLOBAL_PRESETS.length})
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                  {GLOBAL_PRESETS.map((g) => (
                    <div
                      key={g.id}
                      style={{
                        padding: 10, borderRadius: 10,
                        border: '1px solid var(--cx-line-2)',
                        background: '#fff',
                        display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 6,
                      }}
                    >
                      <div style={{ minWidth: 0, flex: 1 }}>
                        <div style={{ fontSize: 12, fontWeight: 800, color: 'var(--cx-text)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          <Puzzle className='inline h-3 w-3 mr-1' style={{ color: '#6758ff' }} />
                          {g.name}
                        </div>
                        <div style={{ fontSize: 10, color: 'var(--cx-sub)', marginTop: 1 }}>
                          {(g.slots?.length ?? 0)} 슬롯 · {g.version}
                        </div>
                      </div>
                      <button
                        className='cx-btn-mini'
                        style={{ fontSize: 11, padding: '4px 8px', height: 26, flexShrink: 0 }}
                        title='이 니치 전용으로 복제하여 편집'
                        onClick={() => {
                          const id = fork(nicheId, g.id)
                          if (id) {
                            setActivePresetId(id)
                            toast.success(`${g.name} 복제됨`)
                          }
                        }}
                      >
                        <GitBranch className='h-3 w-3' />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* CENTER: Slot editor */}
            <div className='cx-card cx-card-pad' style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {!activePreset ? (
                <div
                  style={{
                    flex: 1, display: 'grid', placeItems: 'center',
                    color: 'var(--cx-sub)', fontSize: 13, textAlign: 'center', padding: 40,
                  }}
                >
                  좌측에서 프리셋을 선택하거나<br />글로벌 프리셋을 복제하여 시작하세요.
                </div>
              ) : (
                <>
                  {/* Preset header */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                    <input
                      className='cx-input'
                      value={activePreset.name}
                      onChange={(e) => updateNP(activePreset.id, { name: e.target.value })}
                      style={{ fontSize: 16, fontWeight: 800, flex: 1, height: 40 }}
                    />
                    {activePreset.forked_from && (
                      <span style={{ fontSize: 11, color: 'var(--cx-sub)', fontWeight: 700 }}>
                        ← {GLOBAL_PRESETS.find(g => g.id === activePreset.forked_from)?.name}
                      </span>
                    )}
                  </div>
                  <input
                    className='cx-input'
                    value={activePreset.desc}
                    onChange={(e) => updateNP(activePreset.id, { desc: e.target.value })}
                    placeholder='프리셋 설명 (운영자용 메모)'
                    style={{ fontSize: 13, height: 36 }}
                  />

                  {/* Slot tabs (compact) */}
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 4 }}>
                    {activePreset.slots.map((sl) => {
                      const isReply = sl.target !== '메인 댓글'
                      return (
                        <button
                          key={sl.uid}
                          onClick={() => setActiveSlotUid(sl.uid)}
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 6,
                            padding: '6px 10px', borderRadius: 999,
                            border: `1px solid ${activeSlotUid === sl.uid ? '#ccd6ff' : 'var(--cx-line)'}`,
                            background: activeSlotUid === sl.uid ? '#f6f8ff' : '#fff',
                            cursor: 'pointer',
                            opacity: sl.active ? 1 : 0.5,
                          }}
                        >
                          <span
                            style={{
                              width: 18, height: 18, borderRadius: 999,
                              background: accountColor(sl.account),
                              color: '#fff', fontSize: 10, fontWeight: 900,
                              display: 'grid', placeItems: 'center',
                            }}
                          >
                            {sl.account}
                          </span>
                          <span style={{ fontSize: 12, fontWeight: 700 }}>
                            {isReply ? `↳ ${sl.target}` : '메인'}
                          </span>
                        </button>
                      )
                    })}
                    <button
                      onClick={() => {
                        const used = new Set(activePreset.slots.map(s => s.account))
                        const next = ACCOUNTS.find(a => !used.has(a)) ?? 'A'
                        addSlot(activePreset.id, { account: next, target: '메인 댓글' })
                        toast.success('슬롯 추가됨')
                      }}
                      className='cx-btn-mini'
                      style={{ height: 30 }}
                    >
                      <Plus className='inline h-3 w-3 mr-1' />슬롯
                    </button>
                  </div>

                  {/* Slot detail editor */}
                  {activeSlot ? (
                    <div
                      style={{
                        flex: 1, display: 'flex', flexDirection: 'column', gap: 12,
                        marginTop: 8,
                      }}
                    >
                      {/* Row: account / target / active */}
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap' }}>
                        <select
                          className='cx-input'
                          style={{ width: 100, height: 36, padding: '6px 30px 6px 12px', fontSize: 13 }}
                          value={activeSlot.account}
                          onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { account: e.target.value as AccountKey })}
                        >
                          {ACCOUNTS.map(a => <option key={a} value={a}>계정 {a}</option>)}
                        </select>
                        <select
                          className='cx-input'
                          style={{ minWidth: 150, height: 36, padding: '6px 30px 6px 12px', fontSize: 13 }}
                          value={activeSlot.target}
                          onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { target: e.target.value })}
                        >
                          {targetOptions.map(t => <option key={t} value={t}>{t}</option>)}
                        </select>
                        <span style={{ flex: 1 }} />
                        <label
                          style={{
                            display: 'inline-flex', alignItems: 'center', gap: 6,
                            padding: '6px 10px', borderRadius: 999,
                            background: activeSlot.active ? '#e9fbf1' : '#fff0ef',
                            color: activeSlot.active ? '#16b364' : '#d2554c',
                            fontSize: 11, fontWeight: 800, cursor: 'pointer',
                            border: `1px solid ${activeSlot.active ? '#bff0d3' : '#f4cccb'}`,
                          }}
                        >
                          <input
                            type='checkbox'
                            checked={activeSlot.active}
                            onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { active: e.target.checked })}
                            style={{ width: 14, height: 14 }}
                          />
                          {activeSlot.active ? '활성' : '비활성'}
                        </label>
                        <button
                          className='cx-icon-btn'
                          onClick={() => { duplicateSlot(activePreset.id, activeSlot.uid); toast.success('복제됨') }}
                          title='복제'
                        ><Copy className='h-4 w-4' /></button>
                        <button
                          className='cx-icon-btn'
                          style={{ color: '#d2554c' }}
                          onClick={() => {
                            if (activePreset.slots.length <= 1) {
                              toast.warning('최소 1개 슬롯 필요')
                              return
                            }
                            if (!confirm('이 슬롯을 삭제할까요?')) return
                            deleteSlot(activePreset.id, activeSlot.uid)
                          }}
                          title='삭제'
                        ><Trash2 className='h-4 w-4' /></button>
                      </div>

                      {/* Section: 기본 내용 */}
                      <Section title='1. 기본 내용'>
                        <Field label='의도 (intent)'>
                          <textarea
                            className='cx-input'
                            style={{ minHeight: 60, resize: 'vertical', fontSize: 13 }}
                            value={activeSlot.intent}
                            onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { intent: e.target.value })}
                          />
                        </Field>
                        <Field label='톤 anchor (예시 문장)'>
                          <textarea
                            className='cx-input'
                            style={{ minHeight: 60, resize: 'vertical', fontSize: 13 }}
                            value={activeSlot.tone_anchor}
                            onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { tone_anchor: e.target.value })}
                          />
                        </Field>
                        <Field label='legacy_text_template (선택)' help='비워두면 intent 사용'>
                          <textarea
                            className='cx-input'
                            style={{ minHeight: 50, resize: 'vertical', fontSize: 13 }}
                            value={activeSlot.legacy_text_template ?? ''}
                            onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { legacy_text_template: e.target.value })}
                          />
                        </Field>
                      </Section>

                      {/* Section: AI 가이드 */}
                      <Section title='2. AI 작성 가이드'>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                          <Field label='길이'>
                            <select
                              className='cx-input'
                              value={activeSlot.length}
                              onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { length: e.target.value as PresetSlot['length'] })}
                            >
                              <option value='short'>짧게</option>
                              <option value='normal'>보통</option>
                              <option value='long'>길게</option>
                            </select>
                          </Field>
                          <Field label='이모지'>
                            <select
                              className='cx-input'
                              value={activeSlot.emoji}
                              onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { emoji: e.target.value as PresetSlot['emoji'] })}
                            >
                              <option value='never'>안 함</option>
                              <option value='sometimes'>가끔</option>
                              <option value='often'>자주</option>
                            </select>
                          </Field>
                        </div>
                        <Field label={`AI 자유도 ${activeSlot.ai_freedom}%`}>
                          <input
                            type='range' min={0} max={100} step={5}
                            value={activeSlot.ai_freedom}
                            onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { ai_freedom: Number(e.target.value) })}
                            style={{ width: '100%', accentColor: 'var(--cx-primary)' }}
                          />
                        </Field>
                      </Section>

                      {/* Section: 멘션/스타일 */}
                      <Section title='3. 멘션 정책 + 스타일'>
                        <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap' }}>
                          <ToggleLabel
                            checked={activeSlot.mention_brand}
                            onChange={v => updateSlot(activePreset.id, activeSlot.uid, { mention_brand: v })}
                            label='브랜드 멘션'
                          />
                          <ToggleLabel
                            checked={activeSlot.mention_solution}
                            onChange={v => updateSlot(activePreset.id, activeSlot.uid, { mention_solution: v })}
                            label='솔루션 키워드'
                          />
                          <ToggleLabel
                            checked={activeSlot.reduce_repetition}
                            onChange={v => updateSlot(activePreset.id, activeSlot.uid, { reduce_repetition: v })}
                            label='반복 최소화'
                          />
                        </div>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginTop: 10 }}>
                          <Field label='어조'>
                            <select
                              className='cx-input'
                              value={activeSlot.style_polite}
                              onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { style_polite: e.target.value as PresetSlot['style_polite'] })}
                            >
                              <option value='natural'>자연스럽게</option>
                              <option value='polite'>정중하게</option>
                              <option value='friendly'>친근하게</option>
                            </select>
                          </Field>
                          <Field label='시점'>
                            <select
                              className='cx-input'
                              value={activeSlot.style_pov}
                              onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { style_pov: e.target.value as PresetSlot['style_pov'] })}
                            >
                              <option value='apply'>적용형</option>
                              <option value='experience'>경험형</option>
                              <option value='question'>질문형</option>
                            </select>
                          </Field>
                        </div>
                      </Section>

                      {/* Section: 반응 목표 */}
                      <Section title='4. 반응 목표'>
                        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10 }}>
                          <Field label='좋아요 최소'>
                            <input
                              type='number' className='cx-input'
                              value={activeSlot.like_min}
                              onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { like_min: Number(e.target.value) })}
                            />
                          </Field>
                          <Field label='좋아요 최대'>
                            <input
                              type='number' className='cx-input'
                              value={activeSlot.like_max}
                              onChange={(e) => updateSlot(activePreset.id, activeSlot.uid, { like_max: Number(e.target.value) })}
                            />
                          </Field>
                        </div>
                      </Section>
                    </div>
                  ) : (
                    <div style={{ color: 'var(--cx-sub)', fontSize: 13, padding: 20 }}>슬롯을 선택하세요</div>
                  )}
                </>
              )}
            </div>

            {/* RIGHT: Preview / Summary */}
            <div className='cx-card cx-card-pad' style={{ display: 'flex', flexDirection: 'column', gap: 14 }}>
              <div className='cx-section-head' style={{ marginBottom: 6 }}>
                <div className='cx-section-title' style={{ fontSize: 14 }}>슬롯 요약</div>
              </div>
              {!activePreset ? (
                <div style={{ color: 'var(--cx-sub)', fontSize: 12 }}>프리셋 선택 시 표시</div>
              ) : (
                <>
                  {activePreset.slots.map((sl) => {
                    const isReply = sl.target !== '메인 댓글'
                    return (
                      <div
                        key={sl.uid}
                        onClick={() => setActiveSlotUid(sl.uid)}
                        style={{
                          padding: 10, borderRadius: 12,
                          border: `1px solid ${activeSlotUid === sl.uid ? '#ccd6ff' : 'var(--cx-line-2)'}`,
                          background: activeSlotUid === sl.uid ? '#f6f8ff' : '#fff',
                          cursor: 'pointer',
                          marginLeft: isReply ? 12 : 0,
                          borderLeft: isReply ? '2px solid var(--cx-primary)' : undefined,
                          opacity: sl.active ? 1 : 0.5,
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                          <span
                            style={{
                              width: 22, height: 22, borderRadius: 999,
                              background: accountColor(sl.account),
                              color: '#fff', fontSize: 11, fontWeight: 900,
                              display: 'grid', placeItems: 'center', flexShrink: 0,
                            }}
                          >
                            {sl.account}
                          </span>
                          <div style={{ flex: 1, minWidth: 0 }}>
                            <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--cx-text)' }}>
                              {isReply ? `↳ ${sl.target}` : '메인 댓글'}
                            </div>
                            <div style={{
                              fontSize: 11, color: 'var(--cx-sub)',
                              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                            }}>
                              {sl.tone_anchor || sl.intent || '(내용 없음)'}
                            </div>
                          </div>
                        </div>
                        <div style={{
                          display: 'flex', gap: 8, marginTop: 6,
                          fontSize: 10, color: 'var(--cx-sub)',
                        }}>
                          <span>❤ {sl.like_min}~{sl.like_max}</span>
                          <span>· {sl.length}</span>
                          <span>· AI {sl.ai_freedom}%</span>
                        </div>
                      </div>
                    )
                  })}

                  <div
                    style={{
                      marginTop: 6, padding: 12, borderRadius: 12,
                      background: '#fbfcff', border: '1px solid var(--cx-line-2)',
                      fontSize: 11, color: 'var(--cx-sub)', lineHeight: 1.6,
                    }}
                  >
                    <b style={{ color: 'var(--cx-text)' }}>정책 요약</b><br />
                    슬롯 {activePreset.slots.length}개 · 활성 {activePreset.slots.filter(s => s.active).length}개<br />
                    멘션 브랜드 {activePreset.slots.filter(s => s.mention_brand).length} / 솔루션 {activePreset.slots.filter(s => s.mention_solution).length}
                  </div>

                  <div
                    style={{
                      marginTop: 6, padding: 12, borderRadius: 12,
                      background: 'linear-gradient(180deg,#f3fdf6,#fff)',
                      border: '1px solid #bff0d3',
                      fontSize: 11, color: '#3a8a64', lineHeight: 1.5,
                    }}
                  >
                    💡 <b>다음 PR 예정</b><br />
                    실시간 댓글 미리보기, AI 개선 제안, 과거 성과 배지, 드래그&드롭 fork
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      </Main>
    </>
  )
}

// =================================================================
// helpers
// =================================================================

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div
      style={{
        padding: 14, borderRadius: 14,
        border: '1px solid var(--cx-line-2)',
        background: '#fbfcff',
      }}
    >
      <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--cx-text)', marginBottom: 10 }}>
        {title}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>{children}</div>
    </div>
  )
}

function Field({ label, help, children }: { label: string; help?: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <label style={{ fontSize: 11, fontWeight: 800, color: '#44506a' }}>{label}</label>
      {children}
      {help && <span style={{ fontSize: 10, color: 'var(--cx-sub)' }}>{help}</span>}
    </div>
  )
}

function ToggleLabel({
  checked, onChange, label,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
}) {
  return (
    <label
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 6,
        padding: '6px 10px', borderRadius: 999,
        background: checked ? '#eef0ff' : '#fff',
        border: `1px solid ${checked ? '#d9dffd' : 'var(--cx-line)'}`,
        color: checked ? 'var(--cx-primary)' : '#5f6983',
        fontSize: 11, fontWeight: 700, cursor: 'pointer',
      }}
    >
      <input
        type='checkbox'
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 14, height: 14 }}
      />
      {label}
    </label>
  )
}

export default NichePresetEdit
