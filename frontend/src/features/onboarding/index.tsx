/**
 * /onboarding — 신규 사용자 wizard (PR-7).
 *
 * 5 단계: Brand → Niche → Keyword → Market Definition → Done.
 * 진행 상태는 localStorage 에 저장 (DB 변경 0). AI helper 는 followup.
 */
import { useEffect, useState } from 'react'
import { useNavigate } from '@tanstack/react-router'

import { fetchApi, http } from '@/lib/api'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Button } from '@/components/ui/button'

const STORAGE_KEY = 'hydra_onboarding_state'

interface State {
  step: number
  brandId: number | null
  nicheId: number | null
  keyword: string
  marketDefinition: string
  brandName: string
  category: string
  coreMessage: string
}

const DEFAULT_STATE: State = {
  step: 1,
  brandId: null,
  nicheId: null,
  keyword: '',
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

  const submitBrand = async () => {
    if (!state.brandName.trim()) {
      setError('브랜드 이름을 입력해주세요')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const b = await fetchApi<{ id: number; name: string }>('/brands/api/create', {
        method: 'POST',
        body: JSON.stringify({
          name: state.brandName.trim(),
          product_category: state.category || null,
          core_message: state.coreMessage || null,
        }),
        headers: { 'Content-Type': 'application/json' },
      })
      update({ brandId: b.id, step: 2 })
    } catch (e) {
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
      const n = await http.post<{ id: number }>('/api/admin/niches', {
        brand_id: state.brandId,
        name: `${state.brandName} 시장`,
        description: '온보딩에서 자동 생성됨',
      })
      update({ nicheId: n.data.id, step: 3 })
    } catch {
      setError('시장 생성에 실패했어요')
    } finally {
      setBusy(false)
    }
  }

  const submitKeyword = async () => {
    if (state.nicheId === null) return
    if (!state.keyword.trim()) {
      setError('키워드를 입력해주세요')
      return
    }
    setBusy(true)
    setError(null)
    try {
      await http.post(`/api/admin/niches/${state.nicheId}/keywords`, {
        text: state.keyword.trim(),
        polling: 'daily',
      })
      update({ step: 4 })
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
      update({ step: 5 })
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
        to: '/products/$brandId/niches/$nicheId',
        params: {
          brandId: String(state.brandId),
          nicheId: String(state.nicheId),
        },
      })
    } else {
      navigate({ to: '/products' })
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

          <Stepper current={state.step} />

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
              <Step3 state={state} update={update} onNext={submitKeyword} busy={busy} />
            )}
            {state.step === 4 && (
              <Step4 state={state} update={update} onNext={submitMarketDef} busy={busy} />
            )}
            {state.step === 5 && <Step5 onFinish={finish} />}
          </div>

          {state.step > 1 && state.step < 5 && (
            <div className='mt-3 text-right'>
              <button
                onClick={() => update({ step: state.step - 1 })}
                className='text-muted-foreground text-[12px] hover:underline'
                disabled={busy}
              >
                ← 이전 단계
              </button>
            </div>
          )}
        </div>
      </Main>
    </>
  )
}

function Stepper({ current }: { current: number }) {
  return (
    <ol className='flex items-center gap-2'>
      {STEPS.map((s) => (
        <li
          key={s.n}
          className={
            'flex-1 text-[12px] text-center py-1.5 rounded ' +
            (s.n < current
              ? 'bg-primary/20 text-foreground'
              : s.n === current
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted/30 text-muted-foreground')
          }
        >
          {s.n}. {s.label}
        </li>
      ))}
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
      <Button onClick={onNext} disabled={busy} className='hydra-btn-press w-full'>
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
      <h2 className='text-foreground font-semibold text-[15px]'>첫 키워드 추가</h2>
      <p className='text-muted-foreground text-[13px]'>
        시장이 영상을 발견하기 위한 키워드를 한 개 이상 등록하세요.
      </p>
      <Input
        label='키워드'
        value={state.keyword}
        onChange={(v) => update({ keyword: v })}
        placeholder='예: 탈모 30대'
      />
      <Button onClick={onNext} disabled={busy} className='hydra-btn-press w-full'>
        {busy ? '저장 중…' : '다음'}
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
