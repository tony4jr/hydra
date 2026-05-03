/**
 * /onboarding — 신규 사용자 wizard (PR-7 + UX hot fix).
 *
 * 5 단계: Brand → Niche → Keyword → Market Definition → Done.
 * 진행 상태는 localStorage 에 저장 (DB 변경 0).
 *
 * UX hot fix:
 * - 진행한/현재 탭 클릭 시 해당 단계로 이동 (입력 데이터 보존)
 * - 키워드 탭 Enter → 키워드 등록 (이전: 다음 단계 진행)
 * - 키워드 칩 list + ✕ 삭제, 중복 무시
 * - '다음' 버튼: 키워드 1개 이상일 때만 활성
 */
import { useEffect, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'
import { X } from 'lucide-react'

import { fetchApi, http } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Button } from '@/components/ui/button'

const STORAGE_KEY = 'hydra_onboarding_state'

interface State {
  step: number
  reachedStep: number  // 진행한 최대 단계 — 탭 클릭 가능 범위
  brandId: number | null
  nicheId: number | null
  keywords: string[]
  registeredKeywordIds: number[]  // 이미 백엔드에 등록된 키워드 (중복 호출 방지)
  marketDefinition: string
  brandName: string
  category: string
  coreMessage: string
}

const DEFAULT_STATE: State = {
  step: 1,
  reachedStep: 1,
  brandId: null,
  nicheId: null,
  keywords: [],
  registeredKeywordIds: [],
  marketDefinition: '',
  brandName: '',
  category: '',
  coreMessage: '',
}

function loadState(): State {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return { ...DEFAULT_STATE }
    return { ...DEFAULT_STATE, ...JSON.parse(raw) }
  } catch {
    return { ...DEFAULT_STATE }
  }
}

function saveState(s: State) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(s))
}

const STEPS = [
  { n: 1, label: '브랜드' },
  { n: 2, label: '시장' },
  { n: 3, label: '키워드' },
  { n: 4, label: '시장 정의' },
  { n: 5, label: '완료' },
]

export default function OnboardingPage() {
  const navigate = useNavigate()
  const [state, setState] = useState<State>(loadState)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => saveState(state), [state])

  const update = (patch: Partial<State>) => setState((s) => ({ ...s, ...patch }))

  const goToStep = (n: number) => {
    if (n > state.reachedStep) return
    setError(null)
    update({ step: n })
  }

  const advance = (next: number) => {
    update({ step: next, reachedStep: Math.max(state.reachedStep, next) })
  }

  const submitBrand = async () => {
    if (!state.brandName.trim()) {
      setError('브랜드 이름을 입력해주세요')
      return
    }
    setBusy(true)
    setError(null)
    try {
      // brandId 가 이미 있으면 재생성 X (사용자가 1번 탭으로 돌아왔다 다시 누른 경우)
      if (state.brandId === null) {
        const b = await fetchApi<{ id: number; name: string }>('/brands/api/create', {
          method: 'POST',
          body: JSON.stringify({
            name: state.brandName.trim(),
            product_category: state.category || null,
            core_message: state.coreMessage || null,
          }),
          headers: { 'Content-Type': 'application/json' },
        })
        update({ brandId: b.id })
      }
      advance(2)
    } catch {
      setError('브랜드 생성에 실패했어요')
    } finally {
      setBusy(false)
    }
  }

  const submitNiche = async () => {
    if (state.brandId === null) return
    setBusy(true)
    setError(null)
    try {
      if (state.nicheId === null) {
        const n = await http.post<{ id: number }>('/api/admin/niches', {
          brand_id: state.brandId,
          name: `${state.brandName} 시장`,
          description: '온보딩에서 자동 생성됨',
        })
        update({ nicheId: n.data.id })
      }
      advance(3)
    } catch {
      setError('시장 생성에 실패했어요')
    } finally {
      setBusy(false)
    }
  }

  const addKeyword = (text: string) => {
    const t = text.trim()
    if (!t) return
    if (state.keywords.includes(t)) return
    update({ keywords: [...state.keywords, t] })
  }

  const removeKeyword = (text: string) => {
    update({ keywords: state.keywords.filter((k) => k !== text) })
  }

  const submitKeywords = async () => {
    if (state.nicheId === null) return
    if (state.keywords.length === 0) {
      setError('키워드를 1개 이상 등록하세요')
      return
    }
    setBusy(true)
    setError(null)
    try {
      // 미등록 키워드만 백엔드 호출 (재진입 시 중복 호출 방지)
      const registered = new Set(state.registeredKeywordIds)
      const newIds: number[] = [...state.registeredKeywordIds]
      const idxByText = new Map<string, number>()
      state.keywords.forEach((k, i) => idxByText.set(k, i))
      for (let i = 0; i < state.keywords.length; i++) {
        if (registered.has(i)) continue
        await http.post(`/api/admin/niches/${state.nicheId}/keywords`, {
          text: state.keywords[i],
          polling: 'daily',
        })
        newIds.push(i)
      }
      update({ registeredKeywordIds: newIds })
      advance(4)
    } catch {
      setError('키워드 등록에 실패했어요')
    } finally {
      setBusy(false)
    }
  }

  const submitMarketDef = async () => {
    if (state.nicheId === null) return
    setBusy(true)
    setError(null)
    try {
      await http.patch(`/api/admin/niches/${state.nicheId}`, {
        market_definition: state.marketDefinition || null,
      })
      advance(5)
    } catch {
      setError('저장에 실패했어요')
    } finally {
      setBusy(false)
    }
  }

  const finish = () => {
    localStorage.removeItem(STORAGE_KEY)
    if (state.brandId && state.nicheId) {
      navigate({
        to: '/brands/$brandId/niches/$nicheId',
        params: {
          brandId: String(state.brandId),
          nicheId: String(state.nicheId),
        },
      })
    } else {
      navigate({ to: '/brands' })
    }
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
        <div className='max-w-xl mx-auto'>
          <div className='mb-5'>
            <h1 className='hydra-page-h'>시작하기</h1>
            <p className='hydra-page-sub'>
              브랜드 등록부터 첫 시장까지 5단계로 안내합니다
            </p>
          </div>

          <Stepper
            current={state.step}
            reached={state.reachedStep}
            onClick={goToStep}
          />

          {error && (
            <div className='bg-rose-500/10 border border-rose-400/40 rounded-md px-3 py-2 text-rose-500 text-[13px] mt-4'>
              {error}
            </div>
          )}

          <div className='bg-card border border-border rounded-xl p-5 mt-4'>
            {state.step === 1 && (
              <Step1 state={state} update={update} onNext={submitBrand} busy={busy} />
            )}
            {state.step === 2 && <Step2 onNext={submitNiche} busy={busy} />}
            {state.step === 3 && (
              <Step3
                keywords={state.keywords}
                onAdd={addKeyword}
                onRemove={removeKeyword}
                onNext={submitKeywords}
                busy={busy}
              />
            )}
            {state.step === 4 && (
              <Step4 state={state} update={update} onNext={submitMarketDef} busy={busy} />
            )}
            {state.step === 5 && <Step5 onFinish={finish} />}
          </div>
        </div>
      </Main>
    </>
  )
}

