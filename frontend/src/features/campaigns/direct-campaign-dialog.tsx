import { useEffect, useState } from 'react'
import { Badge } from '@/components/ui/badge'
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
import { Label } from '@/components/ui/label'
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

interface PresetStep {
  step_number: number
  role: string
  type: string
  tone: string
}

interface Preset {
  id: number
  code: string
  name: string
  steps: PresetStep[]
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
  const [workMode, setWorkMode] = useState<'preset' | 'manual'>('manual')
  const [urls, setUrls] = useState('')

  // Preset mode state
  const [presets, setPresets] = useState<Preset[]>([])
  const [brands, setBrands] = useState<Brand[]>([])
  const [selectedPreset, setSelectedPreset] = useState('')
  const [selectedBrand, setSelectedBrand] = useState('')

  // Manual mode state
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

  // Shared
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      fetchApi<Preset[]>('/api/presets/')
        .then(setPresets)
        .catch(() => setPresets([]))
      fetchApi<Brand[]>('/brands/api/list')
        .then(setBrands)
        .catch(() => setBrands([]))
    }
  }, [open])

  const selectedPresetData = presets.find((p) => p.code === selectedPreset)

  const handleSubmit = async () => {
    const urlList = urls
      .split('\n')
      .map((u) => u.trim())
      .filter(Boolean)
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
            like_count: likeEnabled ? likeCount : 0,
            subscribe: subscribeEnabled,
          }),
        })
      } else {
        await fetchApi('/campaigns/api/direct/create', {
          method: 'POST',
          body: JSON.stringify({
            urls: urlList,
            actions: {
              like: likeEnabled ? { count: likeCount } : null,
              comment: commentEnabled
                ? { mode: commentMode, text: commentMode === 'manual' ? commentText : null }
                : null,
              reply: replyEnabled
                ? { target: replyTarget, mode: replyMode, text: replyMode === 'manual' ? replyText : null }
                : null,
              subscribe: subscribeEnabled,
            },
          }),
        })
      }
      onOpenChange(false)
      onSuccess()
    } catch {
      // error handled silently
    } finally {
      setLoading(false)
    }
  }

  const hasAction =
    workMode === 'preset'
      ? !!selectedPreset
      : likeEnabled || commentEnabled || replyEnabled || subscribeEnabled
  const urlCount = urls
    .split('\n')
    .map((u) => u.trim())
    .filter(Boolean).length

  const roleLabels: Record<string, string> = {
    seed: '시드',
    asker: '질문자',
    witness: '목격자',
    agree: '동조자',
    curious: '궁금이',
    info: '정보통',
    fan: '팬',
    qa: 'QA',
    supporter: '서포터',
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>다이렉트 캠페인</DialogTitle>
        </DialogHeader>
        <div className='grid gap-4 py-2'>
          <div className='grid gap-2'>
            <Label>URL 입력 (한 줄에 하나)</Label>
            <Textarea
              value={urls}
              onChange={(e) => setUrls(e.target.value)}
              placeholder={'https://youtube.com/watch?v=...\nhttps://youtube.com/watch?v=...'}
              rows={4}
            />
            {urlCount > 0 && (
              <p className='text-xs text-muted-foreground'>
                {urlCount}개 URL 입력됨
              </p>
            )}
          </div>

          {/* Work mode toggle */}
          <div className='grid gap-2'>
            <Label>작업 방식</Label>
            <RadioGroup
              value={workMode}
              onValueChange={(v) => setWorkMode(v as 'preset' | 'manual')}
              className='flex gap-4'
            >
              <div className='flex items-center gap-2'>
                <RadioGroupItem value='preset' id='mode-preset' />
                <Label htmlFor='mode-preset' className='font-normal'>
                  프리셋 선택 (대화 구조 자동)
                </Label>
              </div>
              <div className='flex items-center gap-2'>
                <RadioGroupItem value='manual' id='mode-manual' />
                <Label htmlFor='mode-manual' className='font-normal'>
                  수동 입력 (개별 댓글)
                </Label>
              </div>
            </RadioGroup>
          </div>

          {workMode === 'preset' ? (
            <div className='grid gap-3'>
              {/* Preset selector */}
              <div className='grid gap-2'>
                <Label>프리셋</Label>
                <Select value={selectedPreset} onValueChange={setSelectedPreset}>
                  <SelectTrigger>
                    <SelectValue placeholder='프리셋을 선택하세요' />
                  </SelectTrigger>
                  <SelectContent>
                    {presets.map((p) => (
                      <SelectItem key={p.id} value={p.code}>
                        <span className='font-mono text-xs text-muted-foreground'>
                          {p.code}
                        </span>{' '}
                        {p.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Brand selector */}
              <div className='grid gap-2'>
                <Label>브랜드</Label>
                <Select value={selectedBrand} onValueChange={setSelectedBrand}>
                  <SelectTrigger>
                    <SelectValue placeholder='브랜드를 선택하세요' />
                  </SelectTrigger>
                  <SelectContent>
                    {brands.map((b) => (
                      <SelectItem key={b.id} value={String(b.id)}>
                        {b.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              {/* Preset steps preview */}
              {selectedPresetData?.steps && selectedPresetData.steps.length > 0 && (
                <div className='grid gap-2'>
                  <Label>스텝 미리보기</Label>
                  <div className='space-y-1 rounded-md border p-2'>
                    {selectedPresetData.steps.map((step) => (
                      <div
                        key={step.step_number}
                        className='flex items-center gap-2 text-sm'
                      >
                        <span className='text-muted-foreground'>
                          #{step.step_number}
                        </span>
                        <Badge variant='outline' className='text-xs'>
                          {roleLabels[step.role] || step.role}
                        </Badge>
                        <span className='text-muted-foreground'>
                          {step.type === 'comment' ? '댓글' : '대댓글'}
                        </span>
                        {step.tone && (
                          <span className='text-xs text-muted-foreground'>
                            ({step.tone})
                          </span>
                        )}
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <p className='text-xs text-muted-foreground'>
                AI가 영상 내용에 맞춰 대화를 자동 생성합니다
              </p>

              {/* Like & Subscribe for preset mode */}
              <div className='flex items-center gap-3'>
                <Checkbox
                  id='preset-like'
                  checked={likeEnabled}
                  onCheckedChange={(v) => setLikeEnabled(v === true)}
                />
                <Label htmlFor='preset-like' className='font-normal'>
                  좋아요
                </Label>
                {likeEnabled && (
                  <Input
                    type='number'
                    min={1}
                    value={likeCount}
                    onChange={(e) => setLikeCount(parseInt(e.target.value) || 1)}
                    className='ml-auto w-20'
                  />
                )}
              </div>
              <div className='flex items-center gap-3'>
                <Checkbox
                  id='preset-subscribe'
                  checked={subscribeEnabled}
                  onCheckedChange={(v) => setSubscribeEnabled(v === true)}
                />
                <Label htmlFor='preset-subscribe' className='font-normal'>
                  구독
                </Label>
              </div>
            </div>
          ) : (
            <div className='grid gap-3'>
              <Label>작업 선택</Label>

              {/* Like */}
              <div className='flex items-center gap-3'>
                <Checkbox
                  id='action-like'
                  checked={likeEnabled}
                  onCheckedChange={(v) => setLikeEnabled(v === true)}
                />
                <Label htmlFor='action-like' className='font-normal'>
                  좋아요
                </Label>
                {likeEnabled && (
                  <Input
                    type='number'
                    min={1}
                    value={likeCount}
                    onChange={(e) => setLikeCount(parseInt(e.target.value) || 1)}
                    className='ml-auto w-20'
                  />
                )}
              </div>

              {/* Comment */}
              <div className='space-y-2'>
                <div className='flex items-center gap-3'>
                  <Checkbox
                    id='action-comment'
                    checked={commentEnabled}
                    onCheckedChange={(v) => setCommentEnabled(v === true)}
                  />
                  <Label htmlFor='action-comment' className='font-normal'>
                    댓글
                  </Label>
                </div>
                {commentEnabled && (
                  <div className='ml-7 space-y-2'>
                    <RadioGroup
                      value={commentMode}
                      onValueChange={(v) =>
                        setCommentMode(v as 'manual' | 'ai')
                      }
                    >
                      <div className='flex items-center gap-2'>
                        <RadioGroupItem value='ai' id='comment-ai' />
                        <Label htmlFor='comment-ai' className='font-normal'>
                          AI 생성
                        </Label>
                      </div>
                      <div className='flex items-center gap-2'>
                        <RadioGroupItem value='manual' id='comment-manual' />
                        <Label htmlFor='comment-manual' className='font-normal'>
                          직접 입력
                        </Label>
                      </div>
                    </RadioGroup>
                    {commentMode === 'manual' && (
                      <Input
                        value={commentText}
                        onChange={(e) => setCommentText(e.target.value)}
                        placeholder='댓글 내용 입력'
                      />
                    )}
                  </div>
                )}
              </div>

              {/* Reply */}
              <div className='space-y-2'>
                <div className='flex items-center gap-3'>
                  <Checkbox
                    id='action-reply'
                    checked={replyEnabled}
                    onCheckedChange={(v) => setReplyEnabled(v === true)}
                  />
                  <Label htmlFor='action-reply' className='font-normal'>
                    대댓글
                  </Label>
                </div>
                {replyEnabled && (
                  <div className='ml-7 space-y-2'>
                    <Input
                      value={replyTarget}
                      onChange={(e) => setReplyTarget(e.target.value)}
                      placeholder='대상 댓글 (텍스트 일부 또는 작성자)'
                    />
                    <RadioGroup
                      value={replyMode}
                      onValueChange={(v) =>
                        setReplyMode(v as 'manual' | 'ai')
                      }
                    >
                      <div className='flex items-center gap-2'>
                        <RadioGroupItem value='ai' id='reply-ai' />
                        <Label htmlFor='reply-ai' className='font-normal'>
                          AI 생성
                        </Label>
                      </div>
                      <div className='flex items-center gap-2'>
                        <RadioGroupItem value='manual' id='reply-manual' />
                        <Label htmlFor='reply-manual' className='font-normal'>
                          직접 입력
                        </Label>
                      </div>
                    </RadioGroup>
                    {replyMode === 'manual' && (
                      <Textarea
                        value={replyText}
                        onChange={(e) => setReplyText(e.target.value)}
                        placeholder='대댓글 내용 입력'
                        rows={2}
                      />
                    )}
                  </div>
                )}
              </div>

              {/* Subscribe */}
              <div className='flex items-center gap-3'>
                <Checkbox
                  id='action-subscribe'
                  checked={subscribeEnabled}
                  onCheckedChange={(v) => setSubscribeEnabled(v === true)}
                />
                <Label htmlFor='action-subscribe' className='font-normal'>
                  구독
                </Label>
              </div>
            </div>
          )}
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button
            onClick={handleSubmit}
            disabled={loading || urlCount === 0 || !hasAction}
          >
            {loading ? '실행 중...' : '실행'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
