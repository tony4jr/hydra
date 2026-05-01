/**
 * /presets/$presetId — 댓글 트리 편집 (PR-8e).
 *
 * 슬롯 = 워커 1명. 자동 라벨링 (A/B/C...). 재등장 ↻ 표시.
 * 슬롯별 컨트롤: 양식 / 길이 / 이모지 / AI 변형 / 좋아요 범위 / 좋아요 시점.
 * 편집 모드 ↔ 미리보기 모드 토글.
 */
import { useMemo, useState } from 'react'
import { Link, useParams } from '@tanstack/react-router'
import { Plus, Trash2 } from 'lucide-react'

import { useCommentPreset } from '@/hooks/use-comment-presets'
import { http } from '@/lib/api'
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

export default function CommentPresetDetailPage() {
  const { presetId } = useParams({ from: '/_authenticated/presets/$presetId' })
  const { detail, loading } = useCommentPreset(presetId)
  const [mode, setMode] = useState<'edit' | 'preview'>('edit')
  const refresh = () => {
    // useCommentPreset cache 갱신 — lean: 페이지 reload
    window.location.reload()
  }

  // useCommentPreset 의 cache key 가 presetId 만이라 refresh 시 다시 fetch.
  // 단순히 detail 재 fetch — useEffect 트리거 위해 query suffix 또는 useCommentPreset 확장.
  // lean: window.location.reload() 대신 hook 강제 — useCommentPreset 가 version 모름.
  // 대신 mutating 후 fetchApi 직접 호출하여 로컬 state 업데이트.

  const slots = detail?.slots ?? []
  const labelCounts = useMemo(() => {
    const m: Record<string, number> = {}
    for (const s of slots) m[s.slot_label] = (m[s.slot_label] ?? 0) + 1
    return m
  }, [slots])
  const labelSeen: Record<string, number> = {}

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
              <div className='flex items-center justify-between mt-1 mb-5'>
                <div>
                  <h1 className='hydra-page-h'>{detail.name}</h1>
                  <p className='hydra-page-sub'>
                    슬롯 {detail.slot_count}개 · 사용 중 {detail.used_by_niches} 타겟
                    {detail.is_default && <> · 기본</>}
                  </p>
                </div>
                <div className='flex items-center gap-1.5'>
                  <Button
                    variant={mode === 'edit' ? 'default' : 'outline'}
                    size='sm'
                    onClick={() => setMode('edit')}
                  >
                    편집
                  </Button>
                  <Button
                    variant={mode === 'preview' ? 'default' : 'outline'}
                    size='sm'
                    onClick={() => setMode('preview')}
                  >
                    미리보기
                  </Button>
                </div>
              </div>

              {mode === 'edit' && (
                <div className='space-y-3'>
                  {slots.map((s) => {
                    labelSeen[s.slot_label] = (labelSeen[s.slot_label] ?? 0) + 1
                    const isReentry = labelSeen[s.slot_label] > 1
                    const totalCount = labelCounts[s.slot_label]
                    return (
                      <SlotCard
                        key={s.id}
                        slot={s}
                        presetId={Number(presetId)}
                        isReentry={isReentry}
                        labelSeen={labelSeen[s.slot_label]}
                        totalCount={totalCount}
                        refresh={refresh}
                      />
                    )
                  })}
                  <SlotAddRow
                    presetId={Number(presetId)}
                    availableLabels={Array.from(new Set(slots.map((x) => x.slot_label)))}
                    refresh={refresh}
                  />
                </div>
              )}

              {mode === 'preview' && <PreviewSection slots={slots} />}
            </>
          )}
        </div>
      </Main>
    </>
  )
}

