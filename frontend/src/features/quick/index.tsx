import { useEffect, useState } from 'react'
import { Plus, Copy, Trash2, Sparkles, Send, Save, Wand2 } from 'lucide-react'
import { toast } from 'sonner'
import { useNavigate } from '@tanstack/react-router'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { useCommexStore } from '../_commex-store'

// ============================================================
// Mock Data
// ============================================================

type Niche = {
  id: string
  name: string
  desc: string
  keywords: string[]
  presetIds: string[]
}
type Brand = {
  id: string
  name: string
  summary: string
  niches: Niche[]
}
type Preset = {
  id: string
  name: string
  scope: '글로벌' | '니치 전용'
  desc: string
  used: number
  version: string
  toneAnchor: string
  slots: { account: AccountKey; target: string; content: string }[]
}

const PREVIEW_SAMPLE_METRICS = [
  [
    { likes: 86, replies: 12 },
    { likes: 73, replies: 8 },
    { likes: 65, replies: 6 },
  ],
  [
    { likes: 91, replies: 14 },
    { likes: 76, replies: 9 },
    { likes: 62, replies: 5 },
  ],
  [
    { likes: 84, replies: 11 },
    { likes: 78, replies: 10 },
    { likes: 67, replies: 7 },
  ],
] as const

const PRESETS: Preset[] = [
  {
    id: 'g1',
    name: '공감형 메인 댓글',
    scope: '글로벌',
    desc: '강한 공감과 자기 경험을 살짝 섞는 메인 댓글',
    used: 1200,
    version: 'v2.3',
    toneAnchor: 'ㅠㅠ 저도 너무 똑같아요. 이 영상 보면서 펑펑 울었어요',
    slots: [
      {
        account: 'A',
        target: '메인 댓글',
        content:
          '저도 비슷한 고민이 있어서 그런지 영상이 더 깊게 와닿네요. 말 한마디 한마디가 진짜 공감돼요.',
      },
      {
        account: 'B',
        target: 'A에게 답글',
        content:
          '저도요. 그냥 지나가려다가 끝까지 보게 됐어요. 겪어본 사람은 바로 느껴질 듯해요.',
      },
    ],
  },
  {
    id: 'g2',
    name: '질문형 진입',
    scope: '글로벌',
    desc: '질문으로 대화 흐름을 여는 타입',
    used: 987,
    version: 'v1.8',
    toneAnchor: '혹시 저처럼 이 부분에서 멈춘 분 또 계신가요?',
    slots: [
      {
        account: 'A',
        target: '메인 댓글',
        content:
          '혹시 저처럼 이 부분에서 제일 공감된 분 또 계신가요? 저는 여기서 완전 멈춰서 다시 봤어요.',
      },
      {
        account: 'B',
        target: 'A에게 답글',
        content:
          '저도 그 부분이 제일 와닿았어요. 실제로 해보신 분들 후기도 궁금하네요.',
      },
    ],
  },
  {
    id: 'g3',
    name: '정보형 메인 댓글',
    scope: '글로벌',
    desc: '정보/팁을 자연스럽게 녹이는 타입',
    used: 756,
    version: 'v3.1',
    toneAnchor: '설명해주신 내용 정리가 잘 되어있네요. 저장해두려구요',
    slots: [
      {
        account: 'A',
        target: '메인 댓글',
        content:
          '설명해주신 내용이 정리가 잘돼 있어서 좋네요. 이런 부분은 처음 보는 분들한테 특히 도움될 것 같아요.',
      },
    ],
  },
  {
    id: 'g4',
    name: '후기형 세트',
    scope: '글로벌',
    desc: '직접 경험한 변화와 후기를 강조',
    used: 654,
    version: 'v2.0',
    toneAnchor: '저도 비슷하게 해봤는데 진짜 차이 느꼈어요',
    slots: [
      {
        account: 'A',
        target: '메인 댓글',
        content:
          '저도 비슷하게 겪어봐서 그런지 훨씬 현실적으로 들려요. 꾸준히 했을 때 달라지는 부분이 진짜 공감됩니다.',
      },
    ],
  },
  {
    id: 'n1',
    name: '탈모 공감 진입',
    scope: '니치 전용',
    desc: '탈모/두피 고민 영상에 강한 감정 공감',
    used: 412,
    version: 'v1.4',
    toneAnchor: '저도 진짜 머리 빠질 때 그랬어요...',
    slots: [
      {
        account: 'A',
        target: '메인 댓글',
        content:
          '저도 머리 빠질 때 진짜 우울했어요... 영상 보면서 너무 공감돼서 댓글 남겨요.',
      },
    ],
  },
  {
    id: 'n2',
    name: '두피 케어 정보형',
    scope: '니치 전용',
    desc: '두피 케어 솔루션을 자연스럽게',
    used: 298,
    version: 'v1.1',
    toneAnchor: '저는 ~~를 써봤는데 도움 됐어요',
    slots: [
      {
        account: 'A',
        target: '메인 댓글',
        content: '두피 마사지랑 같이 케어해주니까 확실히 차이 나더라구요.',
      },
    ],
  },
]

