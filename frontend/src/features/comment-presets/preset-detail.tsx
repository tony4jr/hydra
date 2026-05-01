/**
 * /presets/$presetId — 댓글 트리 편집 (PR-8e + visual fix).
 *
 * spec mockup: redesign/mockups/pr-8e-slot-editor.md
 *
 * 핵심 시각:
 * - 36px 그라디언트 아바타 (A~F)
 * - 답글 들여쓰기 (depth 1/2/3 = ml-12/24/36)
 * - 분홍 좋아요 박스 (❤ + min~max + 시점)
 * - ↻ 재등장 마크 (아바타 + 메타)
 * - 화력 요약 (4 카드) + 슬롯 사용 통계
 * - 편집 ↔ 미리보기 (YouTube 댓글 영역)
 */
import { useMemo, useState, type CSSProperties } from 'react'
import { Link, useParams } from '@tanstack/react-router'
import { Heart, Plus, RotateCcw, Trash2 } from 'lucide-react'

import { useCommentPreset } from '@/hooks/use-comment-presets'
import { http } from '@/lib/api'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import type {
  CommentSlotDistribution,
  CommentSlotEmoji,
  CommentSlotLength,
  CommentTreeSlot,
} from '@/types/comment-preset'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'

// ─── 그라디언트 (mockup 일치) ────────────────────────────────────
const AVATAR_GRADIENT: Record<string, string> = {
  A: 'linear-gradient(135deg, #f59e0b, #ef4444)',
  B: 'linear-gradient(135deg, #3b82f6, #1e40af)',
  C: 'linear-gradient(135deg, #10b981, #047857)',
  D: 'linear-gradient(135deg, #8b5cf6, #6d28d9)',
  E: 'linear-gradient(135deg, #ec4899, #be185d)',
  F: 'linear-gradient(135deg, #14b8a6, #0f766e)',
}
const _DEFAULT_GRADIENT = 'linear-gradient(135deg, #71717a, #3f3f46)'
const gradientFor = (label: string) =>
  AVATAR_GRADIENT[label[0]?.toUpperCase()] ?? _DEFAULT_GRADIENT

// ─── AI 강도 라벨 ────────────────────────────────────────────────
function aiLabel(v: number): string {
  if (v <= 20) return '안전 — 양식 그대로'
  if (v <= 60) return '균형'
  if (v <= 80) return '맥락 우선'
  return '완전 자유'
}

// ─── placeholder 양식 ───────────────────────────────────────────
function placeholderFor(replyDepth: number): string {
  if (replyDepth === 0) return '저도 [고민] 때문에 고생했는데, 이 영상 보고 [공감]...'
  if (replyDepth === 1) return '오 그거 [질문]?'
  return '[답변] 입니다!'
}

// ─── 트리 구조 분석 helper ───────────────────────────────────────
function buildDepthMap(slots: CommentTreeSlot[]): Record<number, number> {
  const labelToDepth: Record<string, number> = {}
  for (const s of slots) {
    if (!s.reply_to_slot_label) labelToDepth[s.slot_label] = 0
  }
  const result: Record<number, number> = {}
  for (const s of slots) {
    if (!s.reply_to_slot_label) {
      result[s.id] = 0
    } else {
      const parentDepth = labelToDepth[s.reply_to_slot_label] ?? 0
      result[s.id] = parentDepth + 1
      if (!(s.slot_label in labelToDepth)) {
        labelToDepth[s.slot_label] = result[s.id]
      }
    }
  }
  return result
}

