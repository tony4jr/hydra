import { useEffect, useState, useCallback } from 'react'
import { toast } from 'sonner'
import { X } from 'lucide-react'
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
import { fetchApi } from '@/lib/api'

interface Brand {
  id: number
  name: string
  product_name?: string | null
  product_category: string | null
  core_message: string | null
  promo_keywords: string[] | null
  status: string
  collection_depth?: string
  longtail_count?: number
  preset_video_limit?: number
}

interface BrandFormDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  mode: 'create' | 'edit'
  brand?: Brand | null
  onSuccess: () => void
}

export function BrandFormDialog({
  open,
  onOpenChange,
  mode,
  brand,
  onSuccess,
}: BrandFormDialogProps) {
  const [name, setName] = useState('')
  const [productName, setProductName] = useState('')
  const [category, setCategory] = useState('')
  const [coreMessage, setCoreMessage] = useState('')
  const [promoKeywords, setPromoKeywords] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState('')
  const [collectionDepth, setCollectionDepth] = useState<'quick'|'standard'|'deep'|'max'>('standard')
  const [longtailCount, setLongtailCount] = useState(5)
  const [presetVideoLimit, setPresetVideoLimit] = useState(1)
  const [loading, setLoading] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)

  useEffect(() => {
    if (open) {
      if (mode === 'edit' && brand) {
        setName(brand.name || '')
        setProductName(brand.product_name || '')
        setCategory(brand.product_category || '')
        setCoreMessage(brand.core_message || '')
        setPromoKeywords(brand.promo_keywords || [])
        setCollectionDepth((brand.collection_depth as any) || 'standard')
        setLongtailCount(brand.longtail_count ?? 5)
        setPresetVideoLimit(brand.preset_video_limit ?? 1)
      } else {
        setName('')
        setProductName('')
        setCategory('')
        setCoreMessage('')
        setPromoKeywords([])
        setCollectionDepth('standard')
        setLongtailCount(5)
        setPresetVideoLimit(1)
      }
      setKeywordInput('')
      setDeleteConfirm(false)
    }
  }, [open, mode, brand])

  const addKeyword = useCallback(() => {
    const trimmed = keywordInput.trim()
    if (trimmed && !promoKeywords.includes(trimmed)) {
      setPromoKeywords(prev => [...prev, trimmed])
    }
    setKeywordInput('')
  }, [keywordInput, promoKeywords])

  const removeKeyword = (kw: string) => {
    setPromoKeywords(prev => prev.filter(k => k !== kw))
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
      e.preventDefault()
      addKeyword()
    }
  }

  const handleSubmit = async () => {
    if (!name.trim()) return
    setLoading(true)
    try {
      const url = mode === 'edit' && brand
        ? `/brands/api/${brand.id}/update`
        : '/brands/api/create'
      const saved = await fetchApi<{ id: number }>(url, {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          product_name: productName.trim() || null,
          product_category: category.trim(),
          core_message: coreMessage.trim(),
          promo_keywords: promoKeywords,
        }),
      })
      // 수집/픽업 정책은 별도 엔드포인트로 저장 (admin_collection)
      const targetId = (mode === 'edit' && brand) ? brand.id : (saved as any)?.id
      if (targetId) {
        try {
          await fetchApi(`/api/admin/collection/policy/${targetId}`, {
            method: 'PATCH',
            body: JSON.stringify({
              collection_depth: collectionDepth,
              longtail_count: longtailCount,
              preset_video_limit: presetVideoLimit,
            }),
          })
        } catch { /* policy 저장 실패해도 brand 자체는 만들어짐 */ }
      }
      onOpenChange(false)
      onSuccess()
    } catch (e) { toast.error("오류", { description: e instanceof Error ? e.message : String(e) }) } finally {
      setLoading(false)
    }
  }

  const handleDelete = async () => {
    if (!brand) return
    if (!deleteConfirm) {
      setDeleteConfirm(true)
      return
    }
    setLoading(true)
    try {
      await fetchApi(`/brands/api/${brand.id}/update-field`, {
        method: 'POST',
        body: JSON.stringify({ field: 'status', value: 'deleted' }),
      })
      onOpenChange(false)
      onSuccess()
    } catch (e) { toast.error("오류", { description: e instanceof Error ? e.message : String(e) }) } finally {
      setLoading(false)
      setDeleteConfirm(false)
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
        <div className='space-y-5 py-2'>
          {/* Name (회사/모브랜드) */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>브랜드 이름</label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder='예: 트리코라'
              autoFocus
            />
            <p className='text-muted-foreground text-xs mt-1'>회사 또는 모브랜드 이름</p>
          </div>

          {/* Product name */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>상품명</label>
            <Input
              value={productName}
              onChange={(e) => setProductName(e.target.value)}
              placeholder='예: 모렉신'
            />
            <p className='text-muted-foreground text-xs mt-1'>홍보할 개별 상품 (없으면 비워두세요)</p>
          </div>

          {/* Category */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>카테고리</label>
            <Input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder='예: 탈모영양제, 화장품, IT서비스'
            />
          </div>

          {mode === 'create' && (
            <p className='text-muted-foreground text-xs'>
              나머지 설정 (메시지·수집 정책·키워드)은 브랜드 생성 후 타겟 단위로 설정합니다.
            </p>
          )}

          {/* Core Message — edit only */}
          {mode === 'edit' && <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>핵심 메시지</label>
            <p className='text-muted-foreground text-xs mb-2'>댓글에서 자연스럽게 전달할 셀링 포인트</p>
            <Textarea
              value={coreMessage}
              onChange={(e) => setCoreMessage(e.target.value)}
              placeholder='예: 케라틴 직접 보충으로 모발 성장 촉진, 해외 논문 검증'
              rows={3}
            />
          </div>}

          {/* 수집 정책 — edit only */}
          {mode === 'edit' && <div className='mb-5 rounded-lg border border-border p-3 space-y-3 bg-muted/20'>
            <div className='flex items-center justify-between'>
              <span className='text-foreground text-sm font-medium'>영상 수집 정책</span>
              <span className='text-muted-foreground text-[11px]'>운영 중 변경 가능</span>
            </div>

            <div>
              <label className='text-foreground text-xs font-medium mb-1 block'>수집 깊이</label>
              <div className='flex gap-1 flex-wrap'>
                {(['quick','standard','deep','max'] as const).map(d => (
                  <button key={d} type='button'
                    onClick={() => setCollectionDepth(d)}
                    className={`px-3 py-1.5 rounded-md text-xs border ${
                      collectionDepth === d
                        ? 'border-primary bg-primary/10 text-primary'
                        : 'border-border bg-background text-muted-foreground hover:bg-muted/40'
                    }`}>
                    {d === 'quick' ? '빠름 (1년)' :
                     d === 'standard' ? '표준 (5년)' :
                     d === 'deep' ? '깊음 (5년+변형15)' :
                     '최대 (10년+변형30)'}
                  </button>
                ))}
              </div>
              <p className='text-muted-foreground text-[11px] mt-1.5'>
                깊을수록 풀 크고 시간 오래. 운영 중 바꿀 수 있음.
              </p>
            </div>

            <div className='grid grid-cols-2 gap-3'>
              <div>
                <label className='text-foreground text-xs font-medium mb-1 block'>변형 키워드 수</label>
                <Input
                  type='number'
                  value={longtailCount}
                  min={0} max={50}
                  onChange={e => setLongtailCount(Math.max(0, Math.min(50, parseInt(e.target.value) || 0)))}
                  className='h-8 text-sm'
                />
                <p className='text-muted-foreground text-[10px] mt-0.5'>키워드당 자동 생성</p>
              </div>
              <div>
                <label className='text-foreground text-xs font-medium mb-1 block'>프리셋 한도</label>
                <Input
                  type='number'
                  value={presetVideoLimit}
                  min={1} max={10}
                  onChange={e => setPresetVideoLimit(Math.max(1, Math.min(10, parseInt(e.target.value) || 1)))}
                  className='h-8 text-sm'
                />
                <p className='text-muted-foreground text-[10px] mt-0.5'>같은 영상×프리셋 7일 내 ≤N</p>
              </div>
            </div>
          </div>}

          {/* Promo Keywords — edit only */}
          {mode === 'edit' && <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>홍보 키워드</label>
            <p className='text-muted-foreground text-xs mb-2'>댓글에 녹일 핵심 키워드를 입력하고 Enter</p>
            <div className='rounded-lg border border-border bg-background p-2 min-h-[42px]'>
              <div className='flex flex-wrap gap-1.5 mb-1'>
                {promoKeywords.map(kw => (
                  <span key={kw} className='hydra-tag hydra-tag-primary flex items-center gap-1'>
                    {kw}
                    <button
                      type='button'
                      onClick={() => removeKeyword(kw)}
                      className='hover:text-foreground'
                    >
                      <X className='h-3 w-3' />
                    </button>
                  </span>
                ))}
              </div>
              <Input
                value={keywordInput}
                onChange={(e) => setKeywordInput(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={addKeyword}
                placeholder={promoKeywords.length === 0 ? '키워드를 입력하고 Enter' : ''}
                className='border-0 p-0 h-7 shadow-none focus-visible:ring-0'
              />
            </div>
          </div>}
        </div>

        <DialogFooter className='flex !justify-between'>
          {mode === 'edit' ? (
            <Button
              variant='ghost'
              className={`text-destructive hover:text-destructive hover:bg-destructive/10 hydra-btn-press ${deleteConfirm ? 'bg-destructive/10' : ''}`}
              onClick={handleDelete}
              disabled={loading}
            >
              {deleteConfirm ? '정말 삭제할까요?' : '삭제'}
            </Button>
          ) : (
            <div />
          )}
          <div className='flex gap-2'>
            <Button variant='outline' onClick={() => onOpenChange(false)} className='hydra-btn-press'>
              취소
            </Button>
            <Button onClick={handleSubmit} disabled={loading || !name.trim()} className='hydra-btn-press'>
              {loading ? '저장 중...' : mode === 'create' ? '추가' : '저장'}
            </Button>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
