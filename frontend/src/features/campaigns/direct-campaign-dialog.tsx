import { useState } from 'react'
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
import { Textarea } from '@/components/ui/textarea'
import { fetchApi } from '@/lib/api'

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
  const [urls, setUrls] = useState('')
  const [likeEnabled, setLikeEnabled] = useState(false)
  const [likeCount, setLikeCount] = useState(1)
  const [commentEnabled, setCommentEnabled] = useState(false)
  const [commentMode, setCommentMode] = useState<'manual' | 'ai'>('ai')
  const [commentText, setCommentText] = useState('')
  const [subscribeEnabled, setSubscribeEnabled] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async () => {
    const urlList = urls
      .split('\n')
      .map((u) => u.trim())
      .filter(Boolean)
    if (urlList.length === 0) return

    setLoading(true)
    try {
      await fetchApi('/campaigns/api/direct/create', {
        method: 'POST',
        body: JSON.stringify({
          urls: urlList,
          actions: {
            like: likeEnabled ? { count: likeCount } : null,
            comment: commentEnabled
              ? { mode: commentMode, text: commentMode === 'manual' ? commentText : null }
              : null,
            subscribe: subscribeEnabled,
          },
        }),
      })
      onOpenChange(false)
      onSuccess()
    } catch {
      // error handled silently
    } finally {
      setLoading(false)
    }
  }

  const hasAction = likeEnabled || commentEnabled || subscribeEnabled
  const urlCount = urls
    .split('\n')
    .map((u) => u.trim())
    .filter(Boolean).length

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