const BRANDS: Brand[] = [
  {
    id: 'b1',
    name: '모렉신',
    summary: '탈모/두피 케어 운영',
    niches: [
      {
        id: 'n1',
        name: '탈모 고민',
        desc: '공감형 진입',
        keywords: ['탈모', '머리빠짐', '두피', '고민'],
        presetIds: ['g1', 'g2', 'n1'],
      },
      {
        id: 'n2',
        name: '두피 관리',
        desc: '정보형 솔루션',
        keywords: ['두피관리', '샴푸', '각질'],
        presetIds: ['g3', 'g4', 'n2'],
      },
    ],
  },
  {
    id: 'b2',
    name: '픽셀브루',
    summary: '직장인 루틴/생산성',
    niches: [
      {
        id: 'n3',
        name: '직장인 루틴',
        desc: '짧은 공감과 루틴 대화',
        keywords: ['출근루틴', '생산성', '아침'],
        presetIds: ['g2', 'g3'],
      },
    ],
  },
  {
    id: 'b3',
    name: '노마셀',
    summary: '뷰티/올리브영 추천',
    niches: [
      {
        id: 'n4',
        name: '신상 추천',
        desc: '경험형 후기',
        keywords: ['올리브영', '신상', '추천'],
        presetIds: ['g1', 'g4'],
      },
    ],
  },
]

type AccountKey = 'A' | 'B' | 'C' | 'D' | 'E'
const ACCOUNTS: AccountKey[] = ['A', 'B', 'C', 'D', 'E']

type Slot = {
  uid: string
  account: AccountKey
  target: string // '메인 댓글' | 'A에게 답글' | 'B에게 답글' ...
  content: string
  literal: boolean // true → 작성 그대로 게시 (AI 처리 안함)
}

const accountColor = (a: AccountKey) =>
  ({
    A: 'linear-gradient(135deg,#ffb35a,#ff8b2f)',
    B: 'linear-gradient(135deg,#5b86ff,#3568ff)',
    C: 'linear-gradient(135deg,#30ca86,#16b364)',
    D: 'linear-gradient(135deg,#aa7cff,#7e63ff)',
    E: 'linear-gradient(135deg,#ff8a9d,#ff5879)',
  })[a]

let uidCounter = 0
const newUid = () => {
  if (globalThis.crypto?.getRandomValues) {
    const values = new Uint32Array(1)
    globalThis.crypto.getRandomValues(values)
    return values[0].toString(36)
  }
  uidCounter += 1
  return `slot-${uidCounter}`
}

// ============================================================
// Component
// ============================================================