function Stepper({
  current,
  reached,
  onClick,
}: {
  current: number
  reached: number
  onClick: (n: number) => void
}) {
  return (
    <ol className='flex items-center gap-2'>
      {STEPS.map((s) => {
        const isCurrent = s.n === current
        const isCompleted = s.n < current
        const isReachable = s.n <= reached
        const tone = isCurrent
          ? 'bg-primary text-primary-foreground'
          : isCompleted
          ? 'bg-primary/20 text-foreground hover:bg-primary/30'
          : isReachable
          ? 'bg-muted/40 text-foreground hover:bg-muted/60'
          : 'bg-muted/30 text-muted-foreground/60 cursor-not-allowed'
        const cursor = isReachable && !isCurrent ? 'cursor-pointer' : ''
        return (
          <li
            key={s.n}
            onClick={() => isReachable && onClick(s.n)}
            className={`flex-1 text-[12px] text-center py-1.5 rounded transition-colors ${tone} ${cursor}`}
          >
            {s.n}. {s.label}
          </li>
        )
      })}
    </ol>
  )
}

function Step1({
  state,
  update,
  onNext,
  busy,
}: {
  state: State
  update: (p: Partial<State>) => void
  onNext: () => void
  busy: boolean
}) {
  return (
    <div className='space-y-3'>
      <h2 className='text-foreground font-semibold text-[15px]'>브랜드 만들기</h2>
      <Input
        label='브랜드 이름'
        value={state.brandName}
        onChange={(v) => update({ brandName: v })}
        placeholder='예: 모렉신'
      />
      <Input
        label='카테고리'
        value={state.category}
        onChange={(v) => update({ category: v })}
        placeholder='예: 탈모 케어'
      />
      <Input
        label='핵심 메시지 (선택)'
        value={state.coreMessage}
        onChange={(v) => update({ coreMessage: v })}
        placeholder='예: 의학적 신뢰 + 자연 성분'
      />
      <Button
        onClick={onNext}
        disabled={busy || !state.brandName.trim()}
        className='hydra-btn-press w-full'
      >
        {busy ? '저장 중…' : '다음'}
      </Button>
    </div>
  )
}

