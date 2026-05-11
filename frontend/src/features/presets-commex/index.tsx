import { useState } from 'react'
import { Plus, Puzzle, X, MessageSquare, CornerDownRight } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { GLOBAL_PRESETS, type GlobalPreset, type PresetSlot, type AccountKey } from '../_commex-mock'

const STORAGE_KEY = 'commex-presets-v1'
const ACCOUNTS: AccountKey[] = ['A', 'B', 'C', 'D', 'E']

const accountColor = (a: AccountKey) =>
  ({
    A: 'linear-gradient(135deg,#ffb35a,#ff8b2f)',
    B: 'linear-gradient(135deg,#5b86ff,#3568ff)',
    C: 'linear-gradient(135deg,#30ca86,#16b364)',
    D: 'linear-gradient(135deg,#aa7cff,#7e63ff)',
    E: 'linear-gradient(135deg,#ff8a9d,#ff5879)',
  })[a]

export function PresetsCommex() {
  const tones = ['cx-bg-purple', 'cx-bg-blue', 'cx-bg-green', 'cx-bg-orange'] as const
  const [presets, setPresets] = useState<GlobalPreset[]>(loadPresets)
  const [activeId, setActiveId] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [newForm, setNewForm] = useState({ name: '', desc: '' })

  const persist = (next: GlobalPreset[]) => {
    setPresets(next)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }
  const activePreset = presets.find((p) => p.id === activeId) ?? null

  const updatePreset = (id: string, patch: Partial<GlobalPreset>) => {
    persist(presets.map((p) => (p.id === id ? { ...p, ...patch } : p)))
  }
  const updateSlot = (presetId: string, slotUid: string, patch: Partial<PresetSlot>) => {
    persist(
      presets.map((p) =>
        p.id !== presetId
          ? p
          : {
              ...p,
              slots: (p.slots ?? []).map((s) => (s.uid === slotUid ? { ...s, ...patch } : s)),
            }
      )
    )
  }
  const addSlot = (presetId: string) => {
    persist(
      presets.map((p) => {
        if (p.id !== presetId) return p
        const used = new Set((p.slots ?? []).map((s) => s.account))
        const next = ACCOUNTS.find((a) => !used.has(a)) ?? 'A'
        const slot: PresetSlot = {
          uid: 's-' + Math.random().toString(36).slice(2, 8),
          account: next,
          target: '메인 댓글',
          active: true,
          intent: '',
          tone_anchor: '',
          legacy_text_template: '',
          length: 'normal',
          emoji: 'sometimes',
          ai_freedom: 70,
          mention_brand: false,
          mention_solution: true,
          style_polite: 'natural',
          style_pov: 'experience',
          reduce_repetition: true,
          like_min: 5,
          like_max: 20,
        }
        return { ...p, slots: [...(p.slots ?? []), slot] }
      })
    )
  }
  const deleteSlot = (presetId: string, slotUid: string) => {
    persist(
      presets.map((p) =>
        p.id !== presetId
          ? p
          : { ...p, slots: (p.slots ?? []).filter((s) => s.uid !== slotUid) }
      )
    )
  }
  const deletePreset = (id: string) => {
    persist(presets.filter((p) => p.id !== id))
    if (activeId === id) setActiveId(null)
  }

  const createPreset = () => {
    const name = newForm.name.trim()
    if (!name) {
      toast.warning('프리셋 이름을 입력하세요')
      return
    }
    const id = `gp-${Date.now().toString(36)}`
    persist([
      {
        id,
        name,
        desc: newForm.desc.trim() || '새 프리셋',
        used: 0,
        version: 'v1.0',
        slots: [],
      },
      ...presets,
    ])
    setNewForm({ name: '', desc: '' })
    setCreating(false)
    setActiveId(id)
    toast.success(`${name} 생성됨`)
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
        <div className='hydra-page' style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div className='flex items-end justify-between flex-wrap gap-3'>
            <div>
              <h1 className='cx-page-h'>글로벌 프리셋</h1>
              <p className='cx-page-sub'>
                여러 브랜드/니치에서 재사용할 수 있는 프리셋 라이브러리. 카드를 클릭해 슬롯을 편집하세요.
              </p>
            </div>
            <button className='cx-btn-primary' onClick={() => setCreating(true)}>
              <Plus className='inline h-4 w-4 mr-1' />새 프리셋
            </button>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 14,
            }}
          >
            {presets.map((p, i) => {
              const slotCount = p.slots?.length ?? 0
              const replyCount = (p.slots ?? []).filter(
                (s) => s.target !== '메인 댓글'
              ).length
              return (
                <div
                  key={p.id}
                  className='cx-card cx-card-pad cx-card-hover'
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 10,
                    cursor: 'pointer',
                  }}
                  onClick={() => setActiveId(p.id)}
                >
                  <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                    <span
                      className={`cx-kpi-circle ${tones[i % 4]}`}
                      style={{ width: 40, height: 40 }}
                    >
                      <Puzzle className='h-4 w-4' />
                    </span>
                    <span style={{ fontSize: 11, color: 'var(--cx-sub)', fontWeight: 800 }}>
                      {p.version}
                    </span>
                  </div>
                  <h4
                    style={{
                      margin: 0,
                      fontSize: 16,
                      fontWeight: 800,
                      color: 'var(--cx-text)',
                    }}
                  >
                    {p.name}
                  </h4>
                  <p
                    style={{
                      margin: 0,
                      fontSize: 13,
                      color: 'var(--cx-sub)',
                      lineHeight: 1.5,
                      flex: 1,
                    }}
                  >
                    {p.desc}
                  </p>
                  {/* 슬롯 미니 요약 */}
                  <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                    {(p.slots ?? []).slice(0, 5).map((s) => (
                      <span
                        key={s.uid}
                        title={s.intent || s.tone_anchor}
                        style={{
                          width: 22,
                          height: 22,
                          borderRadius: 999,
                          background: accountColor(s.account),
                          color: '#fff',
                          fontSize: 11,
                          fontWeight: 900,
                          display: 'grid',
                          placeItems: 'center',
                        }}
                      >
                        {s.account}
                      </span>
                    ))}
                  </div>
                  <div
                    style={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      fontSize: 12,
                      fontWeight: 800,
                      paddingTop: 8,
                      borderTop: '1px solid var(--cx-line-2)',
                    }}
                  >
                    <span style={{ color: 'var(--cx-primary)' }}>
                      슬롯 {slotCount} · 답글 {replyCount}
                    </span>
                    <span style={{ color: 'var(--cx-sub)' }}>
                      {p.used.toLocaleString()}회 사용
                    </span>
                  </div>
                </div>
              )
            })}
          </div>

          {creating && (
            <NewPresetModal
              form={newForm}
              onChange={setNewForm}
              onClose={() => {
                setCreating(false)
                setNewForm({ name: '', desc: '' })
              }}
              onSubmit={createPreset}
            />
          )}

          {activePreset && (
            <PresetDetailDrawer
              preset={activePreset}
              onClose={() => setActiveId(null)}
              onUpdatePreset={(patch) => updatePreset(activePreset.id, patch)}
              onUpdateSlot={(uid, patch) => updateSlot(activePreset.id, uid, patch)}
              onAddSlot={() => addSlot(activePreset.id)}
              onDeleteSlot={(uid) => deleteSlot(activePreset.id, uid)}
              onDeletePreset={() => {
                if (!confirm(`${activePreset.name} 프리셋을 삭제할까요?`)) return
                deletePreset(activePreset.id)
                toast.success('삭제됨')
              }}
            />
          )}
        </div>
      </Main>
    </>
  )
}