export default function CommentPresetDetailPage() {
  const { presetId } = useParams({ from: '/_authenticated/presets/$presetId' })
  const { detail, loading } = useCommentPreset(presetId)
  const [mode, setMode] = useState<'edit' | 'preview'>('edit')

  const slots = detail?.slots ?? []

  const labelCounts = useMemo(() => {
    const m: Record<string, number> = {}
    for (const s of slots) m[s.slot_label] = (m[s.slot_label] ?? 0) + 1
    return m
  }, [slots])

  const depthMap = useMemo(() => buildDepthMap(slots), [slots])

  const totalLikesMin = slots.reduce((sum, s) => sum + (s.like_min || 0), 0)
  const totalLikesMax = slots.reduce((sum, s) => sum + (s.like_max || 0), 0)
  const uniqueWorkers = new Set(slots.map((s) => s.slot_label)).size

  const labelSeenCounter: Record<string, number> = {}

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div>
          <Link to='/presets' className='text-muted-foreground text-[12px] hover:underline'>
            ← 프리셋 라이브러리
          </Link>
          {loading ? (
            <Skeleton className='h-8 w-72 mt-1' />
          ) : !detail ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center mt-3'>
              <p className='text-muted-foreground text-[14px]'>프리셋을 찾지 못했어요</p>
            </div>
          ) : (
            <>
              <div className='mt-1 mb-4'>
                <h1 className='hydra-page-h'>{detail.name}</h1>
                <p className='hydra-page-sub'>
                  슬롯 = 워커 1명. 같은 워커가 답답글로 재등장 가능 = 자연 토론.
                </p>
              </div>

              <div className='inline-flex items-center gap-0 bg-muted/40 p-0.5 rounded-md mb-4'>
                <button
                  onClick={() => setMode('edit')}
                  className={
                    'px-3 py-1.5 text-[12.5px] rounded font-medium transition-colors ' +
                    (mode === 'edit'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground')
                  }
                >
                  편집
                </button>
                <button
                  onClick={() => setMode('preview')}
                  className={
                    'px-3 py-1.5 text-[12.5px] rounded font-medium transition-colors ' +
                    (mode === 'preview'
                      ? 'bg-background text-foreground shadow-sm'
                      : 'text-muted-foreground')
                  }
                >
                  실제 댓글 미리보기
                </button>
              </div>

              {mode === 'edit' && (
                <>
                  <FireSummary
                    totalActions={slots.length}
                    workerCount={uniqueWorkers}
                    likeMin={totalLikesMin}
                    likeMax={totalLikesMax}
                  />
                  <SlotUsage labelCounts={labelCounts} />

                  <div className='space-y-1.5 mb-4'>
                    {slots.map((s) => {
                      labelSeenCounter[s.slot_label] =
                        (labelSeenCounter[s.slot_label] ?? 0) + 1
                      const seen = labelSeenCounter[s.slot_label]
                      const total = labelCounts[s.slot_label]
                      const depth = depthMap[s.id] ?? 0
                      return (
                        <SlotCard
                          key={s.id}
                          slot={s}
                          presetId={Number(presetId)}
                          isReentry={seen > 1}
                          seenIndex={seen}
                          totalCount={total}
                          depth={depth}
                          availableLabels={Array.from(
                            new Set(slots.map((x) => x.slot_label))
                          )}
                        />
                      )
                    })}
                  </div>

                  <AddRow
                    presetId={Number(presetId)}
                    availableLabels={Array.from(new Set(slots.map((x) => x.slot_label)))}
                  />
                </>
              )}

              {mode === 'preview' && <PreviewSection slots={slots} depthMap={depthMap} />}
            </>
          )}
        </div>
      </Main>
    </>
  )
}

function FireSummary({
  totalActions,
  workerCount,
  likeMin,
  likeMax,
}: {
  totalActions: number
  workerCount: number
  likeMin: number
  likeMax: number
}) {
  return (
    <div className='grid grid-cols-2 md:grid-cols-4 gap-2.5 mb-3.5'>
      <FireCard label='총 댓글 (액션)' value={String(totalActions)} />
      <FireCard label='슬롯 (워커 수)' value={String(workerCount)} valueColor='#a16207' />
      <FireCard label='총 좋아요' value={`${likeMin} ~ ${likeMax}`} valueColor='#dc2626' />
      <FireCard label='필요 워커' value={`${workerCount}명`} />
    </div>
  )
}

function FireCard({
  label,
  value,
  valueColor,
}: {
  label: string
  value: string
  valueColor?: string
}) {
  return (
    <div className='bg-card border border-border rounded-lg px-3 py-2.5'>
      <div className='text-[11px] text-muted-foreground mb-0.5'>{label}</div>
      <div
        className='text-[18px] font-semibold'
        style={valueColor ? { color: valueColor } : undefined}
      >
        {value}
      </div>
    </div>
  )
}