function Step2({ onNext, busy }: { onNext: () => void; busy: boolean }) {
  return (
    <div className='space-y-3'>
      <h2 className='text-foreground font-semibold text-[15px]'>첫 시장 만들기</h2>
      <p className='text-muted-foreground text-[13px]'>
        시장은 운영의 단위입니다. 자동으로 default 시장을 생성할게요. 이름은 나중에
        바꿀 수 있어요.
      </p>
      <Button onClick={onNext} disabled={busy} className='hydra-btn-press w-full'>
        {busy ? '생성 중…' : '시장 생성'}
      </Button>
    </div>
  )
}

function Step3({
  keywords,
  onAdd,
  onRemove,
  onNext,
  busy,
}: {
  keywords: string[]
  onAdd: (v: string) => void
  onRemove: (v: string) => void
  onNext: () => void
  busy: boolean
}) {
  const [input, setInput] = useState('')

  const tryAdd = () => {
    const t = input.trim()
    if (!t) return
    onAdd(t)
    setInput('')
  }

  return (
    <div className='space-y-3'>
      <h2 className='text-foreground font-semibold text-[15px]'>키워드 추가</h2>
      <p className='text-muted-foreground text-[13px]'>
        Enter 로 키워드를 등록하세요. 1개 이상 등록해야 다음 단계로 갈 수 있어요.
      </p>
      <div className='flex gap-2'>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            // 한글 IME 조합 중이면 Enter 무시 (탈모 → 탈/모 분리 방지).
            // isComposing 은 모던 브라우저, keyCode 229 는 legacy IME 호환.
            if (e.nativeEvent.isComposing || e.keyCode === 229) return
            if (e.key === 'Enter') {
              e.preventDefault()
              tryAdd()
            }
          }}
          placeholder='예: 탈모 30대'
          className='flex-1 bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
        />
        <Button
          type='button'
          variant='outline'
          size='sm'
          onClick={tryAdd}
          disabled={!input.trim()}
        >
          추가
        </Button>
      </div>
      {keywords.length > 0 && (
        <div className='flex flex-wrap gap-1.5'>
          {keywords.map((kw) => (
            <span
              key={kw}
              className='inline-flex items-center gap-1.5 bg-secondary text-secondary-foreground rounded-md text-[13px] pl-3 pr-1 py-1'
            >
              {kw}
              <button
                type='button'
                onClick={() => onRemove(kw)}
                className='inline-flex items-center justify-center w-[18px] h-[18px] rounded bg-foreground/[0.06] hover:bg-foreground/[0.12] transition-colors'
                aria-label={`${kw} 삭제`}
              >
                <X className='w-3 h-3' />
              </button>
            </span>
          ))}
        </div>
      )}
      <Button
        onClick={onNext}
        disabled={busy || keywords.length === 0}
        className='hydra-btn-press w-full'
      >
        {busy ? '저장 중…' : `다음 (${keywords.length}개)`}
      </Button>
    </div>
  )
}

function Step4({
  state,
  update,
  onNext,
  busy,
}: {
  state: State
  update: (p: Partial<State>) => void
  onNext: () => void
  busy: boolean
}) {
  return (
    <div className='space-y-3'>
      <h2 className='text-foreground font-semibold text-[15px]'>시장 정의 작성 (선택)</h2>
      <p className='text-muted-foreground text-[13px]'>
        시장의 윤곽을 한 단락으로 적어주세요. 영상 적합도 판정에 사용됩니다.
        나중에 다듬어도 OK.
      </p>
      <textarea
        value={state.marketDefinition}
        onChange={(e) => update({ marketDefinition: e.target.value })}
        rows={4}
        placeholder='예: 30대 남성 탈모 초기 단계, 의학적 신뢰 + 자연 성분 선호, 가격 민감도 중간…'
        className='w-full bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
      />
      <Button onClick={onNext} disabled={busy} className='hydra-btn-press w-full'>
        {busy ? '저장 중…' : '저장하고 완료'}
      </Button>
    </div>
  )
}

function Step5({ onFinish }: { onFinish: () => void }) {
  return (
    <div className='space-y-4 text-center'>
      <h2 className='text-foreground font-semibold text-[18px]'>준비 완료 🎉</h2>
      <p className='text-muted-foreground text-[13px]'>
        시장 페이지에서 첫 캠페인을 만들고 운영을 시작하세요.
      </p>
      <Button onClick={onFinish} className='hydra-btn-press'>
        시장으로 이동
      </Button>
    </div>
  )
}

function Input({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string
  value: string
  onChange: (v: string) => void
  placeholder?: string
}) {
  return (
    <div>
      <label className='block text-foreground text-[13px] mb-1'>{label}</label>
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className='w-full bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
      />
    </div>
  )
}