function SlotCard({
  slot,
  presetId,
  isReentry,
  labelSeen,
  totalCount,
  refresh,
}: {
  slot: CommentTreeSlot
  presetId: number
  isReentry: boolean
  labelSeen: number
  totalCount: number
  refresh: () => void
}) {
  const [text, setText] = useState(slot.text_template ?? '')
  const [length, setLength] = useState<CommentSlotLength>(slot.length)
  const [emoji, setEmoji] = useState<CommentSlotEmoji>(slot.emoji)
  const [aiVariation, setAiVariation] = useState(slot.ai_variation)
  const [likeMin, setLikeMin] = useState(slot.like_min)
  const [likeMax, setLikeMax] = useState(slot.like_max)
  const [dist, setDist] = useState<CommentSlotDistribution>(slot.like_distribution)
  const [saving, setSaving] = useState(false)

  const reentryMark = isReentry ? '↻'.repeat(labelSeen - 1) : ''
  const replyTo = slot.reply_to_slot_label
    ? `${slot.reply_to_slot_label} 에 답글`
    : '메인 댓글'

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
    if (!confirm(`슬롯 ${slot.slot_label}${reentryMark} 을 삭제할까요?`)) return
    await http.delete(`/api/admin/comment-presets/${presetId}/slots/${slot.id}`)
    refresh()
    // 페이지 reload 가 필요한 case — useCommentPreset 의 cache 갱신 위해
    window.location.reload()
  }

  return (
    <div className='bg-card border border-border rounded-xl p-5'>
      <div className='flex items-center justify-between mb-3'>
        <div className='flex items-center gap-2'>
          <span className='hydra-tag hydra-tag-primary text-[14px] font-semibold'>
            {slot.slot_label}
            {reentryMark}
          </span>
          <span className='text-muted-foreground text-[12px]'>{replyTo}</span>
          {totalCount > 1 && (
            <span className='text-muted-foreground/60 text-[11px]'>
              · 같은 워커 {totalCount}회 등장
            </span>
          )}
        </div>
        <Button variant='ghost' size='sm' onClick={remove}>
          <Trash2 className='h-3.5 w-3.5' />
        </Button>
      </div>

      <div className='space-y-3'>
        <div>
          <label className='block text-foreground text-[13px] mb-1'>양식</label>
          <textarea
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={2}
            className='w-full bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
          />
        </div>

        <div className='grid grid-cols-2 gap-3'>
          <div>
            <label className='block text-foreground text-[12px] mb-1'>길이</label>
            <select
              value={length}
              onChange={(e) => setLength(e.target.value as CommentSlotLength)}
              className='w-full bg-background border border-border rounded-md text-[12px] px-2 py-1'
            >
              <option value='short'>짧게</option>
              <option value='medium'>보통</option>
              <option value='long'>길게</option>
            </select>
          </div>
          <div>
            <label className='block text-foreground text-[12px] mb-1'>이모지</label>
            <select
              value={emoji}
              onChange={(e) => setEmoji(e.target.value as CommentSlotEmoji)}
              className='w-full bg-background border border-border rounded-md text-[12px] px-2 py-1'
            >
              <option value='none'>없음</option>
              <option value='sometimes'>가끔</option>
              <option value='often'>자주</option>
            </select>
          </div>
        </div>

        <div>
          <label className='block text-foreground text-[12px] mb-1'>
            AI 변형 강도 {aiVariation}%
          </label>
          <input
            type='range'
            min={0}
            max={100}
            value={aiVariation}
            onChange={(e) => setAiVariation(Number(e.target.value))}
            className='w-full'
          />
        </div>

        <div className='grid grid-cols-3 gap-3 items-end'>
          <div>
            <label className='block text-foreground text-[12px] mb-1'>좋아요 최소</label>
            <input
              type='number'
              value={likeMin}
              min={0}
              onChange={(e) => setLikeMin(Number(e.target.value))}
              className='w-full bg-background border border-border rounded-md text-[12px] px-2 py-1'
            />
          </div>
          <div>
            <label className='block text-foreground text-[12px] mb-1'>좋아요 최대</label>
            <input
              type='number'
              value={likeMax}
              min={0}
              onChange={(e) => setLikeMax(Number(e.target.value))}
              className='w-full bg-background border border-border rounded-md text-[12px] px-2 py-1'
            />
          </div>
          <div>
            <label className='block text-foreground text-[12px] mb-1'>분산</label>
            <select
              value={dist}
              onChange={(e) => setDist(e.target.value as CommentSlotDistribution)}
              className='w-full bg-background border border-border rounded-md text-[12px] px-2 py-1'
            >
              <option value='adaptive'>적응형</option>
              <option value='burst'>한꺼번에</option>
              <option value='spread'>시간 분산</option>
              <option value='slow'>천천히</option>
            </select>
          </div>
        </div>

        <Button onClick={save} disabled={saving} size='sm' className='hydra-btn-press'>
          {saving ? '저장 중…' : '저장'}
        </Button>
      </div>
    </div>
  )
}