function SlotUsage({ labelCounts }: { labelCounts: Record<string, number> }) {
  const entries = Object.entries(labelCounts).sort((a, b) => a[0].localeCompare(b[0]))
  if (entries.length === 0) return null
  return (
    <div className='flex items-center gap-2 px-3 py-2.5 bg-muted/40 rounded-lg mb-4 flex-wrap text-[12px]'>
      <span className='text-muted-foreground mr-1'>슬롯 사용</span>
      {entries.map(([label, count]) => (
        <span
          key={label}
          className='inline-flex items-center gap-1.5 px-2.5 py-0.5 bg-card border border-border rounded-full text-[11.5px]'
        >
          <span
            className='inline-flex items-center justify-center w-[18px] h-[18px] rounded text-white text-[10.5px] font-semibold'
            style={{ background: gradientFor(label) }}
          >
            {label}
          </span>
          <span className='text-muted-foreground'>
            <strong className='text-foreground font-semibold'>{count}번</strong> 등장
          </span>
        </span>
      ))}
    </div>
  )
}

function SlotCard({
  slot,
  presetId,
  isReentry,
  seenIndex,
  totalCount,
  depth,
  availableLabels,
}: {
  slot: CommentTreeSlot
  presetId: number
  isReentry: boolean
  seenIndex: number
  totalCount: number
  depth: number
  availableLabels: string[]
}) {
  const [text, setText] = useState(slot.text_template ?? '')
  const [length, setLength] = useState<CommentSlotLength>(slot.length)
  const [emoji, setEmoji] = useState<CommentSlotEmoji>(slot.emoji)
  const [aiVariation, setAiVariation] = useState(slot.ai_variation)
  const [likeMin, setLikeMin] = useState(slot.like_min)
  const [likeMax, setLikeMax] = useState(slot.like_max)
  const [dist, setDist] = useState<CommentSlotDistribution>(slot.like_distribution)
  const [saving, setSaving] = useState(false)

  const indentStyle: CSSProperties =
    depth > 0
      ? {
          marginLeft: `${depth * 48}px`,
          borderLeft: '2px solid var(--border, #e4e4e7)',
          paddingLeft: '14px',
        }
      : {}

  const save = async () => {
    setSaving(true)
    try {
      await http.patch(`/api/admin/comment-presets/${presetId}/slots/${slot.id}`, {
        text_template: text,
        length,
        emoji,
        ai_variation: aiVariation,
        like_min: likeMin,
        like_max: likeMax,
        like_distribution: dist,
      })
    } finally {
      setSaving(false)
    }
  }

  const remove = async () => {
    if (!confirm(`슬롯 ${slot.slot_label} 을 삭제할까요?`)) return
    await http.delete(`/api/admin/comment-presets/${presetId}/slots/${slot.id}`)
    window.location.reload()
  }

  const replyTarget = slot.reply_to_slot_label
    ? `${slot.reply_to_slot_label} 슬롯에게`
    : '메인 댓글'

  return (
    <div
      className='flex gap-3 p-3.5 rounded-lg hover:bg-muted/30 transition-colors'
      style={indentStyle}
    >
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type='button'
            className='relative shrink-0 cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-full'
            title='클릭해서 답글 대상 변경'
          >
            <div
              className='w-9 h-9 rounded-full flex items-center justify-center text-white text-[14px] font-semibold hover:opacity-90 transition-opacity'
              style={{ background: gradientFor(slot.slot_label) }}
            >
              {slot.slot_label}
            </div>
            {isReentry && (
              <div
                className='absolute -bottom-0.5 -right-0.5 w-4 h-4 rounded-full flex items-center justify-center'
                style={{ background: '#a16207', border: '2px solid var(--background, #fafafa)' }}
                title='재등장 슬롯'
              >
                <RotateCcw className='w-2 h-2 text-white' />
              </div>
            )}
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align='start' className='w-56'>
          <DropdownMenuLabel className='text-[11px] text-muted-foreground'>
            답글 대상 슬롯
          </DropdownMenuLabel>
          <DropdownMenuItem
            onClick={async () => {
              await http.patch(
                `/api/admin/comment-presets/${presetId}/slots/${slot.id}`,
                { reply_to_slot_label: null },
              )
              window.location.reload()
            }}
            className='gap-2'
          >
            <span className='inline-flex items-center justify-center w-5 h-5 rounded bg-muted text-[10px] font-semibold'>
              ●
            </span>
            <span className='flex-1 text-[12.5px]'>메인 댓글로 (답글 X)</span>
            {!slot.reply_to_slot_label && (
              <span className='text-[10px] text-primary'>현재</span>
            )}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          {availableLabels
            .filter((l) => l !== slot.slot_label)
            .map((l) => (
              <DropdownMenuItem
                key={l}
                onClick={async () => {
                  await http.patch(
                    `/api/admin/comment-presets/${presetId}/slots/${slot.id}`,
                    { reply_to_slot_label: l },
                  )
                  window.location.reload()
                }}
                className='gap-2'
              >
                <span
                  className='inline-flex items-center justify-center w-5 h-5 rounded text-white text-[10px] font-semibold'
                  style={{ background: gradientFor(l) }}
                >
                  {l}
                </span>
                <span className='flex-1 text-[12.5px]'>{l} 에게 답글</span>
                {slot.reply_to_slot_label === l && (
                  <span className='text-[10px] text-primary'>현재</span>
                )}
              </DropdownMenuItem>
            ))}
        </DropdownMenuContent>
      </DropdownMenu>

      <div className='flex-1 min-w-0'>
        <div className='flex items-center gap-2 mb-2 flex-wrap'>
          <span
            className='inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[11.5px]'
            style={
              isReentry
                ? { background: '#fef3c7', color: '#a16207' }
                : { background: 'var(--muted, #f4f4f5)', color: 'var(--muted-foreground, #71717a)' }
            }
          >
            <span
              className='inline-flex items-center justify-center w-4 h-4 rounded text-white text-[10px] font-semibold'
              style={{ background: gradientFor(slot.slot_label) }}
            >
              {slot.slot_label}
            </span>
            {isReentry ? (
              <>
                <RotateCcw className='w-3 h-3' />
                <strong>재등장</strong>
              </>
            ) : slot.reply_to_slot_label ? (
              <strong className='text-foreground'>답글</strong>
            ) : (
              <strong className='text-foreground'>메인 댓글</strong>
            )}
            <span className='opacity-70'>
              · {seenIndex}번째 {totalCount > 1 && `/ 총 ${totalCount}회`}
            </span>
          </span>
          <span className='text-[11.5px] text-muted-foreground'>대상: {replyTarget}</span>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={2}
          placeholder={placeholderFor(depth)}
          className='w-full px-3 py-2.5 border border-border rounded-lg text-[13.5px] leading-6 bg-background outline-none focus:border-foreground/60 transition-colors resize-y'
        />

        <div className='flex items-center gap-2.5 mt-2.5 flex-wrap'>
          <div className='flex items-center gap-1.5 text-[11.5px] text-muted-foreground'>
            <span>길이</span>
            <select
              value={length}
              onChange={(e) => setLength(e.target.value as CommentSlotLength)}
              className='text-[11.5px] px-2 py-0.5 border border-border rounded bg-background'
            >
              <option value='short'>짧게</option>
              <option value='medium'>보통</option>
              <option value='long'>길게</option>
            </select>
          </div>
          <div className='flex items-center gap-1.5 text-[11.5px] text-muted-foreground'>
            <span>이모지</span>
            <select
              value={emoji}
              onChange={(e) => setEmoji(e.target.value as CommentSlotEmoji)}
              className='text-[11.5px] px-2 py-0.5 border border-border rounded bg-background'
            >
              <option value='none'>없음</option>
              <option value='sometimes'>가끔</option>
              <option value='often'>자주</option>
            </select>
          </div>
          <div className='flex items-center gap-2 text-[11.5px] px-2.5 py-1 bg-muted/40 rounded'>
            <span className='text-muted-foreground'>AI</span>
            <input
              type='range'
              min={0}
              max={100}
              step={10}
              value={aiVariation}
              onChange={(e) => setAiVariation(Number(e.target.value))}
              className='w-20 h-1 cursor-pointer'
            />
            <span className='font-semibold text-foreground'>{aiVariation}%</span>
            <span className='text-muted-foreground/80'>· {aiLabel(aiVariation)}</span>
          </div>
        </div>

        <div
          className='flex items-center gap-3 px-2.5 py-1.5 rounded mt-2 flex-wrap text-[11.5px]'
          style={{ background: '#fef2f2', border: '1px solid #fecaca' }}
        >
          <span
            className='inline-flex items-center gap-1.5 font-medium'
            style={{ color: '#dc2626' }}
          >
            <Heart className='w-3 h-3' fill='#dc2626' />
            좋아요
          </span>
          <input
            type='number'
            value={likeMin}
            min={0}
            onChange={(e) => setLikeMin(Number(e.target.value) || 0)}
            className='w-[42px] px-1.5 py-0.5 border border-border rounded bg-background text-[11.5px] text-center'
            style={{ color: '#dc2626' }}
          />
          <span style={{ color: '#dc2626' }}>~</span>
          <input
            type='number'
            value={likeMax}
            min={0}
            onChange={(e) => setLikeMax(Number(e.target.value) || 0)}
            className='w-[42px] px-1.5 py-0.5 border border-border rounded bg-background text-[11.5px] text-center'
            style={{ color: '#dc2626' }}
          />
          <span className='text-muted-foreground/70'>·</span>
          <span style={{ color: '#dc2626' }}>시점</span>
          <select
            value={dist}
            onChange={(e) => setDist(e.target.value as CommentSlotDistribution)}
            className='text-[11.5px] px-2 py-0.5 border border-border rounded bg-background'
          >
            <option value='adaptive'>적응형</option>
            <option value='burst'>한꺼번에</option>
            <option value='spread'>시간 분산</option>
            <option value='slow'>천천히</option>
          </select>
        </div>

        <div className='flex gap-1.5 mt-2.5'>
          <Button onClick={save} disabled={saving} size='sm' className='hydra-btn-press'>
            {saving ? '저장 중…' : '저장'}
          </Button>
          <Button onClick={remove} size='sm' variant='ghost'>
            <Trash2 className='w-3 h-3 mr-1' />
            삭제
          </Button>
        </div>
      </div>
    </div>
  )
}