function loadPresets(): GlobalPreset[] {
  if (typeof window === 'undefined') return GLOBAL_PRESETS
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return GLOBAL_PRESETS
  try {
    const parsed = JSON.parse(raw) as GlobalPreset[]
    // 슬롯 데이터가 비어있는 옛 저장본이면 기본 데이터로 교체
    if (Array.isArray(parsed) && parsed.length > 0 && parsed.every((p) => !p.slots?.length)) {
      return GLOBAL_PRESETS
    }
    return parsed
  } catch {
    return GLOBAL_PRESETS
  }
}

// =================================================================
// 상세 드로어 — 우측 슬라이드 인
// =================================================================

function PresetDetailDrawer({
  preset,
  onClose,
  onUpdatePreset,
  onUpdateSlot,
  onAddSlot,
  onDeleteSlot,
  onDeletePreset,
}: {
  preset: GlobalPreset
  onClose: () => void
  onUpdatePreset: (patch: Partial<GlobalPreset>) => void
  onUpdateSlot: (uid: string, patch: Partial<PresetSlot>) => void
  onAddSlot: () => void
  onDeleteSlot: (uid: string) => void
  onDeletePreset: () => void
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        background: 'rgba(15,23,42,0.45)',
        display: 'flex',
        justifyContent: 'flex-end',
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 'min(720px, 100%)',
          height: '100%',
          background: '#fff',
          overflow: 'auto',
          boxShadow: '-12px 0 40px rgba(15,23,42,0.18)',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '18px 22px',
            borderBottom: '1px solid var(--cx-line)',
            display: 'flex',
            alignItems: 'flex-start',
            justifyContent: 'space-between',
            gap: 10,
          }}
        >
          <div style={{ flex: 1, minWidth: 0 }}>
            <input
              className='cx-input'
              value={preset.name}
              onChange={(e) => onUpdatePreset({ name: e.target.value })}
              style={{ fontSize: 16, fontWeight: 800, height: 38, marginBottom: 6 }}
            />
            <input
              className='cx-input'
              value={preset.desc}
              onChange={(e) => onUpdatePreset({ desc: e.target.value })}
              placeholder='설명'
              style={{ fontSize: 12, height: 32 }}
            />
            <div style={{ fontSize: 11, color: 'var(--cx-sub)', marginTop: 8 }}>
              버전 {preset.version} · {preset.used.toLocaleString()}회 사용
            </div>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
            <button className='cx-icon-btn' onClick={onClose} title='닫기'>
              <X className='h-4 w-4' />
            </button>
            <button
              className='cx-btn-mini'
              onClick={onDeletePreset}
              style={{
                color: '#d2554c',
                borderColor: '#f4cccb',
                fontSize: 11,
                padding: '4px 10px',
              }}
            >
              삭제
            </button>
          </div>
        </div>

        {/* Slots */}
        <div style={{ padding: 18, display: 'flex', flexDirection: 'column', gap: 12, flex: 1 }}>
          <div
            style={{
              display: 'flex',
              justifyContent: 'space-between',
              alignItems: 'center',
              marginBottom: 4,
            }}
          >
            <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--cx-text)' }}>
              슬롯 ({preset.slots?.length ?? 0})
            </div>
            <button className='cx-btn-mini' onClick={onAddSlot}>
              <Plus className='inline h-3 w-3 mr-1' />슬롯 추가
            </button>
          </div>

          {!preset.slots?.length ? (
            <div
              style={{
                padding: 30,
                borderRadius: 14,
                border: '1px dashed var(--cx-line)',
                background: '#fbfcff',
                color: 'var(--cx-sub)',
                fontSize: 12,
                textAlign: 'center',
              }}
            >
              아직 슬롯이 없습니다. 위 '+ 슬롯 추가' 로 시작하세요.
            </div>
          ) : (
            preset.slots.map((s) => (
              <SlotRow
                key={s.uid}
                slot={s}
                allSlots={preset.slots ?? []}
                onChange={(patch) => onUpdateSlot(s.uid, patch)}
                onDelete={() => {
                  if (!confirm('이 슬롯을 삭제할까요?')) return
                  onDeleteSlot(s.uid)
                }}
              />
            ))
          )}
        </div>
      </div>
    </div>
  )
}

