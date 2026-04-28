/**
 * Phase 1 — TargetCollectionConfig 편집 패널.
 *
 * embedding reference text + 임계값들 운영자가 직접 조정.
 * 가장 중요: embedding_reference_text — Haiku 가 이걸로 영상 관련도 판단.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Save, AlertCircle } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Textarea } from '@/components/ui/textarea'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchApi } from '@/lib/api'

interface TargetConfig {
  target_id: number
  embedding_reference_text: string
  embedding_threshold: number
  l1_threshold_score: number
  l1_max_pool_size: number
  l2_max_age_hours: number
  l3_views_per_hour_threshold: number
  hard_block_min_video_seconds: number
  exclude_kids_category: boolean
  exclude_live_streaming: boolean
}

export function TargetConfigPanel({ brandId }: { brandId: number | null }) {
  const [config, setConfig] = useState<TargetConfig | null>(null)
  const [loading, setLoading] = useState(false)
  const [saving, setSaving] = useState(false)
  const [open, setOpen] = useState(false)

  // 로컬 편집 상태
  const [refText, setRefText] = useState('')
  const [embTh, setEmbTh] = useState('0.65')
  const [l1Th, setL1Th] = useState('70')
  const [l3Vph, setL3Vph] = useState('1000')
  const [minSec, setMinSec] = useState('30')

  useEffect(() => {
    if (!brandId) { setConfig(null); return }
    setLoading(true)
    fetchApi<TargetConfig>(`/api/admin/collection/config/${brandId}`)
      .then(c => {
        setConfig(c)
        setRefText(c.embedding_reference_text || '')
        setEmbTh(String(c.embedding_threshold ?? 0.65))
        setL1Th(String(c.l1_threshold_score ?? 70))
        setL3Vph(String(c.l3_views_per_hour_threshold ?? 1000))
        setMinSec(String(c.hard_block_min_video_seconds ?? 30))
      })
      .catch(() => setConfig(null))
      .finally(() => setLoading(false))
  }, [brandId])

  if (!brandId) return null
  if (loading || !config) return <Skeleton className='h-32 mb-5 rounded-xl' />

  const handleSave = async () => {
    setSaving(true)
    try {
      await fetchApi(`/api/admin/collection/config/${brandId}`, {
        method: 'PATCH',
        body: JSON.stringify({
          embedding_reference_text: refText.trim(),
          embedding_threshold: parseFloat(embTh),
          l1_threshold_score: parseFloat(l1Th),
          l3_views_per_hour_threshold: parseInt(l3Vph),
          hard_block_min_video_seconds: parseInt(minSec),
        }),
      })
      toast.success('분류 설정 저장됨')
    } catch (e) {
      toast.error('저장 실패', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      setSaving(false)
    }
  }

  const isMissingRef = !refText || refText.trim().length < 20
  const previewRef = refText ? `${refText.slice(0, 80)}${refText.length > 80 ? '…' : ''}` : '(비어있음)'

  return (
    <div className={`mb-5 rounded-xl border p-5 ${
      isMissingRef ? 'border-amber-500/40 bg-amber-500/5' : 'border-border bg-card'
    }`}>
      <div className='flex items-center justify-between mb-2 cursor-pointer' onClick={() => setOpen(o => !o)}>
        <div className='flex items-center gap-2'>
          <span className='text-foreground text-[14px] font-medium'>분류 설정 (Phase 1)</span>
          {isMissingRef ? (
            <span className='inline-flex items-center gap-1 text-amber-600 dark:text-amber-400 text-[11px]'>
              <AlertCircle className='h-3 w-3' /> reference 비어있음 — 임베딩 분류 작동 안 함
            </span>
          ) : (
            <span className='text-muted-foreground text-[11px]'>
              {previewRef}
            </span>
          )}
        </div>
        <span className='text-muted-foreground text-[12px]'>{open ? '접기' : '펼치기'}</span>
      </div>

      {open && (
        <div className='mt-4 space-y-4'>
          {/* Reference text — 가장 중요 */}
          <div>
            <label className='text-foreground text-xs font-medium block mb-1'>
              임베딩 Reference Text
              <span className='text-muted-foreground ml-2'>(이 시장의 정의 — Haiku 가 이걸로 영상 관련도 판단)</span>
            </label>
            <Textarea
              value={refText}
              onChange={e => setRefText(e.target.value)}
              rows={4}
              placeholder='예: 탈모, 머리숱, 두피 건강, 모발 관리, 비오틴, 영양제, 두피 케어, 탈모 초기 증상, M자 탈모, 정수리 탈모, 산후 탈모, 스트레스 탈모, 유전 탈모...'
              className='font-mono text-[12px]'
            />
            <p className='text-muted-foreground text-[11px] mt-1'>
              200자 정도, 콤마로 구분. 운영 시작 전 반드시 입력.
            </p>
          </div>

          {/* 임계값들 */}
          <div className='grid grid-cols-2 lg:grid-cols-4 gap-3'>
            <div>
              <label className='text-foreground text-xs font-medium mb-1 block'>
                관련도 임계값
                <span className='text-muted-foreground ml-1'>(0~1)</span>
              </label>
              <Input
                type='number' step='0.05' min='0' max='1'
                value={embTh}
                onChange={e => setEmbTh(e.target.value)}
                className='h-8 text-sm'
              />
              <p className='text-muted-foreground text-[10px] mt-0.5'>이하면 차단. 권장 0.65</p>
            </div>
            <div>
              <label className='text-foreground text-xs font-medium mb-1 block'>
                L1 점수 임계값
                <span className='text-muted-foreground ml-1'>(0~100)</span>
              </label>
              <Input
                type='number' min='0' max='100'
                value={l1Th}
                onChange={e => setL1Th(e.target.value)}
                className='h-8 text-sm'
              />
              <p className='text-muted-foreground text-[10px] mt-0.5'>이상이면 L1. 권장 70</p>
            </div>
            <div>
              <label className='text-foreground text-xs font-medium mb-1 block'>
                L3 트렌딩 임계
                <span className='text-muted-foreground ml-1'>(시간당 조회수)</span>
              </label>
              <Input
                type='number' min='0'
                value={l3Vph}
                onChange={e => setL3Vph(e.target.value)}
                className='h-8 text-sm'
              />
              <p className='text-muted-foreground text-[10px] mt-0.5'>이상이면 L3. 권장 1000</p>
            </div>
            <div>
              <label className='text-foreground text-xs font-medium mb-1 block'>
                최소 영상 길이
                <span className='text-muted-foreground ml-1'>(초)</span>
              </label>
              <Input
                type='number' min='0' max='600'
                value={minSec}
                onChange={e => setMinSec(e.target.value)}
                className='h-8 text-sm'
              />
              <p className='text-muted-foreground text-[10px] mt-0.5'>이하면 차단. 권장 30s</p>
            </div>
          </div>

          <div className='flex justify-end'>
            <Button onClick={handleSave} disabled={saving} className='hydra-btn-press'>
              <Save className='h-3.5 w-3.5 mr-1.5' />
              {saving ? '저장 중…' : '저장'}
            </Button>
          </div>
        </div>
      )}
    </div>
  )
}
