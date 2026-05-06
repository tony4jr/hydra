import { useState } from 'react'
import { Copy, Check, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

interface WorkerAddDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  onCreated?: () => void
}

interface EnrollResponse {
  enrollment_token: string
  install_command: string
  expires_in_hours: number
}

/**
 * Task 28.5 — enrollment 기반 워커 추가 다이얼로그.
 *
 * 1. 어드민이 worker_name 입력 → POST /api/admin/workers/enroll
 * 2. 서버가 enrollment_token + PowerShell install_command 반환
 * 3. 어드민이 "복사" 눌러 Windows PC 에서 관리자 PowerShell 로 실행
 * 4. 워커 PC 가 /api/workers/enroll 호출 → 등록 완료 (수 초 후 목록에 나타남)
 */
export function WorkerAddDialog({
  open,
  onOpenChange,
  onCreated,
}: WorkerAddDialogProps) {
  const [name, setName] = useState('')
  const [ttlHours, setTtlHours] = useState(24)
  const [creating, setCreating] = useState(false)
  const [result, setResult] = useState<EnrollResponse | null>(null)
  const [copied, setCopied] = useState(false)

  const handleCreate = async () => {
    const worker_name = name.trim()
    if (!worker_name) {
      toast.error('워커 이름을 입력해주세요')
      return
    }
    setCreating(true)
    try {
      const data = await fetchApi<EnrollResponse>(
        '/api/admin/workers/enroll',
        {
          method: 'POST',
          body: JSON.stringify({ worker_name, ttl_hours: ttlHours }),
        },
      )
      setResult(data)
      onCreated?.()
    } catch (e) {
      toast.error((e as Error).message || 'enrollment 토큰 발급 실패')
    } finally {
      setCreating(false)
    }
  }

  const handleCopy = async () => {
    if (!result) return
    await navigator.clipboard.writeText(result.install_command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
    toast.success('클립보드에 복사됨')
  }

  const handleClose = (v: boolean) => {
    if (!v) {
      setName('')
      setTtlHours(24)
      setResult(null)
      setCopied(false)
    }
    onOpenChange(v)
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className='sm:max-w-lg'>
        <DialogHeader>
          <DialogTitle>
            {result ? '설치 명령 발급 완료' : '워커 추가'}
          </DialogTitle>
          <DialogDescription>
            {result
              ? `${result.expires_in_hours}시간 내 Windows PC에서 실행하세요`
              : 'Windows 워커 PC를 등록합니다'}
          </DialogDescription>
        </DialogHeader>

        {result ? (
          <div className='space-y-4'>
            <div className='rounded-md border bg-emerald-500/5 border-emerald-500/30 p-3'>
              <div className='flex items-center justify-between mb-2'>
                <p className='font-semibold text-sm'>방법 A · 더블클릭 (권장)</p>
                <span className='text-[11px] text-muted-foreground'>PowerShell 몰라도 OK</span>
              </div>
              <ol className='text-xs text-muted-foreground space-y-1 mb-3 list-decimal list-inside'>
                <li>아래 버튼으로 install-worker.bat 다운로드</li>
                <li>토큰을 복사 (아래 박스 옆 복사 버튼)</li>
                <li>다운로드한 .bat 파일 더블클릭 → UAC "예" → 토큰 붙여넣기</li>
              </ol>
              <Button
                variant='outline'
                size='sm'
                className='w-full'
                onClick={() => {
                  window.location.href = '/api/workers/install-worker.bat'
                }}
              >
                <Download className='h-3.5 w-3.5 mr-1.5' />
                install-worker.bat 다운로드
              </Button>
              <div className='mt-2 relative rounded-md border bg-muted/50 p-2'>
                <code className='pr-9 block font-mono text-[10px] break-all text-muted-foreground'>
                  {result.enrollment_token}
                </code>
                <Button
                  variant='ghost'
                  size='sm'
                  className='absolute top-1 right-1 h-6 w-6 p-0'
                  onClick={async () => {
                    await navigator.clipboard.writeText(result.enrollment_token)
                    toast.success('토큰 복사됨')
                  }}
                  aria-label='토큰 복사'
                >
                  <Copy className='h-3 w-3' />
                </Button>
              </div>
            </div>

            <div className='rounded-md border bg-muted/30 p-3'>
              <p className='font-semibold text-sm mb-2'>방법 B · PowerShell 한 줄</p>
              <p className='text-xs text-muted-foreground mb-2'>
                관리자 PowerShell 에 아래 명령 붙여넣기.
              </p>
              <div className='relative rounded-md border bg-muted/50 p-3'>
                <pre className='pr-12 whitespace-pre-wrap break-all font-mono text-[11px] leading-relaxed'>
                  {result.install_command}
                </pre>
                <Button
                  variant='secondary'
                  size='sm'
                  className='absolute top-2 right-2'
                  onClick={handleCopy}
                >
                  {copied ? (
                    <Check className='h-3.5 w-3.5' />
                  ) : (
                    <Copy className='h-3.5 w-3.5' />
                  )}
                </Button>
              </div>
            </div>

            <p className='text-xs text-muted-foreground'>
              설치 완료 시 수 초 후 워커 목록에 자동으로 나타납니다.
            </p>
          </div>
        ) : (
          <div className='space-y-4'>
            <div className='space-y-2'>
              <Label htmlFor='worker-name'>워커 이름</Label>
              <Input
                id='worker-name'
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder='예: pc-01, office-desk'
                autoFocus
                disabled={creating}
              />
              <p className='text-xs text-muted-foreground'>
                고유 식별자. 같은 이름으로 재발급 시 토큰만 회전됩니다.
              </p>
            </div>

            <div className='space-y-2'>
              <Label htmlFor='ttl'>만료 시간 (시간)</Label>
              <Input
                id='ttl'
                type='number'
                min={1}
                max={168}
                value={ttlHours}
                onChange={(e) =>
                  setTtlHours(Math.max(1, Number(e.target.value) || 1))
                }
                disabled={creating}
              />
              <p className='text-xs text-muted-foreground'>
                이 시간 내에 설치 스크립트를 실행해야 합니다 (1~168).
              </p>
            </div>
          </div>
        )}

        <DialogFooter>
          {result ? (
            <Button onClick={() => handleClose(false)}>닫기</Button>
          ) : (
            <>
              <Button
                variant='outline'
                onClick={() => handleClose(false)}
                disabled={creating}
              >
                취소
              </Button>
              <Button onClick={handleCreate} disabled={creating}>
                {creating ? '발급 중…' : '설치 명령 발급'}
              </Button>
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
