import { useState } from 'react'
import { Plus, Eye, Puzzle } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { GLOBAL_PRESETS, type GlobalPreset } from '../_commex-mock'

const STORAGE_KEY = 'commex-presets-v1'

type PresetForm = Pick<GlobalPreset, 'name' | 'desc'>

export function PresetsCommex() {
  const tones = ['cx-bg-purple', 'cx-bg-blue', 'cx-bg-green', 'cx-bg-orange'] as const
  const [presets, setPresets] = useState<GlobalPreset[]>(loadPresets)
  const [editing, setEditing] = useState<GlobalPreset | null>(null)
  const [preview, setPreview] = useState<GlobalPreset | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)
  const [form, setForm] = useState<PresetForm>({ name: '', desc: '' })

  const persist = (next: GlobalPreset[]) => {
    setPresets(next)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }
  const openNew = () => {
    setEditing(null)
    setForm({ name: '', desc: '' })
    setEditorOpen(true)
  }
  const openEdit = (p: GlobalPreset) => {
    setEditing(p)
    setForm({ name: p.name, desc: p.desc })
    setEditorOpen(true)
  }
  const savePreset = () => {
    const name = form.name.trim()
    const desc = form.desc.trim()
    if (!name || !desc) {
      toast.warning('프리셋 이름과 설명을 입력하세요')
      return
    }
    if (editing) {
      persist(
        presets.map((p) =>
          p.id === editing.id
            ? { ...p, name, desc, version: bumpPatchVersion(p.version) }
            : p
        )
      )
      toast.success('프리셋을 수정했습니다')
    } else {
      persist([
        {
          id: `gp-${Date.now().toString(36)}`,
          name,
          desc,
          used: 0,
          version: 'v1.0',
        },
        ...presets,
      ])
      toast.success('프리셋을 만들었습니다')
    }
    setEditing(null)
    setEditorOpen(false)
    setForm({ name: '', desc: '' })
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
              <h1 className='cx-page-h'>글로벌 프리셋</h1>
              <p className='cx-page-sub'>
                여러 브랜드/니치에서 재사용할 수 있는 기본 프리셋 라이브러리입니다.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8 }}>
              <button
                className='cx-btn-soft'
                onClick={() => setPreview(presets[0] ?? null)}
                disabled={!presets.length}
              >
                <Eye className='inline h-4 w-4 mr-1.5' />미리보기
              </button>
              <button className='cx-btn-primary' onClick={openNew}>
                <Plus className='inline h-4 w-4 mr-1' />새 프리셋
              </button>
            </div>
          </div>

          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
              gap: 14,
            }}
          >
            {presets.map((p, i) => (
              <div
                key={p.id}
                className='cx-card cx-card-pad cx-card-hover'
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 10,
                  cursor: 'pointer',
                }}
                onClick={() => openEdit(p)}
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
                <div
                  style={{
                    fontSize: 12,
                    color: 'var(--cx-primary)',
                    fontWeight: 800,
                    paddingTop: 8,
                    borderTop: '1px solid var(--cx-line-2)',
                  }}
                >
                  {p.used.toLocaleString()} 회 사용
                </div>
              </div>
            ))}
          </div>
          {editorOpen && (
            <PresetModal
              title={editing ? '프리셋 편집' : '새 프리셋'}
              form={form}
              onChange={setForm}
              onClose={() => {
                setEditing(null)
                setEditorOpen(false)
                setForm({ name: '', desc: '' })
              }}
              onSubmit={savePreset}
            />
          )}
          {preview && (
            <PreviewModal preset={preview} onClose={() => setPreview(null)} />
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
    return JSON.parse(raw) as GlobalPreset[]
  } catch {
    return GLOBAL_PRESETS
  }
}

function bumpPatchVersion(version: string): string {
  const match = version.match(/^v(\d+)\.(\d+)$/)
  if (!match) return 'v1.1'
  return `v${match[1]}.${Number(match[2]) + 1}`
}

function PresetModal({
  title,
  form,
  onChange,
  onClose,
  onSubmit,
}: {
  title: string
  form: PresetForm
  onChange: (next: PresetForm) => void
  onClose: () => void
  onSubmit: () => void
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
            style={{ minHeight: 110, resize: 'vertical' }}
          />
        </Field>
        <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
          <button className='cx-btn-soft' onClick={onClose}>
            취소
          </button>
          <button className='cx-btn-primary' onClick={onSubmit}>
            저장
          </button>
        </div>
      </div>
    </div>
  )
}

function PreviewModal({
  preset,
  onClose,
}: {
  preset: GlobalPreset
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
        style={{ width: 'min(520px, 100%)', display: 'flex', flexDirection: 'column', gap: 12 }}
        onClick={(e) => e.stopPropagation()}
      >
        <div className='cx-section-head'>
          <div className='cx-section-title'>미리보기 · {preset.name}</div>
          <button className='cx-btn-mini' onClick={onClose}>
            닫기
          </button>
        </div>
        <div
          style={{
            padding: 14,
            borderRadius: 12,
            border: '1px solid var(--cx-line)',
            background: '#fbfcff',
            lineHeight: 1.6,
            fontSize: 13,
            color: 'var(--cx-text)',
          }}
        >
          {preset.desc}
          <br />
          <b>샘플:</b> 영상 맥락에 맞춰 공감형 메인 댓글 1개와 후속 답글 2개를 생성합니다.
        </div>
      </div>
    </div>
  )
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

export default PresetsCommex
