import { useState } from 'react'
import { Copy, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
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

export function WorkerAddDialog({ open, onOpenChange, onCreated }: WorkerAddDialogProps) {
  const [name, setName] = useState('')
  const [registrationSecret, setRegistrationSecret] = useState('')
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
          registration_secret: registrationSecret,
          allow_preparation: allowPreparation,
          allow_campaign: allowCampaign,
        }),
      })
      setResult(data)
      onCreated?.()
    } catch {
      // error
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

  const handleClose = (v: boolean) => {
    if (!v) {
      setName('')
      setRegistrationSecret('')
      setAllowPreparation(true)
      setAllowCampaign(true)
      setResult(null)
      setCopied(false)
    }
    onOpenChange(v)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>{result ? '워커 생성 완료' : '워커 추가'}</DialogTitle>
        </DialogHeader>

        {result ? (
          <div className='space-y-5 py-2'>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>워커 이름</label>
              <p className='text-foreground text-[14px] font-medium'>{result.name}</p>
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>연결 토큰</label>
              <p className='text-muted-foreground text-xs mb-2'>이 토큰은 다시 표시되지 않습니다. 반드시 복사하세요.</p>
              <div className='flex items-center gap-2'>
                <code className='flex-1 rounded-lg bg-muted p-3 text-[12px] break-all font-mono'>
                  {result.token}
                </code>
                <Button variant='outline' size='icon' onClick={handleCopy} className='hydra-btn-press'>
                  {copied ? <Check className='h-4 w-4 text-green-500' /> : <Copy className='h-4 w-4' />}
                </Button>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => handleClose(false)} className='hydra-btn-press'>닫기</Button>
            </DialogFooter>
          </div>
        ) : (
          <div className='space-y-5 py-2'>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>워커 이름</label>
              <p className='text-muted-foreground text-xs mb-2'>이 PC를 구분할 수 있는 이름</p>
              <Input
                placeholder='예: Worker-PC-01'
                value={name}
                onChange={e => setName(e.target.value)}
              />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>등록 시크릿</label>
              <p className='text-muted-foreground text-xs mb-2'>서버 설정의 WORKER_TOKEN_SECRET 값</p>
              <Input
                type='password'
                placeholder='시크릿 입력'
                value={registrationSecret}
                onChange={e => setRegistrationSecret(e.target.value)}
              />
            </div>
            <div className='mb-5'>
              <label className='text-foreground text-sm font-medium mb-1.5'>역할</label>
              <p className='text-muted-foreground text-xs mb-2'>이 워커가 수행할 작업 유형</p>
              <div className='space-y-2 mt-1'>
                <label className='flex items-center gap-2 cursor-pointer'>
                  <Checkbox checked={allowPreparation} onCheckedChange={v => setAllowPreparation(!!v)} />
                  <span className='text-[13px]'>준비 작업 (로그인, 워밍업, 채널 설정)</span>
                </label>
                <label className='flex items-center gap-2 cursor-pointer'>
                  <Checkbox checked={allowCampaign} onCheckedChange={v => setAllowCampaign(!!v)} />
                  <span className='text-[13px]'>캠페인 작업 (댓글, 좋아요, 부스트)</span>
                </label>
              </div>
            </div>
            <DialogFooter>
              <Button variant='outline' onClick={() => handleClose(false)} className='hydra-btn-press'>취소</Button>
              <Button onClick={handleCreate} disabled={!name.trim() || !registrationSecret.trim() || creating} className='hydra-btn-press'>
                {creating ? '생성 중...' : '생성'}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
