import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Plus, X } from 'lucide-react'
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
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Textarea } from '@/components/ui/textarea'
import { fetchApi } from '@/lib/api'

interface Preset {
  id: number
  code: string
  name: string
}

interface Brand {
  id: number
  name: string
}

interface ManualStep {
  role: string
  type: 'comment' | 'reply'
  target: string
  text: string
}

const ROLES = [
  { value: 'seed', label: '시드 (메인 작성자)' },
  { value: 'asker', label: '질문자' },
  { value: 'agree', label: '동조' },
  { value: 'witness', label: '경험자' },
  { value: 'curious', label: '궁금이' },
]

interface DirectCampaignDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onSuccess: () => void
}

export function DirectCampaignDialog({
  open,
  onOpenChange,
  onSuccess,
}: DirectCampaignDialogProps) {
  const [workMode, setWorkMode] = useState<'preset' | 'manual'>('preset')
  const [urls, setUrls] = useState('')

  // Preset mode
  const [presets, setPresets] = useState<Preset[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  const [selectedPreset, setSelectedPreset] = useState('')
  const [selectedBrand, setSelectedBrand] = useState('')

  // Common
  const [likeEnabled, setLikeEnabled] = useState(false)
  const [likeCount, setLikeCount] = useState(30)
  const [subscribeEnabled, setSubscribeEnabled] = useState(false)

  // Manual mode — 대화 흐름
  const [steps, setSteps] = useState<ManualStep[]>([
    { role: 'seed', type: 'comment', target: 'main', text: '' },
  ])

  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      fetchApi<Preset[]>('/api/presets/').then(setPresets).catch(() => setPresets([]))
      fetchApi<Brand[]>('/brands/api/list').then(setBrands).catch(() => setBrands([]))
    }
  }, [open])

  const urlCount = urls.split('\n').map(u => u.trim()).filter(Boolean).length

  const addStep = () => {
    setSteps([...steps, {
      role: 'asker',
      type: 'reply',
      target: `step_${steps.length}`,
      text: '',
    }])
  }

  const removeStep = (idx: number) => {
    if (steps.length <= 1) return
    setSteps(steps.filter((_, i) => i !== idx))
  }

  const updateStep = (idx: number, field: keyof ManualStep, value: string) => {
    setSteps(steps.map((s, i) => i === idx ? { ...s, [field]: value } : s))
  }

  const handleSubmit = async () => {
    const urlList = urls.split('\n').map(u => u.trim()).filter(Boolean)
    if (urlList.length === 0) return

    setLoading(true)
    try {
      await fetchApi('/campaigns/api/direct/create', {
        method: 'POST',
        body: JSON.stringify({
          video_urls: urlList,
          work_mode: workMode,
          preset_code: workMode === 'preset' ? selectedPreset : null,
          brand_id: selectedBrand ? parseInt(selectedBrand) : null,
          like_count: likeEnabled ? likeCount : 0,
          subscribe: subscribeEnabled,
          manual_steps: workMode === 'manual' ? steps : null,
        }),
      })
      onOpenChange(false)
      onSuccess()
    } catch (e) { toast.error("오류", { description: e instanceof Error ? e.message : String(e) }) } finally {
      setLoading(false)
    }
  }

  const hasAction = workMode === 'preset'
    ? !!selectedPreset
    : steps.some(s => s.text.trim()) || likeEnabled || subscribeEnabled

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-lg max-h-[85vh] overflow-y-auto'>
        <DialogHeader>
          <DialogTitle>다이렉트 캠페인</DialogTitle>
          <p className='text-muted-foreground text-xs'>특정 영상에 바로 작업을 실행해요</p>
        </DialogHeader>
        <div className='space-y-4 py-2'>

          {/* URLs */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium block mb-1.5'>영상 URL</label>
            <p className='text-muted-foreground text-xs mb-2'>작업할 영상 URL을 한 줄에 하나씩 입력하세요</p>
            <Textarea
              value={urls}
              onChange={e => setUrls(e.target.value)}
              placeholder={'https://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...'}
              rows={3}
            />
            {urlCount > 0 && (
              <p className='text-muted-foreground text-[11px] mt-1'>{urlCount}개 영상에 동일한 작업을 실행해요</p>
            )}
          </div>

          {/* Mode Toggle */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium block mb-1.5'>댓글 작업 방식</label>
            <RadioGroup value={workMode} onValueChange={v => setWorkMode(v as 'preset' | 'manual')} className='flex gap-4'>
              <div className='flex items-center gap-2'>
                <RadioGroupItem value='preset' id='dm-preset' />
                <label htmlFor='dm-preset' className='text-[13px] cursor-pointer'>프리셋 (AI 대화 자동)</label>
              </div>
              <div className='flex items-center gap-2'>
                <RadioGroupItem value='manual' id='dm-manual' />
                <label htmlFor='dm-manual' className='text-[13px] cursor-pointer'>직접 작성 (대화 흐름)</label>
              </div>
            </RadioGroup>
          </div>

          {workMode === 'preset' ? (
            <div className='space-y-3'>
              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium block mb-1.5'>프리셋</label>
                <p className='text-muted-foreground text-xs mb-2'>선택한 프리셋 구조로 AI가 댓글을 자동 생성해요</p>
                <Select value={selectedPreset} onValueChange={setSelectedPreset}>
                  <SelectTrigger><SelectValue placeholder='프리셋을 선택하세요' /></SelectTrigger>
                  <SelectContent>
                    {presets.map(p => (
                      <SelectItem key={p.id} value={p.code}>
                        <span className='font-mono text-[11px] text-muted-foreground mr-1'>{p.code}</span> {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium block mb-1.5'>브랜드</label>
                <p className='text-muted-foreground text-xs mb-2'>어떤 브랜드를 홍보할까요?</p>
                <Select value={selectedBrand} onValueChange={setSelectedBrand}>
                  <SelectTrigger><SelectValue placeholder='브랜드를 선택하세요' /></SelectTrigger>
                  <SelectContent>
                    {brands.map(b => (
                      <SelectItem key={b.id} value={String(b.id)}>{b.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          ) : (
            /* 수동 모드 — 대화 흐름 구조 */
            <div className='space-y-3'>
              <label className='text-foreground text-sm font-medium block mb-1.5'>대화 흐름</label>
              <p className='text-muted-foreground text-xs mb-2'>
                같은 역할은 같은 계정이 담당해요. 시스템이 자동으로 계정을 배정합니다.
              </p>

              <div className='space-y-2'>
                {steps.map((step, idx) => (
                  <div key={idx}
                       className='rounded-lg border border-white/10 p-3'
                       style={{ marginLeft: step.type === 'reply' ? 20 : 0 }}>

                    <div className='flex items-center gap-2 mb-2'>
                      <span className='flex items-center justify-center w-5 h-5 rounded-full text-[10px] font-bold text-white'
                            style={{ background: step.role === 'seed' ? '#6c5ce7' : step.role === 'asker' ? '#eab308' : '#22c55e' }}>
                        {idx + 1}
                      </span>

                      <Select value={step.role} onValueChange={v => updateStep(idx, 'role', v)}>
                        <SelectTrigger className='h-7 w-[150px] text-xs'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ROLES.map(r => (
                            <SelectItem key={r.value} value={r.value}>{r.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>

                      <Select value={step.type} onValueChange={v => {
                        updateStep(idx, 'type', v)
                        if (v === 'comment') updateStep(idx, 'target', 'main')
                        if (v === 'reply') updateStep(idx, 'target', `step_${idx}`)
                      }}>
                        <SelectTrigger className='h-7 w-[100px] text-xs'>
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          <SelectItem value='comment'>메인 댓글</SelectItem>
                          <SelectItem value='reply'>대댓글</SelectItem>
                        </SelectContent>
                      </Select>

                      {step.type === 'reply' && (
                        <Select value={step.target} onValueChange={v => updateStep(idx, 'target', v)}>
                          <SelectTrigger className='h-7 w-[120px] text-xs'>
                            <SelectValue />
                          </SelectTrigger>
                          <SelectContent>
                            {steps.slice(0, idx).map((_, i) => (
                              <SelectItem key={i} value={`step_${i + 1}`}>Step {i + 1}에</SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                      )}

                      {steps.length > 1 && (
                        <Button variant='ghost' size='icon' className='h-6 w-6 ml-auto text-muted-foreground hover:text-destructive'
                                onClick={() => removeStep(idx)}>
                          <X className='h-3 w-3' />
                        </Button>
                      )}
                    </div>

                    <Textarea
                      value={step.text}
                      onChange={e => updateStep(idx, 'text', e.target.value)}
                      placeholder={step.type === 'comment' ? '메인 댓글 내용을 입력하세요' : '대댓글 내용을 입력하세요'}
                      rows={2}
                      className='text-sm'
                    />
                  </div>
                ))}
              </div>

              <Button variant='outline' size='sm' onClick={addStep} className='w-full'>
                <Plus className='h-3 w-3 mr-1' /> 스텝 추가
              </Button>

              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium block mb-1.5'>브랜드 (선택)</label>
                <Select value={selectedBrand} onValueChange={setSelectedBrand}>
                  <SelectTrigger><SelectValue placeholder='브랜드 없이도 가능' /></SelectTrigger>
                  <SelectContent>
                    <SelectItem value='none'>없음</SelectItem>
                    {brands.map(b => (
                      <SelectItem key={b.id} value={String(b.id)}>{b.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>
          )}

          {/* 공통: 좋아요 + 구독 */}
          <div className='border-t border-border pt-3 space-y-3'>
            <p className='text-foreground text-sm font-medium'>추가 작업</p>

            <div className='flex items-center gap-3'>
              <Checkbox id='d-like' checked={likeEnabled} onCheckedChange={v => setLikeEnabled(v === true)} />
              <label htmlFor='d-like' className='text-[13px] cursor-pointer flex-1'>좋아요</label>
              {likeEnabled && (
                <div className='flex items-center gap-1'>
                  <Input type='number' min={1} value={likeCount} onChange={e => setLikeCount(parseInt(e.target.value) || 1)} className='w-20 h-8 text-center' />
                  <span className='text-muted-foreground text-xs'>개</span>
                </div>
              )}
            </div>

            <div className='flex items-center gap-3'>
              <Checkbox id='d-sub' checked={subscribeEnabled} onCheckedChange={v => setSubscribeEnabled(v === true)} />
              <label htmlFor='d-sub' className='text-[13px] cursor-pointer'>구독</label>
            </div>
          </div>

        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>취소</Button>
          <Button onClick={handleSubmit} disabled={loading || urlCount === 0 || !hasAction}>
            {loading ? '실행 중...' : `${urlCount}개 영상에 실행`}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