export function QuickWork() {
  const [videoUrl, setVideoUrl] = useState(
    'https://youtube.com/watch?v=demo123'
  )
  const [brandId, setBrandId] = useState<string>('b1')
  const [nicheId, setNicheId] = useState<string>('n1')
  const [presetId, setPresetId] = useState<string>('g1')
  const isManual = presetId === '__manual__'
  const [slots, setSlots] = useState<Slot[]>([
    {
      uid: 'initial-a',
      account: 'A',
      target: '메인 댓글',
      content:
        '저도 비슷한 고민이 있어서 그런지 영상이 더 깊게 와닿네요. 말 한마디가 진짜 공감돼요.',
      literal: false,
    },
    {
      uid: 'initial-b',
      account: 'B',
      target: 'A에게 답글',
      content:
        '저도요. 그냥 지나가려다가 끝까지 보게 됐어요. 겪어본 사람은 바로 느껴질 듯해요.',
      literal: false,
    },
    {
      uid: 'initial-c',
      account: 'C',
      target: '메인 댓글',
      content: '진짜 정리 너무 잘 해주셨네요. 저장해두고 다시 볼래요.',
      literal: true,
    },
  ])
  const [previewKey, setPreviewKey] = useState(0)

  const brand = BRANDS.find((b) => b.id === brandId)!
  const niches = brand.niches
  const niche = niches.find((n) => n.id === nicheId) ?? niches[0]
  const availablePresetIds = new Set([
    ...PRESETS.filter((p) => p.scope === '글로벌').map((p) => p.id),
    ...niche.presetIds,
  ])
  const availablePresets = PRESETS.filter((p) => availablePresetIds.has(p.id))
  const preset = isManual
    ? null
    : (availablePresets.find((p) => p.id === presetId) ?? availablePresets[0])

  // 브랜드 변경 → 첫 니치
  const onBrandChange = (id: string) => {
    setBrandId(id)
    const b = BRANDS.find((x) => x.id === id)!
    setNicheId(b.niches[0].id)
    setPresetId(b.niches[0].presetIds[0])
  }
  const onNicheChange = (id: string) => {
    setNicheId(id)
    const n = niches.find((x) => x.id === id)!
    setPresetId(n.presetIds[0])
  }

  const targetOptions = Array.from(
    new Set(['메인 댓글', ...slots.map((s) => `${s.account}에게 답글`)])
  )

  const addSlot = () => {
    const used = new Set(slots.map((s) => s.account))
    const next = ACCOUNTS.find((a) => !used.has(a)) ?? 'A'
    setSlots([
      ...slots,
      {
        uid: newUid(),
        account: next,
        target: '메인 댓글',
        content: '',
        literal: true,
      },
    ])
  }
  const dupSlot = (uid: string) => {
    const idx = slots.findIndex((s) => s.uid === uid)
    if (idx < 0) return
    const copy = { ...slots[idx], uid: newUid() }
    setSlots([...slots.slice(0, idx + 1), copy, ...slots.slice(idx + 1)])
  }
  const delSlot = (uid: string) => {
    if (slots.length <= 1) {
      toast.warning('최소 1개의 슬롯이 필요합니다')
      return
    }
    setSlots(slots.filter((s) => s.uid !== uid))
  }
  const updateSlot = (uid: string, patch: Partial<Slot>) => {
    setSlots(slots.map((s) => (s.uid === uid ? { ...s, ...patch } : s)))
  }

  const applyPresetToSlots = () => {
    if (!preset) return
    const next: Slot[] = preset.slots.map((s) => ({
      uid: newUid(),
      account: s.account,
      target: s.target,
      content: s.content,
      literal: false,
    }))
    setSlots(next)
    toast.success(`${preset.name} 프리셋을 슬롯에 채웠습니다`)
  }

  const navigate = useNavigate()
  const storeSave = useCommexStore((s) => s.saveDraft)
  const nicheContext = useCommexStore((s) => s.nicheContext)
  const clearCtx = useCommexStore((s) => s.clearNicheContext)

  // 브랜드/니치 페이지에서 컨텍스트 가지고 진입 시 selection 자동 세팅
  useEffect(() => {
    if (!nicheContext) return
    const b = BRANDS.find((br) => br.name === nicheContext.brandName)
    if (!b) return
    setBrandId(b.id)
    const n = b.niches.find((nn) => nn.name === nicheContext.nicheName)
    if (n) {
      setNicheId(n.id)
      setPresetId(n.presetIds[0])
    }
    clearCtx()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  const storeQueue = useCommexStore((s) => s.sendToQueue)
  const storeRun = useCommexStore((s) => s.runNow)

  const buildDraft = () => ({
    title: `${niche.name} — ${slots[0]?.content.slice(0, 28) || '댓글 작업'}${
      slots[0]?.content && slots[0].content.length > 28 ? '…' : ''
    }`,
    brand: brand.name,
    niche: niche.name,
  })

  const saveDraft = () => {
    if (!validateSlots()) return
    storeSave(buildDraft())
    toast.success('초안이 작업 큐에 저장됐어요', {
      description: '큐 페이지에서 이어서 작업할 수 있습니다',
      action: { label: '큐 보기', onClick: () => navigate({ to: '/queue' }) },
    })
  }
  const generatePreview = () => {
    setPreviewKey((k) => k + 1)
    toast.success('샘플 댓글을 다시 생성했습니다')
  }
  const sendToQueue = () => {
    if (!validateSlots()) return
    storeQueue(buildDraft())
    toast.success('작업 큐로 전송됐어요 — 승인 대기', {
      description: `${slots.length}개 슬롯 / 큐에서 승인하면 실행 예약됩니다`,
      action: { label: '큐 보기', onClick: () => navigate({ to: '/queue' }) },
    })
  }
  const runNow = () => {
    if (!validateSlots()) return
    storeRun(buildDraft())
    toast.success('즉시 실행 시작', {
      description: '워커에 할당돼 실행 중입니다',
      action: { label: '큐 보기', onClick: () => navigate({ to: '/queue' }) },
    })
  }
  const validateSlots = () => {
    if (slots.length === 0) {
      toast.warning('댓글 슬롯을 1개 이상 추가하세요')
      return false
    }
    const empty = slots.find((s) => !s.content.trim())
    if (empty) {
      toast.warning(`계정 ${empty.account} 슬롯의 내용이 비어있습니다`)
      return false
    }
    return true
  }

  // 샘플 미리보기 — preset.slots 기반으로 결정적인 지표 세트를 순환
  const previewMetrics =
    PREVIEW_SAMPLE_METRICS[previewKey % PREVIEW_SAMPLE_METRICS.length]
  const previewSamples = preset
    ? preset.slots.slice(0, 3).map((s, i) => ({
        account: s.account,
        content: s.content,
        likes: previewMetrics[i]?.likes ?? 60,
        replies: previewMetrics[i]?.replies ?? 5,
        time: `${i + 3}분 전`,
      }))
    : []

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
          {/* Header bar */}
          <div className='flex items-end justify-between flex-wrap gap-3'>
            <div>
              <h1 className='cx-page-h'>빠른 작업</h1>
              <p className='cx-page-sub'>
                영상 URL에 맞는 프리셋을 불러오거나, 그 자리에서 직접 댓글
                세트를 작성할 수 있어요.
              </p>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className='cx-btn-soft' onClick={applyPresetToSlots}>
                <Wand2 className='inline h-4 w-4 mr-1.5' />
                프리셋 불러오기
              </button>
              <button className='cx-btn-soft' onClick={saveDraft}>
                <Save className='inline h-4 w-4 mr-1.5' />
                초안 저장
              </button>
              <button className='cx-btn-primary' onClick={generatePreview}>
                <Sparkles className='inline h-4 w-4 mr-1.5' />
                댓글 샘플 생성
              </button>
            </div>
          </div>

          {/* 2-column layout */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: '1.1fr 0.9fr',
              gap: 18,
            }}
            className='cx-quick-grid'
          >
            {/* Left: 작업 설정 */}
            <div className='cx-card cx-card-pad'>
              <div className='cx-section-head'>
                <div className='cx-section-title'>작업 설정</div>
              </div>

              {/* Context card */}
              <div
                style={{
                  padding: 14,
                  borderRadius: 14,
                  background: '#f8faff',
                  border: '1px solid #dfe6ff',
                  display: 'flex',
                  alignItems: 'center',
                  gap: 12,
                }}
              >
                <div
                  style={{
                    width: 56,
                    height: 36,
                    borderRadius: 10,
                    background: 'linear-gradient(135deg,#384e70,#132135)',
                    flexShrink: 0,
                  }}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div
                    style={{
                      fontSize: 13,
                      fontWeight: 800,
                      color: 'var(--cx-text)',
                    }}
                  >
                    영상 풀에서 불러온 컨텍스트
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--cx-sub)' }}>
                    {brand.name} · {niche.name} · 관련성 92
                  </div>
                </div>
                <span
                  style={{
                    padding: '4px 10px',
                    borderRadius: 999,
                    background: '#eef4ff',
                    color: 'var(--cx-blue)',
                    fontSize: 11,
                    fontWeight: 800,
                  }}
                >
                  자동 세팅
                </span>
              </div>

              {/* Video URL */}
              <Field label='영상 URL' style={{ marginTop: 16 }}>
                <input
                  className='cx-input'
                  value={videoUrl}
                  onChange={(e) => setVideoUrl(e.target.value)}
                />
              </Field>

              {/* Brand / Niche */}
              <div
                style={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 14,
                  marginTop: 14,
                }}
              >
                <Field label='브랜드'>
                  <select
                    className='cx-input'
                    value={brandId}
                    onChange={(e) => onBrandChange(e.target.value)}
                  >
                    {BRANDS.map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                  </select>
                </Field>
                <Field label='니치'>
                  <select
                    className='cx-input'
                    value={nicheId}
                    onChange={(e) => onNicheChange(e.target.value)}
                  >
                    {niches.map((n) => (
                      <option key={n.id} value={n.id}>
                        {n.name}
                      </option>
                    ))}
                  </select>
                </Field>
              </div>

              {/* Preset */}
              <Field
                label='작성 방식'
                help={
                  isManual
                    ? '아래 댓글 슬롯에 입력한 텍스트가 그대로 게시됩니다 (AI 처리 안 함).'
                    : '프리셋을 고르면 슬롯이 자동 채워지고, AI 가 톤·길이를 보강합니다.'
                }
                style={{ marginTop: 14 }}
              >
                <select
                  className='cx-input'
                  value={presetId}
                  onChange={(e) => setPresetId(e.target.value)}
                  style={
                    isManual
                      ? {
                          borderColor: '#bff0d3',
                          background: '#f3fdf6',
                          color: '#16b364',
                          fontWeight: 800,
                        }
                      : undefined
                  }
                >
                  <option value='__manual__'>
                    ✍️ 직접 작성 — AI 처리 없이 그대로 게시
                  </option>
                  <optgroup label='글로벌 프리셋'>
                    {availablePresets
                      .filter((p) => p.scope === '글로벌')
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                  </optgroup>
                  <optgroup label={`니치 전용 — ${niche.name}`}>
                    {availablePresets
                      .filter((p) => p.scope === '니치 전용')
                      .map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                  </optgroup>
                </select>
              </Field>

              {/* Chips */}
              <div
                style={{
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: 8,
                  marginTop: 12,
                }}
              >
                <Chip>✨ 글로벌 프리셋 포함</Chip>
                <Chip>🧩 니치 전용 프리셋 포함</Chip>
                <Chip>✍️ 수기 작성 가능</Chip>
                {niche.keywords.slice(0, 3).map((k) => (
                  <Chip key={k}>#{k}</Chip>
                ))}
              </div>
            </div>

            {/* Right: 모드별 패널 */}
            <div className='cx-card cx-card-pad'>
              <div className='cx-section-head'>
                <div className='cx-section-title'>
                  {isManual ? '직접 작성 모드' : '프리셋 / 샘플 결과'}
                </div>
                {!isManual && (
                  <button className='cx-btn-mini' onClick={generatePreview}>
                    다시 생성
                  </button>
                )}
              </div>

              {isManual ? (
                /* 직접 작성 모드 안내 */
                <div
                  style={{
                    padding: 18,
                    borderRadius: 16,
                    background: 'linear-gradient(180deg,#f3fdf6,#fff)',
                    border: '1px solid #bff0d3',
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 12,
                  }}
                >
                  <div
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 10,
                    }}
                  >
                    <div
                      style={{
                        width: 36,
                        height: 36,
                        borderRadius: 12,
                        background: 'linear-gradient(135deg,#30ca86,#16b364)',
                        display: 'grid',
                        placeItems: 'center',
                        color: '#fff',
                        fontSize: 18,
                      }}
                    >
                      ✍️
                    </div>
                    <div>
                      <div
                        style={{
                          fontSize: 15,
                          fontWeight: 900,
                          color: '#0e7c4a',
                        }}
                      >
                        직접 작성한 댓글 그대로 게시
                      </div>
                      <div style={{ fontSize: 12, color: '#3a8a64', marginTop: 2 }}>
                        AI 가 단어·문장을 바꾸지 않습니다.
                      </div>
                    </div>
                  </div>

                  <div
                    style={{
                      padding: 12,
                      borderRadius: 12,
                      background: '#fff',
                      border: '1px solid #def3e3',
                      fontSize: 12,
                      color: '#3a8a64',
                      lineHeight: 1.55,
                    }}
                  >
                    <b>아래 “직접 작성 댓글 세트”</b> 에 슬롯을 추가하고 내용을
                    그대로 입력하세요. 슬롯마다 계정·대상(메인/답글)을 지정할 수
                    있어요.
                  </div>

                  <div
                    style={{
                      display: 'grid',
                      gridTemplateColumns: '1fr 1fr',
                      gap: 8,
                    }}
                  >
                    <Stat label='슬롯' value={`${slots.length}개`} />
                    <Stat
                      label='이대로 게시'
                      value={`${slots.filter((s) => s.literal).length}/${slots.length}`}
                    />
                  </div>

                  <button
                    className='cx-btn-soft'
                    style={{ width: '100%', height: 42 }}
                    onClick={() =>
                      document
                        .getElementById('cx-quick-slots')
                        ?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                    }
                  >
                    아래 슬롯 영역으로 이동 ↓
                  </button>
                </div>
              ) : (
                /* 프리셋 메타 + 샘플 미리보기 */
                <>
                  <div
                    style={{
                      padding: 14,
                      border: '1px dashed var(--cx-line)',
                      borderRadius: 14,
                      background: '#fbfcff',
                      marginBottom: 14,
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                        marginBottom: 6,
                      }}
                    >
                      <div
                        style={{
                          fontSize: 14,
                          fontWeight: 800,
                          color: 'var(--cx-text)',
                        }}
                      >
                        {preset!.name}
                      </div>
                      <span
                        style={{
                          fontSize: 11,
                          color: 'var(--cx-sub)',
                          fontWeight: 700,
                        }}
                      >
                        {preset!.scope} · {preset!.version} · {preset!.used.toLocaleString()}회 사용
                      </span>
                    </div>
                    <div
                      style={{
                        fontSize: 12,
                        color: 'var(--cx-sub)',
                        lineHeight: 1.5,
                      }}
                    >
                      {preset!.desc}
                    </div>
                    <div
                      style={{
                        marginTop: 8,
                        padding: '8px 10px',
                        borderRadius: 10,
                        background: '#f3efff',
                        fontSize: 12,
                        color: '#6758ff',
                        fontWeight: 700,
                      }}
                    >
                      톤 참고: {preset!.toneAnchor}
                    </div>
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      flexDirection: 'column',
                      gap: 10,
                    }}
                  >
                    {previewSamples.map((s, i) => (
                      <div
                        key={`${previewKey}-${i}`}
                        style={{
                          padding: 14,
                          borderRadius: 14,
                          border: '1px solid var(--cx-line-2)',
                          background: '#fff',
                          display: 'flex',
                          gap: 10,
                        }}
                      >
                        <div
                          style={{
                            width: 32,
                            height: 32,
                            borderRadius: 999,
                            background: accountColor(s.account),
                            display: 'grid',
                            placeItems: 'center',
                            color: '#fff',
                            fontWeight: 900,
                            fontSize: 13,
                            flexShrink: 0,
                          }}
                        >
                          {s.account}
                        </div>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div
                            style={{
                              fontSize: 13,
                              color: 'var(--cx-text)',
                              lineHeight: 1.55,
                            }}
                          >
                            {s.content}
                          </div>
                          <div
                            style={{
                              marginTop: 6,
                              display: 'flex',
                              gap: 12,
                              fontSize: 11,
                              color: 'var(--cx-sub)',
                            }}
                          >
                            <span>❤ {s.likes}</span>
                            <span>💬 {s.replies}</span>
                            <span>{s.time}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </>
              )}

              <div
                style={{
                  display: 'flex',
                  justifyContent: 'flex-end',
                  gap: 10,
                  marginTop: 18,
                }}
              >
                <button className='cx-btn-soft' onClick={sendToQueue}>
                  <Send className='inline h-4 w-4 mr-1.5' />큐로 보내기
                </button>
                <button className='cx-btn-primary' onClick={runNow}>
                  즉시 실행
                </button>
              </div>
            </div>
          </div>

          {/* Direct authoring slots */}
          <div
            id='cx-quick-slots'
            className='cx-card cx-card-pad'
            style={
              isManual
                ? {
                    border: '2px solid #bff0d3',
                    boxShadow: '0 12px 28px rgba(22,179,100,0.10)',
                  }
                : undefined
            }
          >
            <div className='cx-section-head'>
              <div>
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 8,
                  }}
                >
                  <div className='cx-section-title'>직접 작성 댓글 세트</div>
                  {isManual && (
                    <span
                      style={{
                        padding: '4px 10px',
                        borderRadius: 999,
                        background: 'linear-gradient(135deg,#30ca86,#16b364)',
                        color: '#fff',
                        fontSize: 11,
                        fontWeight: 900,
                      }}
                    >
                      활성 모드
                    </span>
                  )}
                </div>
                <div
                  style={{
                    fontSize: 13,
                    color: 'var(--cx-sub)',
                    marginTop: 4,
                  }}
                >
                  {isManual
                    ? '입력한 내용 그대로 게시됩니다. 슬롯마다 계정·대상을 지정하세요.'
                    : '프리셋과 별개로 직접 슬롯을 만들어 답글 흐름을 구성할 수 있어요.'}
                </div>
              </div>
              <div style={{ display: 'flex', gap: 8 }}>
                {!isManual && (
                  <button className='cx-btn-soft' onClick={applyPresetToSlots}>
                    선택 프리셋으로 채우기
                  </button>
                )}
                <button className='cx-btn-primary' onClick={addSlot}>
                  <Plus className='inline h-4 w-4 mr-1' />
                  댓글 슬롯 추가
                </button>
              </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
              {slots.map((s) => {
                const isReply = s.target !== '메인 댓글'
                return (
                  <div
                    key={s.uid}
                    style={{
                      position: 'relative',
                      paddingLeft: isReply ? 56 : 0,
                    }}
                  >
                    {isReply && (
                      <>
                        {/* L 모양 트리 커넥터 */}
                        <span
                          style={{
                            position: 'absolute',
                            left: 22,
                            top: 0,
                            bottom: 0,
                            width: 2,
                            background: '#dfe6ff',
                            borderRadius: 1,
                          }}
                        />
                        <span
                          style={{
                            position: 'absolute',
                            left: 22,
                            top: 36,
                            width: 28,
                            height: 2,
                            background: '#dfe6ff',
                            borderRadius: 1,
                          }}
                        />
                        <span
                          style={{
                            position: 'absolute',
                            left: 18,
                            top: 26,
                            fontSize: 11,
                            color: 'var(--cx-primary)',
                            fontWeight: 800,
                            background: '#fff',
                            padding: '2px 4px',
                          }}
                        >
                          ↳
                        </span>
                      </>
                    )}
                    <SlotCard
                      slot={s}
                      targetOptions={targetOptions}
                      onUpdate={(patch) => updateSlot(s.uid, patch)}
                      onDup={() => dupSlot(s.uid)}
                      onDel={() => delSlot(s.uid)}
                      isReply={isReply}
                    />
                  </div>
                )
              })}
            </div>
          </div>
        </div>
      </Main>
    </>
  )
}

