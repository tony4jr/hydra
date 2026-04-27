import { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { fetchApi } from '@/lib/api'

interface Brand {
  id: number
  name: string
}

interface Preset {
  id: number
  code: string
  name: string
}

interface CampaignCreateDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

const mentionStyles = [
  { value: 'indirect', label: '간접 언급', desc: '대화 흐름 속에서 자연스럽게' },
  { value: 'direct', label: '직접 추천', desc: '경험담 형식으로 제품명 직접 언급' },
  { value: 'minimal', label: '최소 멘션', desc: '브랜드명만 살짝 언급' },
]

export function CampaignCreateDialog({
  open,
  onOpenChange,
  onSuccess,
}: CampaignCreateDialogProps) {
  const [step, setStep] = useState(1)
  const [brands, setBrands] = useState<Brand[]>([])
  const [presets, setPresets] = useState<Preset[]>([])

  // Step 1: Brand
  const [brandId, setBrandId] = useState('')
  // Step 2: Keywords
  const [keywords, setKeywords] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState('')
  // Step 3: Preset / Style
  const [selectedPresets, setSelectedPresets] = useState<string[]>([])
  const [setsPerVideo, setSetsPerVideo] = useState(1)
  const [mentionStyle, setMentionStyle] = useState('indirect')
  // Step 4: Duration / Goal
  const [durationDays, setDurationDays] = useState(7)
  const [targetCount, setTargetCount] = useState(50)

  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      fetchApi<Brand[]>('/brands/api/list').then(setBrands).catch(() => setBrands([]))
      fetchApi<Preset[]>('/api/presets/').then(d => setPresets(Array.isArray(d) ? d : [])).catch(() => setPresets([]))
      setStep(1)
      setBrandId('')
      setKeywords([])
      setKeywordInput('')
      setSelectedPresets([])
      setSetsPerVideo(1)
      setMentionStyle('indirect')
      setDurationDays(7)
      setTargetCount(50)
    }
  }, [open])

  const addKeyword = useCallback(() => {
    const trimmed = keywordInput.trim()
    if (trimmed && !keywords.includes(trimmed)) {
      setKeywords(prev => [...prev, trimmed])
    }
    setKeywordInput('')
  }, [keywordInput, keywords])

  const togglePreset = (code: string) => {
    setSelectedPresets(prev =>
      prev.includes(code) ? prev.filter(c => c !== code) : [...prev, code]
    )
  }

  const canNext = () => {
    switch (step) {
      case 1: return !!brandId
      case 2: return keywords.length > 0
      case 3: return selectedPresets.length > 0
      case 4: return durationDays > 0 && targetCount > 0
      default: return false
    }
  }

  const handleSubmit = async () => {
    setLoading(true)
    try {
      await fetchApi('/campaigns/api/create-project', {
        method: 'POST',
        body: JSON.stringify({
          brand_id: parseInt(brandId),
          target_keywords: keywords,
          preset_codes: selectedPresets,
          sets_per_video: setsPerVideo,
          mention_style: mentionStyle,
          duration_days: durationDays,
          target_count: targetCount,
        }),
      })
      onOpenChange(false)
      onSuccess()
    } catch (e) { toast.error("오류", { description: e instanceof Error ? e.message : String(e) }) } finally {
      setLoading(false)
    }
  }

  const stepTitles = [
    '누구의 홍보인가요?',
    '어떤 영상에 작업할까요?',
    '어떻게 작업할까요?',
    '얼마나 할까요?',
  ]

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>캠페인 만들기</DialogTitle>
        </DialogHeader>

        {/* Step indicator (Toss-style with gradient bars) */}
        <div className='hydra-wizard-steps'>
          {[1, 2, 3, 4].map(s => (
            <div key={s} className='hydra-wizard-step'>
              <div
                className='hydra-wizard-step-dot'
                data-state={s === step ? 'active' : s < step ? 'done' : 'pending'}
              >
                <span className='step-num'>{s}</span>
              </div>
              {s < 4 && (
                <div
                  className='hydra-wizard-step-bar'
                  data-passed={s < step ? 'true' : 'false'}
                />
              )}
            </div>
          ))}
        </div>

        <p className='hydra-wizard-title'>{stepTitles[step - 1]}</p>

        <div className='min-h-[200px] hydra-wizard-content' key={step}>
          {/* Step 1: Brand */}
          {step === 1 && (
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>브랜드 선택</label>
              <p className='text-muted-foreground text-xs mb-2'>홍보할 브랜드를 선택하세요</p>
              <Select value={brandId} onValueChange={setBrandId}>
                <SelectTrigger>
                  <SelectValue placeholder='브랜드를 선택하세요' />
                </SelectTrigger>
                <SelectContent>
                  {brands.map(b => (
                    <SelectItem key={b.id} value={String(b.id)}>{b.name}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              {brands.length === 0 && (
                <p className='text-muted-foreground/60 text-[12px] mt-2'>
                  먼저 브랜드를 등록해주세요
                </p>
              )}
            </div>
          )}

          {/* Step 2: Keywords */}
          {step === 2 && (
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>타겟 키워드</label>
              <p className='text-muted-foreground text-xs mb-2'>이 키워드로 영상을 검색해서 작업합니다. Enter로 추가하세요.</p>
              <div className='rounded-lg border border-border bg-background p-2 min-h-[42px]'>
                <div className='flex flex-wrap gap-1.5 mb-1'>
                  {keywords.map(kw => (
                    <span key={kw} className='hydra-tag hydra-tag-primary flex items-center gap-1'>
                      {kw}
                      <button type='button' onClick={() => setKeywords(prev => prev.filter(k => k !== kw))} className='hover:text-foreground'>
                        <X className='h-3 w-3' />
                      </button>
                    </span>
                  ))}
                </div>
                <Input
                  value={keywordInput}
                  onChange={e => setKeywordInput(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) { e.preventDefault(); addKeyword() } }}
                  onBlur={addKeyword}
                  placeholder={keywords.length === 0 ? '예: 탈모, 케라틴, 모발 관리' : ''}
                  className='border-0 p-0 h-7 shadow-none focus-visible:ring-0'
                />
              </div>
            </div>
          )}

          {/* Step 3: Presets + Style */}
          {step === 3 && (
            <div className='space-y-4'>
              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>프리셋 선택</label>
                <p className='text-muted-foreground text-xs mb-2'>사용할 댓글 대화 구조를 선택하세요 (복수 선택 가능)</p>
                <div className='max-h-[140px] overflow-y-auto rounded-lg border border-border p-2 space-y-1'>
                  {presets.length === 0 ? (
                    <p className='text-muted-foreground text-[13px] py-2 text-center'>프리셋이 없습니다</p>
                  ) : presets.map(p => (
                    <label key={p.id} className='flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted'>
                      <Checkbox
                        checked={selectedPresets.includes(p.code)}
                        onCheckedChange={() => togglePreset(p.code)}
                      />
                      <span className='font-mono text-[11px] text-muted-foreground'>{p.code}</span>
                      <span className='text-[13px]'>{p.name}</span>
                    </label>
                  ))}
                </div>
              </div>

              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>한 영상에 댓글 대화를 몇 개 만들까요?</label>
                <p className='text-muted-foreground text-xs mb-2'>각 대화는 다른 프리셋, 다른 계정으로 만들어져요</p>
                <Input
                  type='number'
                  min={1}
                  max={5}
                  value={setsPerVideo}
                  onChange={e => setSetsPerVideo(parseInt(e.target.value) || 1)}
                  className='w-24'
                />
              </div>

              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>멘션 스타일</label>
                <p className='text-muted-foreground text-xs mb-2'>제품을 어떤 방식으로 언급할까요?</p>
                <Select value={mentionStyle} onValueChange={setMentionStyle}>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {mentionStyles.map(ms => (
                      <SelectItem key={ms.value} value={ms.value}>
                        {ms.label} — {ms.desc}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {/* Step 4: Duration + Goal */}
          {step === 4 && (
            <div className='space-y-4'>
              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>작업 기간</label>
                <p className='text-muted-foreground text-xs mb-2'>며칠 동안 작업할까요?</p>
                <div className='flex items-center gap-2'>
                  <Input
                    type='number'
                    min={1}
                    value={durationDays}
                    onChange={e => setDurationDays(parseInt(e.target.value) || 1)}
                    className='w-24'
                  />
                  <span className='text-muted-foreground text-[13px]'>일</span>
                </div>
              </div>

              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>목표 영상 수</label>
                <p className='text-muted-foreground text-xs mb-2'>총 몇 개 영상에 작업할까요?</p>
                <div className='flex items-center gap-2'>
                  <Input
                    type='number'
                    min={1}
                    value={targetCount}
                    onChange={e => setTargetCount(parseInt(e.target.value) || 1)}
                    className='w-24'
                  />
                  <span className='text-muted-foreground text-[13px]'>개</span>
                </div>
              </div>

              <div className='bg-muted/50 rounded-lg p-4 text-[13px]'>
                <p className='text-foreground font-medium mb-2'>캠페인 요약</p>
                <div className='space-y-1 text-muted-foreground'>
                  <p>브랜드: {brands.find(b => String(b.id) === brandId)?.name || '-'}</p>
                  <p>키워드: {keywords.join(', ')}</p>
                  <p>프리셋: {selectedPresets.join(', ')}</p>
                  <p>기간: {durationDays}일 · 목표: {targetCount}개 영상</p>
                </div>
              </div>
            </div>
          )}
        </div>

        <DialogFooter className='flex !justify-between'>
          <Button
            variant='outline'
            onClick={() => step > 1 ? setStep(step - 1) : onOpenChange(false)}
            className='hydra-btn-press'
          >
            {step > 1 ? '이전' : '취소'}
          </Button>
          {step < 4 ? (
            <Button onClick={() => setStep(step + 1)} disabled={!canNext()} className='hydra-btn-press'>
              다음
            </Button>
          ) : (
            <Button onClick={handleSubmit} disabled={loading || !canNext()} className='hydra-btn-press'>
              {loading ? '생성 중...' : '캠페인 시작'}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