function SlotAddRow({
  presetId,
  availableLabels,
  refresh,
}: {
  presetId: number
  availableLabels: string[]
  refresh: () => void
}) {
  const [replyTo, setReplyTo] = useState<string>('')
  const [busy, setBusy] = useState(false)

  const add = async () => {
    setBusy(true)
    try {
      await http.post(`/api/admin/comment-presets/${presetId}/slots`, {
        reply_to_slot_label: replyTo || null,
        text_template: '',
      })
      refresh()
      window.location.reload()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className='bg-card border border-dashed border-border rounded-xl p-4 flex items-center gap-2'>
      <span className='text-muted-foreground text-[12px]'>새 슬롯</span>
      <select
        value={replyTo}
        onChange={(e) => setReplyTo(e.target.value)}
        className='bg-background border border-border rounded-md text-[12px] px-2 py-1'
      >
        <option value=''>메인 댓글</option>
        {availableLabels.map((l) => (
          <option key={l} value={l}>
            {l} 에 답글
          </option>
        ))}
      </select>
      <Button onClick={add} disabled={busy} size='sm' className='ml-auto'>
        <Plus className='h-3.5 w-3.5 mr-1' /> 추가
      </Button>
    </div>
  )
}

function PreviewSection({ slots }: { slots: CommentTreeSlot[] }) {
  // 트리 구조로 정렬: NULL parent → A → A 의 자식 → ...
  // 단순: position 순서대로 indented 표시 (계층 indent = depth)
  const labelToDepth: Record<string, number> = {}
  for (const s of slots) {
    if (!s.reply_to_slot_label) {
      labelToDepth[s.slot_label] = 0
    } else {
      labelToDepth[s.slot_label] = (labelToDepth[s.reply_to_slot_label] ?? 0) + 1
    }
  }

  return (
    <div className='bg-card border border-border rounded-xl p-5'>
      <p className='text-muted-foreground text-[12px] mb-3'>
        미리보기 — 실제 유튜브 댓글 영역처럼 (워커 자동 배정, mock)
      </p>
      <ul className='space-y-3'>
        {slots.map((s) => {
          const depth = labelToDepth[s.slot_label] ?? 0
          const likeAvg = Math.round(((s.like_min || 0) + (s.like_max || 0)) / 2)
          return (
            <li key={s.id} style={{ marginLeft: `${depth * 24}px` }}>
              <div className='flex items-baseline gap-2'>
                <span className='font-medium text-foreground text-[13px]'>
                  유저{s.slot_label}
                </span>
                <span className='text-muted-foreground/70 text-[11px]'>
                  · 워커 {s.slot_label}
                </span>
              </div>
              <p className='text-foreground text-[14px] mt-1'>
                {s.text_template || <span className='text-muted-foreground/50'>(빈 양식)</span>}
              </p>
              <p className='text-muted-foreground/70 text-[11px] mt-1'>
                ❤ {likeAvg} · {s.length} · {s.emoji} · AI {s.ai_variation}%
              </p>
            </li>
          )
        })}
      </ul>
    </div>
  )
}
