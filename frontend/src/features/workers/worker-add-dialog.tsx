import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { fetchApi } from '@/lib/api'

interface WorkerAddDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: () => void
}

interface RegisterResponse {
  worker_id: number
  name: string
  token: string
}

export function WorkerAddDialog({
  open,
  onOpenChange,
  onCreated,
}: WorkerAddDialogProps) {
  const [name, setName] = useState('')
  const [allowPreparation, setAllowPreparation] = useState(true)
  const [allowCampaign, setAllowCampaign] = useState(true)
  const [creating, setCreating] = useState(false)
  const [result, setResult] = useState<RegisterResponse | null>(null)
  const [copied, setCopied] = useState(false)

  const handleCreate = async () => {
    if (!name.trim()) return
    setCreating(true)
    try {
      const data = await fetchApi<RegisterResponse>('/api/workers/register', {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          allow_preparation: allowPreparation,
          allow_campaign: allowCampaign,
        }),
      })
      setResult(data)
      onCreated?.()
    } catch {
      alert('워커 생성 실패')
    } finally {
      setCreating(false)
    }
  }

  const handleCopy = async () => {
    if (!result) return
    await navigator.clipboard.writeText(result.token)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleClose = (open: boolean) => {
    if (!open) {
      setName('')
      setAllowPreparation(true)
      setAllowCampaign(true)
      setResult(null)
      setCopied(false)
    }
    onOpenChange(open)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>워커 추가</DialogTitle>
          <DialogDescription>
            {result
              ? '워커가 생성되었습니다. 토큰을 복사하세요.'
              : '새 워커를 등록합니다.'}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className='space-y-4'>
            <div className='space-y-2'>
              <Label>워커 이름</Label>
              <p className='text-sm font-medium'>{result.name}</p>
            </div>
            <div className='space-y-2'>
              <Label>토큰</Label>
              <div className='flex items-center gap-2'>
                <code className='flex-1 rounded-lg bg-muted p-3 text-sm break-all'>
                  {result.token}
                </code>
                <Button
                  variant='outline'
                  size='icon'
                  onClick={handleCopy}
                >
                  {copied ? (
                    <Check className='h-4 w-4 text-green-500' />
                  ) : (
                    <Copy className='h-4 w-4' />
                  )}
                </Button>
              </div>
              <p className='text-xs text-destructive'>
                이 토큰은 다시 표시되지 않습니다. 반드시 복사하여 보관하세요.
              </p>
            </div>
            <DialogFooter>
              <Button onClick={() => handleClose(false)}>닫기</Button>
            </DialogFooter>
          </div>
        ) : (
          <div className='space-y-4'>
            <div className='space-y-2'>
              <Label htmlFor='worker-name'>워커 이름</Label>
              <Input
                id='worker-name'
                placeholder='예: Worker-PC-01'
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>
            <div className='space-y-3'>
              <Label>역할</Label>
              <div className='flex items-center space-x-2'>
                <Checkbox
                  id='allow-preparation'
                  checked={allowPreparation}
                  onCheckedChange={(v) => setAllowPreparation(!!v)}
                />
                <label
                  htmlFor='allow-preparation'
                  className='text-sm leading-none'
                >
                  준비 작업 허용
                </label>
              </div>
              <div className='flex items-center space-x-2'>
                <Checkbox
                  id='allow-campaign'
                  checked={allowCampaign}
                  onCheckedChange={(v) => setAllowCampaign(!!v)}
                />
                <label
                  htmlFor='allow-campaign'
                  className='text-sm leading-none'
                >
                  캠페인 작업 허용
                </label>
              </div>
            </div>
            <DialogFooter>
              <Button
                variant='outline'
                onClick={() => handleClose(false)}
              >
                취소
              </Button>
              <Button
                onClick={handleCreate}
                disabled={!name.trim() || creating}
              >
                {creating ? '생성 중...' : '생성'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