function AddRow({
  presetId,
  availableLabels,
}: {
  presetId: number
  availableLabels: string[]
}) {
  const [replyTo, setReplyTo] = useState<string>('')
  const [reuseLabel, setReuseLabel] = useState<string>('')
  const [busy, setBusy] = useState(false)

  const add = async () => {
    setBusy(true)
    try {
      const body: Record<string, unknown> = { text_template: '' }
      if (replyTo) body.reply_to_slot_label = replyTo
      if (reuseLabel) body.slot_label = reuseLabel
      await http.post(`/api/admin/comment-presets/${presetId}/slots`, body)
      window.location.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='flex flex-wrap items-center gap-2 px-3.5 py-3 bg-muted/40 rounded-lg'>
      <span className='text-[11.5px] text-muted-foreground mr-1'>추가:</span>

      <div className='inline-flex items-center gap-1 px-2.5 py-1.5 bg-card border border-border rounded-md text-[12.5px]'>
        <span className='text-muted-foreground'>대상</span>
        <select
          value={replyTo}
          onChange={(e) => setReplyTo(e.target.value)}
          className='border-0 bg-transparent px-1 py-0 text-[12.5px] outline-none cursor-pointer'
        >
          <option value=''>메인 댓글</option>
          {availableLabels.map((l) => (
            <option key={l} value={l}>
              {l} 에 답글
            </option>
          ))}
        </select>
      </div>

      <div className='inline-flex items-center gap-1 px-2.5 py-1.5 bg-card border border-border rounded-md text-[12.5px]'>
        <span className='text-muted-foreground'>슬롯</span>
        <select
          value={reuseLabel}
          onChange={(e) => setReuseLabel(e.target.value)}
          className='border-0 bg-transparent px-1 py-0 text-[12.5px] outline-none cursor-pointer'
        >
          <option value=''>새 슬롯 (자동)</option>
          {availableLabels.map((l) => (
            <option key={l} value={l}>
              ↻ {l} 재등장
            </option>
          ))}
        </select>
      </div>

      <Button onClick={add} disabled={busy} size='sm' className='ml-auto'>
        <Plus className='w-3 h-3 mr-1' />
        추가
      </Button>
    </div>
  )
}

function PreviewSection({
  slots,
  depthMap,
}: {
  slots: CommentTreeSlot[]
  depthMap: Record<number, number>
}) {
  const labelSeenCounter: Record<string, number> = {}
  return (
    <div className='bg-card border border-border rounded-xl p-5 mt-3'>
      <div className='flex items-center gap-2 pb-3 mb-3 border-b border-border'>
        <div
          className='w-6 h-6 rounded flex items-center justify-center'
          style={{ background: '#ff0000' }}
        >
          <svg className='w-3.5 h-3.5 text-white' fill='currentColor' viewBox='0 0 24 24'>
            <path d='M23.498 6.186a3.016 3.016 0 0 0-2.122-2.136C19.505 3.545 12 3.545 12 3.545s-7.505 0-9.377.505A3.017 3.017 0 0 0 .502 6.186C0 8.07 0 12 0 12s0 3.93.502 5.814a3.016 3.016 0 0 0 2.122 2.136c1.871.505 9.376.505 9.376.505s7.505 0 9.377-.505a3.015 3.015 0 0 0 2.122-2.136C24 15.93 24 12 24 12s0-3.93-.502-5.814zM9.545 15.568V8.432L15.818 12l-6.273 3.568z' />
          </svg>
        </div>
        <div className='text-[13px] font-medium flex-1'>실제 영상 댓글 — 자연 토론</div>
        <div className='text-[11.5px] text-muted-foreground'>
          {new Set(slots.map((s) => s.slot_label)).size} 워커 · {slots.length} 액션
        </div>
      </div>

      <ul className='space-y-0'>
        {slots.map((s) => {
          labelSeenCounter[s.slot_label] = (labelSeenCounter[s.slot_label] ?? 0) + 1
          const seen = labelSeenCounter[s.slot_label]
          const isReentry = seen > 1
          const depth = depthMap[s.id] ?? 0
          const likeAvg = Math.round(((s.like_min || 0) + (s.like_max || 0)) / 2)
          const indentStyle: CSSProperties =
            depth > 0 ? { marginLeft: `${depth * 48}px` } : {}
          return (
            <li
              key={s.id}
              className='flex gap-3 py-3.5 border-t border-border first:border-t-0'
              style={indentStyle}
            >
              <div
                className='w-9 h-9 rounded-full flex items-center justify-center text-white text-[14px] font-semibold shrink-0'
                style={{ background: gradientFor(s.slot_label) }}
              >
                {s.slot_label}
              </div>
              <div className='flex-1 min-w-0'>
                <div className='flex items-center gap-2 mb-1 flex-wrap text-[12px]'>
                  <span className='font-medium text-[12.5px]'>유저{s.slot_label}</span>
                  <span className='text-muted-foreground/70'>· 1일 전</span>
                  <span
                    className='text-[10px] px-1.5 py-0.5 rounded font-semibold'
                    style={
                      isReentry
                        ? { background: '#fef3c7', color: '#a16207' }
                        : { background: '#f5f3ff', color: '#6d28d9' }
                    }
                  >
                    {s.slot_label}
                    {isReentry && ' · ↻ 재등장'} · ❤ {likeAvg}
                  </span>
                </div>
                <p className='text-[13.5px] leading-relaxed break-words'>
                  {s.text_template || (
                    <span className='text-muted-foreground/50'>(빈 양식)</span>
                  )}
                </p>
                <div className='flex items-center gap-4 mt-2 text-[11.5px] text-muted-foreground'>
                  <span
                    className='inline-flex items-center gap-1'
                    style={{ color: '#dc2626' }}
                  >
                    <Heart className='w-3 h-3' fill='#dc2626' />
                    <span className='font-semibold'>{likeAvg}</span>
                  </span>
                  <span>답글</span>
                </div>
              </div>
            </li>
          )
        })}
      </ul>

      {slots.length > 0 && (
        <div
          className='mt-4 px-3 py-2.5 rounded-lg text-[12.5px] border'
          style={{ background: '#f0fdf4', color: '#15803d', borderColor: '#15803d' }}
        >
          <strong>자연 토론</strong> · 슬롯 재등장 = 같은 워커가 답답글로 다시 등장 ·
          알고리즘이 활발한 스레드 위로 올림 (HYDRA 의 차별점)
        </div>
      )}
    </div>
  )
}