function SlotRow({
  slot,
  allSlots,
  onChange,
  onDelete,
}: {
  slot: PresetSlot
  allSlots: PresetSlot[]
  onChange: (patch: Partial<PresetSlot>) => void
  onDelete: () => void
}) {
  const [expanded, setExpanded] = useState(false)
  const isReply = slot.target !== '메인 댓글'
  const targetOptions = ['메인 댓글', ...allSlots
    .filter((s) => s.uid !== slot.uid && s.target === '메인 댓글')
    .map((s) => `${s.account}에게 답글`)]

  return (
    <div
      style={{
        padding: 12,
        borderRadius: 14,
        border: '1px solid var(--cx-line-2)',
        background: '#fff',
        marginLeft: isReply ? 16 : 0,
        borderLeft: isReply ? '2px solid var(--cx-primary)' : '1px solid var(--cx-line-2)',
      }}
    >
      {/* Compact header */}
      <div
        style={{ display: 'flex', alignItems: 'center', gap: 8 }}
        onClick={() => setExpanded((v) => !v)}
      >
        <span
          style={{
            width: 28,
            height: 28,
            borderRadius: 999,
            background: accountColor(slot.account),
            color: '#fff',
            fontSize: 12,
            fontWeight: 900,
            display: 'grid',
            placeItems: 'center',
            flexShrink: 0,
          }}
        >
          {slot.account}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div
            style={{
              fontSize: 12,
              fontWeight: 800,
              color: 'var(--cx-text)',
              display: 'flex',
              alignItems: 'center',
              gap: 6,
            }}
          >
            {isReply ? (
              <CornerDownRight className='h-3 w-3' style={{ color: 'var(--cx-sub)' }} />
            ) : (
              <MessageSquare className='h-3 w-3' style={{ color: 'var(--cx-sub)' }} />
            )}
            {slot.target}
          </div>
          <div
            style={{
              fontSize: 11,
              color: 'var(--cx-sub)',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
              marginTop: 2,
            }}
          >
            {slot.tone_anchor || slot.intent || '(내용 없음)'}
          </div>
        </div>
        <div style={{ display: 'flex', gap: 6, fontSize: 10, color: 'var(--cx-sub)' }}>
          <span>❤ {slot.like_min}~{slot.like_max}</span>
          <span>· AI {slot.ai_freedom}%</span>
        </div>
        <button
          className='cx-btn-mini'
          style={{ fontSize: 11, padding: '4px 8px', height: 26 }}
          onClick={(e) => {
            e.stopPropagation()
            setExpanded((v) => !v)
          }}
        >
          {expanded ? '접기' : '편집'}
        </button>
      </div>

      {/* Expanded body */}
      {expanded && (
        <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 10 }}>
          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <select
              className='cx-input'
              style={{ width: 100, height: 32, padding: '4px 26px 4px 10px', fontSize: 12 }}
              value={slot.account}
              onChange={(e) => onChange({ account: e.target.value as AccountKey })}
            >
              {ACCOUNTS.map((a) => (
                <option key={a} value={a}>계정 {a}</option>
              ))}
            </select>
            <select
              className='cx-input'
              style={{ minWidth: 130, height: 32, padding: '4px 26px 4px 10px', fontSize: 12 }}
              value={slot.target}
              onChange={(e) => onChange({ target: e.target.value })}
            >
              {targetOptions.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <button
              className='cx-btn-mini'
              style={{ marginLeft: 'auto', color: '#d2554c', borderColor: '#f4cccb', fontSize: 11 }}
              onClick={onDelete}
            >
              슬롯 삭제
            </button>
          </div>

          <Field label='의도 (intent)'>
            <textarea
              className='cx-input'
              style={{ minHeight: 50, resize: 'vertical', fontSize: 12 }}
              value={slot.intent}
              onChange={(e) => onChange({ intent: e.target.value })}
            />
          </Field>
          <Field label='톤 anchor'>
            <textarea
              className='cx-input'
              style={{ minHeight: 50, resize: 'vertical', fontSize: 12 }}
              value={slot.tone_anchor}
              onChange={(e) => onChange({ tone_anchor: e.target.value })}
            />
          </Field>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8 }}>
            <Field label='길이'>
              <select
                className='cx-input'
                value={slot.length}
                onChange={(e) => onChange({ length: e.target.value as PresetSlot['length'] })}
                style={{ height: 32, fontSize: 12 }}
              >
                <option value='short'>짧게</option>
                <option value='normal'>보통</option>
                <option value='long'>길게</option>
              </select>
            </Field>
            <Field label='이모지'>
              <select
                className='cx-input'
                value={slot.emoji}
                onChange={(e) => onChange({ emoji: e.target.value as PresetSlot['emoji'] })}
                style={{ height: 32, fontSize: 12 }}
              >
                <option value='never'>안 함</option>
                <option value='sometimes'>가끔</option>
                <option value='often'>자주</option>
              </select>
            </Field>
            <Field label={`AI ${slot.ai_freedom}%`}>
              <input
                type='range'
                min={0}
                max={100}
                step={5}
                value={slot.ai_freedom}
                onChange={(e) => onChange({ ai_freedom: Number(e.target.value) })}
                style={{ width: '100%', accentColor: 'var(--cx-primary)' }}
              />
            </Field>
          </div>

          <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
            <CheckPill
              checked={slot.mention_brand}
              onChange={(v) => onChange({ mention_brand: v })}
              label='브랜드 멘션'
            />
            <CheckPill
              checked={slot.mention_solution}
              onChange={(v) => onChange({ mention_solution: v })}
              label='솔루션 키워드'
            />
            <CheckPill
              checked={slot.reduce_repetition}
              onChange={(v) => onChange({ reduce_repetition: v })}
              label='반복 최소화'
            />
          </div>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
            <Field label='좋아요 최소'>
              <input
                type='number'
                className='cx-input'
                value={slot.like_min}
                onChange={(e) => onChange({ like_min: Number(e.target.value) })}
                style={{ height: 32, fontSize: 12 }}
              />
            </Field>
            <Field label='좋아요 최대'>
              <input
                type='number'
                className='cx-input'
                value={slot.like_max}
                onChange={(e) => onChange({ like_max: Number(e.target.value) })}
                style={{ height: 32, fontSize: 12 }}
              />
            </Field>
          </div>
        </div>
      )}
    </div>
  )
}

