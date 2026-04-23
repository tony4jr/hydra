import { useEffect, useState } from 'react'
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
import { Label } from '@/components/ui/label'
import { fetchApi } from '@/lib/api'
import { toast } from 'sonner'

/** Task 39 — 서버 VALID_TASK_TYPES 와 일치 유지 필수. */
const TASK_TYPES = [
  { value: 'create_account', label: '계정 생성' },
  { value: 'comment', label: '댓글' },
  { value: 'like', label: '좋아요' },
  { value: 'watch_video', label: '영상 시청' },
  { value: 'warmup', label: '워밍업' },
  { value: 'onboarding_verify', label: '온보딩 검증' },
]

interface WorkerEditDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  worker: {
    id: number
    name: string
    allowed_task_types: string[]
    allow_preparation?: boolean | null
    allow_campaign?: boolean | null
  } | null
  onSaved?: () => void
}

export function WorkerEditDialog({
  open,
  onOpenChange,
  worker,
  onSaved,
}: WorkerEditDialogProps) {
  const [wildcard, setWildcard] = useState(true)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [prep, setPrep] = useState(false)
  const [camp, setCamp] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (!worker) return
    const isWild = worker.allowed_task_types.includes('*')
    setWildcard(isWild)
    setSelected(
      new Set(worker.allowed_task_types.filter((t) => t !== '*')),
    )
    setPrep(!!worker.allow_preparation)
    setCamp(worker.allow_campaign !== false)
  }, [worker])

  const toggle = (value: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(value)) next.delete(value)
      else next.add(value)
      return next
    })
  }

  const save = async () => {
    if (!worker) return
    const types = wildcard ? ['*'] : Array.from(selected)
    if (!wildcard && types.length === 0) {
      toast.error('최소 한 가지 작업 유형을 선택하거나 전체 허용을 켜세요')
      return
    }
    setSaving(true)
    try {
      await fetchApi(`/api/admin/workers/${worker.id}`, {
        method: 'PATCH',
        body: JSON.stringify({
          allowed_task_types: types,
          allow_preparation: prep,
          allow_campaign: camp,
        }),
      })
      toast.success('저장됨')
      onSaved?.()
      onOpenChange(false)
    } catch (e) {
      toast.error((e as Error).message || '저장 실패')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            워커 설정 · <span className='font-mono'>{worker?.name}</span>
          </DialogTitle>
          <DialogDescription>
            이 워커가 처리할 작업 유형과 역할을 설정합니다.
          </DialogDescription>
        </DialogHeader>

        <div className='space-y-5 py-2'>
          <div className='space-y-2'>
            <Label>작업 유형</Label>
            <div className='flex items-start gap-2 rounded-md border bg-muted/30 p-3'>
              <Checkbox
                id='wild'
                checked={wildcard}
                onCheckedChange={(v) => setWildcard(Boolean(v))}
              />
              <div>
                <Label htmlFor='wild' className='font-medium'>
                  전체 허용 (와일드카드)
                </Label>
                <p className='text-xs text-muted-foreground'>
                  모든 종류의 작업을 수행합니다
                </p>
              </div>
            </div>

            <div
              className={
                wildcard
                  ? 'pointer-events-none space-y-1 opacity-50'
                  : 'space-y-1'
              }
            >
              {TASK_TYPES.map((t) => (
                <label
                  key={t.value}
                  className='flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-muted/40'
                >
                  <Checkbox
                    checked={selected.has(t.value)}
                    onCheckedChange={() => toggle(t.value)}
                    disabled={wildcard}
                  />
                  <span className='text-sm'>{t.label}</span>
                  <span className='ml-auto font-mono text-[11px] text-muted-foreground'>
                    {t.value}
                  </span>
                </label>
              ))}
            </div>
          </div>

          <div className='space-y-2'>
            <Label>역할</Label>
            <label className='flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-muted/40'>
              <Checkbox
                checked={prep}
                onCheckedChange={(v) => setPrep(Boolean(v))}
              />
              <span className='text-sm'>워밍업 / 준비 단계</span>
            </label>
            <label className='flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-muted/40'>
              <Checkbox
                checked={camp}
                onCheckedChange={(v) => setCamp(Boolean(v))}
              />
              <span className='text-sm'>캠페인 실행</span>
            </label>
          </div>
        </div>

        <DialogFooter>
          <Button
            variant='outline'
            onClick={() => onOpenChange(false)}
            disabled={saving}
          >
            취소
          </Button>
          <Button onClick={save} disabled={saving}>
            {saving ? '저장중…' : '저장'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
