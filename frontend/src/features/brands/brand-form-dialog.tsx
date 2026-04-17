import { useEffect, useState, useCallback } from 'react'
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
  product_category: string | null
  core_message: string | null
  promo_keywords: string[] | null
  status: string
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
  const [category, setCategory] = useState('')
  const [coreMessage, setCoreMessage] = useState('')
  const [promoKeywords, setPromoKeywords] = useState<string[]>([])
  const [keywordInput, setKeywordInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [deleteConfirm, setDeleteConfirm] = useState(false)

  useEffect(() => {
    if (open) {
      if (mode === 'edit' && brand) {
        setName(brand.name || '')
        setCategory(brand.product_category || '')
        setCoreMessage(brand.core_message || '')
        setPromoKeywords(brand.promo_keywords || [])
      } else {
        setName('')
        setCategory('')
        setCoreMessage('')
        setPromoKeywords([])
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
    if (e.key === 'Enter') {
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
      await fetchApi(url, {
        method: 'POST',
        body: JSON.stringify({
          name: name.trim(),
          product_category: category.trim(),
          core_message: coreMessage.trim(),
          promo_keywords: promoKeywords,
        }),
      })
      onOpenChange(false)
      onSuccess()
    } catch {
      // error
    } finally {
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
      await fetchApi(`/brands/api/${brand.id}/update`, {
        method: 'POST',
        body: JSON.stringify({ status: 'deleted' }),
      })
      onOpenChange(false)
      onSuccess()
    } catch {
      // error
    } finally {
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
          {/* Name */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>브랜드 이름</label>
            <p className='text-muted-foreground text-xs mb-2'>홍보할 브랜드나 제품의 이름</p>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder='예: 모렉신'
            />
          </div>

          {/* Category */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>카테고리</label>
            <p className='text-muted-foreground text-xs mb-2'>어떤 종류의 제품인가요?</p>
            <Input
              value={category}
              onChange={(e) => setCategory(e.target.value)}
              placeholder='예: 건강기능식품, 화장품, IT서비스'
            />
          </div>

          {/* Core Message */}
          <div className='mb-5'>
            <label className='text-foreground text-sm font-medium mb-1.5'>핵심 메시지</label>
            <p className='text-muted-foreground text-xs mb-2'>댓글에서 자연스럽게 전달할 셀링 포인트</p>
            <Textarea
              value={coreMessage}
              onChange={(e) => setCoreMessage(e.target.value)}
              placeholder='예: 케라틴 직접 보충으로 모발 성장 촉진, 해외 논문 검증'
              rows={3}
            />
          </div>

          {/* Promo Keywords (Tag Input) */}
          <div className='mb-5'>
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
          </div>
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