// ============================================================
// Subcomponents
// ============================================================

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div
      style={{
        padding: '10px 12px',
        borderRadius: 12,
        background: '#fff',
        border: '1px solid #def3e3',
      }}
    >
      <div style={{ fontSize: 11, color: '#3a8a64', fontWeight: 800 }}>{label}</div>
      <div style={{ fontSize: 16, fontWeight: 900, color: '#0e7c4a', marginTop: 2 }}>
        {value}
      </div>
    </div>
  )
}

function Field({
  label,
  help,
  children,
  style,
}: {
  label: string
  help?: string
  children: React.ReactNode
  style?: React.CSSProperties
}) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, ...style }}>
      <label
        style={{
          fontSize: 13,
          fontWeight: 800,
          color: '#44506a',
        }}
      >
        {label}
      </label>
      {children}
      {help && (
        <span style={{ fontSize: 11, color: 'var(--cx-sub)' }}>{help}</span>
      )}
    </div>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '6px 10px',
        borderRadius: 999,
        background: '#f6f8fd',
        border: '1px solid var(--cx-line-2)',
        color: '#5f6983',
        fontSize: 12,
        fontWeight: 700,
      }}
    >
      {children}
    </span>
  )
}

function SlotCard({
  slot,
  targetOptions,
  onUpdate,
  onDup,
  onDel,
  isReply,
}: {
  slot: Slot
  targetOptions: string[]
  onUpdate: (patch: Partial<Slot>) => void
  onDup: () => void
  onDel: () => void
  isReply: boolean
}) {
  const avatarSize = isReply ? 36 : 48
  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: `${avatarSize + 12}px 1fr auto`,
        gap: 12,
        alignItems: 'flex-start',
        padding: isReply ? 14 : 16,
        border: '1px solid var(--cx-line)',
        borderRadius: 16,
        background: '#fff',
        boxShadow: 'var(--cx-shadow-soft)',
      }}
      className='cx-slot'
    >
      <div
        style={{
          width: avatarSize,
          height: avatarSize,
          borderRadius: 999,
          background: accountColor(slot.account),
          display: 'grid',
          placeItems: 'center',
          color: '#fff',
          fontWeight: 900,
          fontSize: isReply ? 14 : 18,
          boxShadow: '0 8px 16px rgba(75,99,255,0.16)',
        }}
      >
        {slot.account}
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, minWidth: 0 }}>
        {/* Header row: selects + literal toggle */}
        <div
          style={{
            display: 'flex',
            gap: 8,
            alignItems: 'center',
            flexWrap: 'wrap',
          }}
        >
          <select
            className='cx-input'
            style={{ height: 36, width: 110, padding: '6px 30px 6px 12px', fontSize: 13 }}
            value={slot.account}
            onChange={(e) =>
              onUpdate({ account: e.target.value as AccountKey })
            }
          >
            {ACCOUNTS.map((a) => (
              <option key={a} value={a}>
                계정 {a}
              </option>
            ))}
          </select>
          <select
            className='cx-input'
            style={{ height: 36, minWidth: 150, padding: '6px 30px 6px 12px', fontSize: 13 }}
            value={slot.target}
            onChange={(e) => onUpdate({ target: e.target.value })}
          >
            {targetOptions.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <span style={{ flex: 1 }} />
          <label
            style={{
              fontSize: 11,
              fontWeight: 800,
              color: slot.literal ? '#16b364' : 'var(--cx-primary)',
              display: 'inline-flex',
              alignItems: 'center',
              gap: 6,
              cursor: 'pointer',
              padding: '6px 10px',
              borderRadius: 999,
              background: slot.literal ? '#e9fbf1' : '#eef0ff',
              border: `1px solid ${slot.literal ? '#bff0d3' : '#d9dffd'}`,
              whiteSpace: 'nowrap',
              height: 30,
            }}
          >
            <input
              type='checkbox'
              checked={slot.literal}
              onChange={(e) => onUpdate({ literal: e.target.checked })}
              style={{
                width: 14,
                height: 14,
                accentColor: slot.literal ? '#16b364' : 'var(--cx-primary)',
              }}
            />
            {slot.literal ? '그대로 게시' : 'AI 보강'}
          </label>
        </div>

        <textarea
          className='cx-input'
          style={{
            minHeight: isReply ? 64 : 80,
            resize: 'vertical',
            lineHeight: 1.55,
            background: slot.literal ? '#fcfffe' : '#fff',
            borderColor: slot.literal ? '#bff0d3' : 'var(--cx-line)',
            fontSize: 13,
          }}
          value={slot.content}
          onChange={(e) => onUpdate({ content: e.target.value })}
          placeholder={
            slot.literal
              ? '이 텍스트가 그대로 댓글로 게시됩니다 (AI 재작성 없음)'
              : 'AI 가 톤·길이를 보강해 게시합니다 — 의도/방향만 적어도 OK'
          }
        />
        <div
          style={{
            fontSize: 11,
            color: 'var(--cx-sub)',
            display: 'flex',
            justifyContent: 'space-between',
          }}
        >
          <span>
            {slot.target === '메인 댓글'
              ? '독립적인 메인 댓글'
              : `${slot.target.split('에게')[0]} 슬롯에 답글`}
          </span>
          <span>{slot.content.length}자</span>
        </div>
      </div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        <button
          className='cx-icon-btn'
          onClick={onDup}
          title='슬롯 복제'
          aria-label='슬롯 복제'
        >
          <Copy className='h-4 w-4' />
        </button>
        <button
          className='cx-icon-btn'
          onClick={onDel}
          title='슬롯 삭제'
          aria-label='슬롯 삭제'
          style={{ color: 'var(--cx-red)' }}
        >
          <Trash2 className='h-4 w-4' />
        </button>
      </div>
    </div>
  )
}
