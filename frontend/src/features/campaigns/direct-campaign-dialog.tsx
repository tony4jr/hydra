import { useEffect, useState } from 'react'
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

  // Manual mode
  const [likeEnabled, setLikeEnabled] = useState(false)
  const [likeCount, setLikeCount] = useState(1)
  const [commentEnabled, setCommentEnabled] = useState(false)
  const [commentMode, setCommentMode] = useState<'manual' | 'ai'>('ai')
  const [commentText, setCommentText] = useState('')
  const [replyEnabled, setReplyEnabled] = useState(false)
  const [replyTarget, setReplyTarget] = useState('')
  const [replyMode, setReplyMode] = useState<'manual' | 'ai'>('ai')
  const [replyText, setReplyText] = useState('')
  const [subscribeEnabled, setSubscribeEnabled] = useState(false)

  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      fetchApi<Preset[]>('/api/presets/').then(setPresets).catch(() => setPresets([]))
      fetchApi<Brand[]>('/brands/api/list').then(setBrands).catch(() => setBrands([]))
    }
  }, [open])

  const urlCount = urls.split('\n').map(u => u.trim()).filter(Boolean).length

  const handleSubmit = async () => {
    const urlList = urls.split('\n').map(u => u.trim()).filter(Boolean)
    if (urlList.length === 0) return

    setLoading(true)
    try {
      if (workMode === 'preset') {
        await fetchApi('/campaigns/api/create', {
          method: 'POST',
          body: JSON.stringify({
            video_urls: urlList,
            preset_code: selectedPreset,
            brand_id: selectedBrand ? parseInt(selectedBrand) : null,
            campaign_type: 'direct',
          }),
        })
      } else {
        await fetchApi('/campaigns/api/create', {
          method: 'POST',
          body: JSON.stringify({
            video_urls: urlList,
            campaign_type: 'direct',
            actions: {
              like: likeEnabled ? { count: likeCount } : null,
              comment: commentEnabled ? { mode: commentMode, text: commentMode === 'manual' ? commentText : null } : null,
              reply: replyEnabled ? { target: replyTarget, mode: replyMode, text: replyMode === 'manual' ? replyText : null } : null,
              subscribe: subscribeEnabled,
            },
          }),
        })
      }
      onOpenChange(false)
      onSuccess()
    } catch {
      // error
    } finally {
      setLoading(false)
    }
  }

  const hasAction = workMode === 'preset'
    ? !!selectedPreset
    : likeEnabled || commentEnabled || replyEnabled || subscribeEnabled

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>다이렉트 캠페인</DialogTitle>
        </DialogHeader>
        <div className='space-y-4 py-2'>
          {/* URLs */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>영상 URL</label>
            <p className='text-muted-foreground text-xs mb-2'>작업할 영상 URL을 한 줄에 하나씩 입력하세요</p>
            <Textarea
              value={urls}
              onChange={e => setUrls(e.target.value)}
              placeholder={'https://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...'}
              rows={4}
            />
            {urlCount > 0 && (
              <p className='text-muted-foreground text-[11px] mt-1'>{urlCount}개 URL 입력됨</p>
            )}
          </div>

          {/* Mode Toggle */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>작업 방식</label>
            <RadioGroup value={workMode} onValueChange={v => setWorkMode(v as 'preset' | 'manual')} className='flex gap-4'>
              <div className='flex items-center gap-2'>
                <RadioGroupItem value='preset' id='dm-preset' />
                <label htmlFor='dm-preset' className='text-[13px] cursor-pointer'>프리셋 (AI 대화 자동)</label>
              </div>
              <div className='flex items-center gap-2'>
                <RadioGroupItem value='manual' id='dm-manual' />
                <label htmlFor='dm-manual' className='text-[13px] cursor-pointer'>수동 입력 (개별 작업)</label>
              </div>
            </RadioGroup>
          </div>

          {workMode === 'preset' ? (
            <div className='space-y-3'>
              <div className='mb-5'>
                <label className='text-foreground text-sm font-medium mb-1.5'>프리셋</label>
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
                <label className='text-foreground text-sm font-medium mb-1.5'>브랜드</label>
                <Select value={selectedBrand} onValueChange={setSelectedBrand}>
                  <SelectTrigger><SelectValue placeholder='브랜드를 선택하세요' /></SelectTrigger>
                  <SelectContent>
                    {brands.map(b => (
                      <SelectItem key={b.id} value={String(b.id)}>{b.name}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <p className='text-muted-foreground/60 text-[12px]'>AI가 영상 내용에 맞춰 대화를 자동 생성합니다</p>
            </div>
          ) : (
            <div className='space-y-3'>
              <p className='text-foreground text-sm font-medium mb-1.5'>작업 선택</p>

              {/* Like */}
              <div className='flex items-center gap-3'>
                <Checkbox id='d-like' checked={likeEnabled} onCheckedChange={v => setLikeEnabled(v === true)} />
                <label htmlFor='d-like' className='text-[13px] cursor-pointer'>좋아요</label>
                {likeEnabled && (
                  <Input type='number' min={1} value={likeCount} onChange={e => setLikeCount(parseInt(e.target.value) || 1)} className='ml-auto w-20 h-8' />
                )}
              </div>

              {/* Comment */}
              <div className='space-y-2'>
                <div className='flex items-center gap-3'>
                  <Checkbox id='d-comment' checked={commentEnabled} onCheckedChange={v => setCommentEnabled(v === true)} />
                  <label htmlFor='d-comment' className='text-[13px] cursor-pointer'>댓글</label>
                </div>
                {commentEnabled && (
                  <div className='ml-7 space-y-2'>
                    <RadioGroup value={commentMode} onValueChange={v => setCommentMode(v as 'manual' | 'ai')}>
                      <div className='flex items-center gap-2'>
                        <RadioGroupItem value='ai' id='dc-ai' />
                        <label htmlFor='dc-ai' className='text-[12px] cursor-pointer'>AI 생성</label>
                      </div>
                      <div className='flex items-center gap-2'>
                        <RadioGroupItem value='manual' id='dc-manual' />
                        <label htmlFor='dc-manual' className='text-[12px] cursor-pointer'>직접 입력</label>
                      </div>
                    </RadioGroup>
                    {commentMode === 'manual' && (
                      <Input value={commentText} onChange={e => setCommentText(e.target.value)} placeholder='댓글 내용 입력' className='h-8' />
                    )}
                  </div>
                )}
              </div>

              {/* Reply */}
              <div className='space-y-2'>
                <div className='flex items-center gap-3'>
                  <Checkbox id='d-reply' checked={replyEnabled} onCheckedChange={v => setReplyEnabled(v === true)} />
                  <label htmlFor='d-reply' className='text-[13px] cursor-pointer'>대댓글</label>
                </div>
                {replyEnabled && (
                  <div className='ml-7 space-y-2'>
                    <Input value={replyTarget} onChange={e => setReplyTarget(e.target.value)} placeholder='대상 댓글 (텍스트 일부 또는 작성자)' className='h-8' />
                    <RadioGroup value={replyMode} onValueChange={v => setReplyMode(v as 'manual' | 'ai')}>
                      <div className='flex items-center gap-2'>
                        <RadioGroupItem value='ai' id='dr-ai' />
                        <label htmlFor='dr-ai' className='text-[12px] cursor-pointer'>AI 생성</label>
                      </div>
                      <div className='flex items-center gap-2'>
                        <RadioGroupItem value='manual' id='dr-manual' />
                        <label htmlFor='dr-manual' className='text-[12px] cursor-pointer'>직접 입력</label>
                      </div>
                    </RadioGroup>
                    {replyMode === 'manual' && (
                      <Textarea value={replyText} onChange={e => setReplyText(e.target.value)} placeholder='대댓글 내용 입력' rows={2} />
                    )}
                  </div>
                )}
              </div>

              {/* Subscribe */}
              <div className='flex items-center gap-3'>
                <Checkbox id='d-sub' checked={subscribeEnabled} onCheckedChange={v => setSubscribeEnabled(v === true)} />
                <label htmlFor='d-sub' className='text-[13px] cursor-pointer'>구독</label>
              </div>
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)} className='hydra-btn-press'>
            취소
          </Button>
          <Button onClick={handleSubmit} disabled={loading || urlCount === 0 || !hasAction} className='hydra-btn-press'>
            {loading ? '실행 중...' : '실행'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
