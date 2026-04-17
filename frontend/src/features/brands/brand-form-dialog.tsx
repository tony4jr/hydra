import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { fetchApi } from '@/lib/api'

interface BrandFormData {
  name: string
  product_category: string
  core_message: string
  tone_guide: string
  weekly_campaign_target: number
  auto_campaign_enabled: boolean
}

interface Brand {
  id: number
  name: string
  product_category: string | null
  core_message: string | null
  tone_guide: string | null
  status: string
  weekly_campaign_target: number
  auto_campaign_enabled: boolean
}

interface BrandFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'create' | 'edit'
  brand?: Brand | null
  onSuccess: () => void
}

const defaultForm: BrandFormData = {
  name: '',
  product_category: '',
  core_message: '',
  tone_guide: '',
  weekly_campaign_target: 5,
  auto_campaign_enabled: false,
}

export function BrandFormDialog({
  open,
  onOpenChange,
  mode,
  brand,
  onSuccess,
}: BrandFormDialogProps) {
  const [form, setForm] = useState<BrandFormData>(defaultForm)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      if (mode === 'edit' && brand) {
        setForm({
          name: brand.name || '',
          product_category: brand.product_category || '',
          core_message: brand.core_message || '',
          tone_guide: brand.tone_guide || '',
          weekly_campaign_target: brand.weekly_campaign_target || 5,
          auto_campaign_enabled: brand.auto_campaign_enabled || false,
        })
      } else {
        setForm(defaultForm)
      }
    }
  }, [open, mode, brand])

  const handleSubmit = async () => {
    if (!form.name.trim()) return
    setLoading(true)
    try {
      const url =
        mode === 'edit' && brand
          ? `/brands/api/${brand.id}/update`
          : '/brands/api/create'
      await fetchApi(url, {
        method: 'POST',
        body: JSON.stringify(form),
      })
      onOpenChange(false)
      onSuccess()
    } catch {
      // error handled silently
    } finally {
      setLoading(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className='sm:max-w-md'>
        <DialogHeader>
          <DialogTitle>
            {mode === 'create' ? '브랜드 추가' : '브랜드 수정'}
          </DialogTitle>
        </DialogHeader>
        <div className='grid gap-4 py-2'>
          <div className='grid gap-2'>
            <Label htmlFor='brand-name'>브랜드명 *</Label>
            <Input
              id='brand-name'
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder='브랜드명을 입력하세요'
            />
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='brand-category'>카테고리</Label>
            <Input
              id='brand-category'
              value={form.product_category}
              onChange={(e) =>
                setForm({ ...form, product_category: e.target.value })
              }
              placeholder='예: 화장품, IT서비스, 식품'
            />
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='brand-message'>핵심 메시지</Label>
            <Textarea
              id='brand-message'
              value={form.core_message}
              onChange={(e) =>
                setForm({ ...form, core_message: e.target.value })
              }
              placeholder='브랜드의 핵심 메시지를 입력하세요'
              rows={3}
            />
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='brand-tone'>톤 가이드</Label>
            <Textarea
              id='brand-tone'
              value={form.tone_guide}
              onChange={(e) =>
                setForm({ ...form, tone_guide: e.target.value })
              }
              placeholder='댓글 작성 시 톤/말투 가이드'
              rows={3}
            />
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='brand-target'>주간 목표</Label>
            <Input
              id='brand-target'
              type='number'
              min={0}
              value={form.weekly_campaign_target}
              onChange={(e) =>
                setForm({
                  ...form,
                  weekly_campaign_target: parseInt(e.target.value) || 0,
                })
              }
            />
          </div>
          <div className='flex items-center gap-3'>
            <Switch
              id='brand-auto'
              checked={form.auto_campaign_enabled}
              onCheckedChange={(checked) =>
                setForm({ ...form, auto_campaign_enabled: checked })
              }
            />
            <Label htmlFor='brand-auto'>자동 캠페인</Label>
          </div>
        </div>
        <DialogFooter>
          <Button variant='outline' onClick={() => onOpenChange(false)}>
            취소
          </Button>
          <Button onClick={handleSubmit} disabled={loading || !form.name.trim()}>
            {loading ? '저장 중...' : mode === 'create' ? '추가' : '저장'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