function CheckPill({
  checked,
  onChange,
  label,
}: {
  checked: boolean
  onChange: (v: boolean) => void
  label: string
}) {
  return (
    <label
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '5px 10px',
        borderRadius: 999,
        background: checked ? '#eef0ff' : '#fff',
        border: `1px solid ${checked ? '#d9dffd' : 'var(--cx-line)'}`,
        color: checked ? 'var(--cx-primary)' : '#5f6983',
        fontSize: 11,
        fontWeight: 700,
        cursor: 'pointer',
      }}
    >
      <input
        type='checkbox'
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ width: 13, height: 13 }}
      />
      {label}
    </label>
  )
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <span style={{ fontSize: 11, color: '#44506a', fontWeight: 800 }}>{label}</span>
      {children}
    </label>
  )
}

function NewPresetModal({
  form,
  onChange,
  onClose,
  onSubmit,
}: {
  form: { name: string; desc: string }
  onChange: (next: { name: string; desc: string }) => void
  onClose: () => void
  onSubmit: () => void
}) {
  return (
    <div
      onClick={onClose}
      style={{
        position: 'fixed',
        inset: 0,
        zIndex: 60,
        background: 'rgba(15,23,42,0.35)',
        display: 'grid',
        placeItems: 'center',
        padding: 20,
      }}
    >
      <div
        className='cx-card cx-card-pad'
        style={{ width: 'min(460px, 100%)', display: 'flex', flexDirection: 'column', gap: 12 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className='cx-section-head'>
          <div className='cx-section-title'>새 프리셋</div>
          <button className='cx-btn-mini' onClick={onClose}>닫기</button>
        </div>
        <Field label='프리셋명'>
          <input
            className='cx-input'
            value={form.name}
            onChange={(e) => onChange({ ...form, name: e.target.value })}
            autoFocus
          />
        </Field>
        <Field label='설명'>
          <textarea
            className='cx-input'
            value={form.desc}
            onChange={(e) => onChange({ ...form, desc: e.target.value })}
            style={{ minHeight: 80, resize: 'vertical' }}
          />
        </Field>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className='cx-btn-soft' onClick={onClose}>취소</button>
          <button className='cx-btn-primary' onClick={onSubmit}>만들기</button>
        </div>
      </div>
    </div>
  )
}

export default PresetsCommex
