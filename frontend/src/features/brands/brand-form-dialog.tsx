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
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { fetchApi } from '@/lib/api'

interface Preset {
  id: number
  code: string
  name: string
}

interface BrandFormData {
  name: string
  product_category: string
  core_message: string
  tone_guide: string
  promo_keywords: string
  target_keywords: string
  selected_presets: string[]
  weekly_campaign_target: number
  auto_campaign_enabled: boolean
}

interface Brand {
  id: number
  name: string
  product_category: string | null
  core_message: string | null
  tone_guide: string | null
  promo_keywords: string[] | null
  target_keywords: string[] | null
  selected_presets: string[] | null
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
  promo_keywords: '',
  target_keywords: '',
  selected_presets: [],
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
  const [presets, setPresets] = useState<Preset[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (open) {
      fetchApi<Preset[]>('/api/presets/')
        .then(setPresets)
        .catch(() => setPresets([]))

      if (mode === 'edit' && brand) {
        setForm({
          name: brand.name || '',
          product_category: brand.product_category || '',
          core_message: brand.core_message || '',
          tone_guide: brand.tone_guide || '',
          promo_keywords: (brand.promo_keywords || []).join(', '),
          target_keywords: (brand.target_keywords || []).join(', '),
          selected_presets: brand.selected_presets || [],
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
      const payload = {
        ...form,
        promo_keywords: form.promo_keywords
          .split(',')
          .map((k) => k.trim())
          .filter(Boolean),
        target_keywords: form.target_keywords
          .split(',')
          .map((k) => k.trim())
          .filter(Boolean),
      }
      await fetchApi(url, {
        method: 'POST',
        body: JSON.stringify(payload),
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
            <Label htmlFor='brand-tone'>브랜드 멘션 스타일</Label>
            <Textarea
              id='brand-tone'
              value={form.tone_guide}
              onChange={(e) =>
                setForm({ ...form, tone_guide: e.target.value })
              }
              placeholder='간접 언급 / 직접 추천 / 경험담 형식 등'
              rows={3}
            />
            <p className='text-xs text-muted-foreground'>
              페르소나별 말투(ㅋㅋ체, 존댓말 등)는 자동 적용됩니다. 여기서는
              제품을 어떻게 언급할지만 설정하세요.
            </p>
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='brand-promo'>홍보 키워드</Label>
            <Textarea
              id='brand-promo'
              value={form.promo_keywords}
              onChange={(e) =>
                setForm({ ...form, promo_keywords: e.target.value })
              }
              placeholder='댓글에 녹일 메시지 키워드 (쉼표로 구분)'
              rows={2}
            />
            <p className='text-xs text-muted-foreground'>
              쉼표로 구분하여 입력하세요
            </p>
          </div>
          <div className='grid gap-2'>
            <Label htmlFor='brand-target-kw'>타겟 키워드</Label>
            <Textarea
              id='brand-target-kw'
              value={form.target_keywords}
              onChange={(e) =>
                setForm({ ...form, target_keywords: e.target.value })
              }
              placeholder='영상 검색용 키워드 (쉼표로 구분)'
              rows={2}
            />
            <p className='text-xs text-muted-foreground'>
              영상 수집 시 사용할 검색 키워드
            </p>
          </div>
          {presets.length > 0 && (
            <div className='grid gap-2'>
              <Label>사용할 프리셋</Label>
              <div className='max-h-32 space-y-1 overflow-y-auto rounded-md border p-2'>
                {presets.map((p) => (
                  <label
                    key={p.id}
                    className='flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-sm hover:bg-muted'
                  >
                    <Checkbox
                      checked={form.selected_presets.includes(p.code)}
                      onCheckedChange={(checked) => {
                        setForm((prev) => ({
                          ...prev,
                          selected_presets: checked
                            ? [...prev.selected_presets, p.code]
                            : prev.selected_presets.filter((c) => c !== p.code),
                        }))
                      }}
                    />
                    <span>
                      <span className='font-mono text-xs text-muted-foreground'>
                        {p.code}
                      </span>{' '}
                      {p.name}
                    </span>
                  </label>
                ))}
              </div>
            </div>
          )}
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
