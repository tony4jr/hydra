import { useEffect, useState } from 'react'
import { toast } from 'sonner'

import { fetchApi } from '@/lib/api'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  brandId: number
  onSuccess: () => void
}

/**
 * 타겟(니치) 추가 — 단순화 모달.
 * 받는 정보는 이름 + 오디언스 두 가지뿐.
 * 이름 → /api/admin/niches POST
 * 오디언스 → 직후 /api/admin/niches/{id}/messaging PATCH
 */
export function NicheCreateDialog({ open, onOpenChange, brandId, onSuccess }: Props) {
  const [name, setName] = useState('')
  const [audience, setAudience] = useState('')
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    if (open) {
      setName('')
      setAudience('')
    }
  }, [open])

  const submit = async () => {
    const trimmedName = name.trim()
    if (!trimmedName) return
    setBusy(true)
    try {
      const created = await fetchApi<{ id: number }>('/api/admin/niches', {
        method: 'POST',
        body: JSON.stringify({
          brand_id: brandId,
          name: trimmedName,
          description: null,
        }),
      })
      const trimmedAudience = audience.trim()
      if (trimmedAudience && created?.id) {
        try {
          await fetchApi(`/api/admin/niches/${created.id}/messaging`, {
            method: 'PATCH',
            body: JSON.stringify({ target_audience: trimmedAudience }),
          })
        } catch {
          // 오디언스 저장 실패해도 niche 자체는 생성됨 — 메시지 탭에서 채울 수 있음
        }
      }
      onOpenChange(false)
      onSuccess()
    } catch (e) {
      toast.error('타겟 추가 실패', {
        description: e instanceof Error ? e.message : String(e),
      })
    } finally {
      setBusy(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>타겟 추가</DialogTitle>
        </DialogHeader>
        <div className='space-y-5 py-2'>
          <div>
            <label className='text-foreground text-sm font-medium mb-1.5 block'>타겟 이름</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder='예: 산후, 남성, 30대 직장인'
              autoFocus
            />
          </div>
          <div>
            <label className='text-foreground text-sm font-medium mb-1.5 block'>오디언스</label>
            <Textarea
              value={audience}
              onChange={(e) => setAudience(e.target.value)}
              placeholder='예: 출산 후 6~24개월 여성 / 30~40대 직장 남성'
              rows={3}
            />
            <p className='text-muted-foreground text-xs mt-1.5'>
              누구를 노릴지 한 줄로. 비워둬도 나중에 메시지 탭에서 채울 수 있어요.
            </p>
          </div>
          <p className='text-muted-foreground text-xs'>
            수집 키워드·메시지·캠페인은 타겟 생성 후 각 탭에서 설정합니다.
          </p>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button onClick={submit} disabled={busy || !name.trim()}>
            {busy ? '추가 중…' : '추가'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
