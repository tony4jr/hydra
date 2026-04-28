/**
 * Phase 1 — 키워드 폴링 토글 패널.
 *
 * 키워드별로 5min/30min/daily 폴링 활성화 + 부정 키워드 토글.
 * 5min 은 핫 키워드(트렌드 잡고 싶은 거)만 켜는 게 권장.
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Zap, Plus, X, Search } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import { fetchApi } from '@/lib/api'

interface Keyword {
  id: number
  text: string
  brand_id: number
  status: string
  source: string
  is_variant: boolean
  is_negative: boolean
  poll_5min: boolean
  poll_30min: boolean
  poll_daily: boolean
  total_videos_found: number
  parent_keyword_id: number | null
}

export function KeywordPollingPanel({ brandId }: { brandId: number | null }) {
  const [keywords, setKeywords] = useState<Keyword[]>([])
  const [loading, setLoading] = useState(false)
  const [newKw, setNewKw] = useState('')
  const [adding, setAdding] = useState(false)

  const load = () => {
    if (!brandId) { setKeywords([]); return }
    setLoading(true)
    fetchApi<Keyword[]>(`/keywords/api/list?brand_id=${brandId}`)
      .then(setKeywords)
      .catch(() => setKeywords([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [brandId])

  const updateField = async (kwId: number, field: string, value: boolean) => {
    try {
      await fetchApi(`/keywords/api/${kwId}/update-field`, {
        method: 'POST',
        body: JSON.stringify({ field, value }),
      })
      // 낙관적 갱신
      setKeywords(prev => prev.map(k => k.id === kwId ? { ...k, [field]: value } : k))
    } catch (e) {
      toast.error('업데이트 실패', { description: e instanceof Error ? e.message : String(e) })
      load()
    }
  }

  const addKeyword = async () => {
    const text = newKw.trim()
    if (!text || !brandId) return
    setAdding(true)
    try {
      await fetchApi('/keywords/api/create', {
        method: 'POST',
        body: JSON.stringify({ text, brand_id: brandId, status: 'active' }),
      })
      setNewKw('')
      load()
    } catch (e) {
      toast.error('키워드 추가 실패', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      setAdding(false)
    }
  }

  const removeKeyword = async (kwId: number) => {
    if (!confirm('키워드를 삭제하시겠어요? 연결된 영상은 유지됩니다.')) return
    try {
      await fetchApi(`/keywords/api/${kwId}/delete`, { method: 'POST' })
      load()
    } catch (e) {
      toast.error('삭제 실패', { description: e instanceof Error ? e.message : String(e) })
    }
  }

  if (!brandId) return null

  // 원본 vs 변형 분리
  const roots = keywords.filter(k => !k.is_variant)
  const variants = keywords.filter(k => k.is_variant)

  return (
    <div className='mb-5 rounded-xl border border-border bg-card p-5'>
      <div className='flex items-center justify-between mb-3 flex-wrap gap-2'>
        <div>
          <span className='text-foreground text-[14px] font-medium'>키워드 폴링</span>
          <span className='text-muted-foreground text-[11px] ml-2'>
            ⚡ 5분: 핫 키워드만 (quota 보호)
          </span>
        </div>
        <div className='flex gap-2'>
          <Input
            placeholder='새 키워드'
            value={newKw}
            onChange={e => setNewKw(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && !e.nativeEvent.isComposing) addKeyword() }}
            className='h-8 text-xs w-40'
          />
          <Button size='sm' className='h-8' onClick={addKeyword} disabled={adding || !newKw.trim()}>
            <Plus className='h-3.5 w-3.5 mr-1' /> 추가
          </Button>
        </div>
      </div>

      {loading ? (
        <Skeleton className='h-32 rounded-md' />
      ) : keywords.length === 0 ? (
        <div className='text-center py-8 text-muted-foreground text-[13px]'>
          키워드 없음. 위에서 추가하세요.
        </div>
      ) : (
        <>
          {/* 원본 키워드 (변형 X) */}
          <div className='space-y-1.5'>
            {roots.map(kw => (
              <KwRow key={kw.id} kw={kw} onUpdate={updateField} onRemove={removeKeyword} />
            ))}
          </div>

          {/* 변형 키워드 — 별도 표시 (압축) */}
          {variants.length > 0 && (
            <details className='mt-4 border-t border-border pt-3'>
              <summary className='text-muted-foreground text-[12px] cursor-pointer hover:text-foreground'>
                자동 생성 변형 ({variants.length}개)
              </summary>
              <div className='space-y-1 mt-2'>
                {variants.map(kw => (
                  <div key={kw.id} className='flex items-center justify-between text-[12px] px-2 py-1 rounded bg-muted/30'>
                    <span className='text-muted-foreground'>{kw.text}</span>
                    <span className='text-muted-foreground/60 text-[10px]'>
                      {kw.total_videos_found || 0}개 영상
                    </span>
                  </div>
                ))}
              </div>
            </details>
          )}
        </>
      )}
    </div>
  )
}


function KwRow({ kw, onUpdate, onRemove }: {
  kw: Keyword
  onUpdate: (id: number, field: string, value: boolean) => void
  onRemove: (id: number) => void
}) {
  return (
    <div className={`flex items-center gap-3 px-3 py-2 rounded-md border ${
      kw.is_negative ? 'border-red-500/30 bg-red-500/5' : 'border-border bg-background'
    }`}>
      <Search className='h-3.5 w-3.5 text-muted-foreground flex-shrink-0' />
      <span className={`text-[13px] flex-1 truncate ${kw.is_negative ? 'text-red-500' : 'text-foreground'}`}>
        {kw.text}
        {kw.is_negative && <span className='ml-1.5 text-[10px] text-red-500'>부정</span>}
      </span>
      <span className='text-muted-foreground text-[11px] mr-2'>
        {kw.total_videos_found || 0}개
      </span>

      {/* 폴링 토글 3종 */}
      <div className='flex items-center gap-2 text-[11px]'>
        <ToggleBtn
          label='5분' icon={Zap}
          active={kw.poll_5min}
          warn={kw.poll_5min}
          onClick={() => onUpdate(kw.id, 'poll_5min', !kw.poll_5min)}
          tooltip='핫 키워드만 (quota 보호)'
        />
        <ToggleBtn
          label='30분'
          active={kw.poll_30min}
          onClick={() => onUpdate(kw.id, 'poll_30min', !kw.poll_30min)}
        />
        <ToggleBtn
          label='일배치'
          active={kw.poll_daily}
          onClick={() => onUpdate(kw.id, 'poll_daily', !kw.poll_daily)}
        />
      </div>

      <div className='flex items-center gap-1 ml-2'>
        <Button
          size='sm' variant='ghost' className='h-6 px-2 text-[10px]'
          onClick={() => onUpdate(kw.id, 'is_negative', !kw.is_negative)}
          title={kw.is_negative ? '부정 키워드 해제' : '부정 키워드로 설정 (배제 룰)'}
        >
          {kw.is_negative ? '부정해제' : '부정'}
        </Button>
        <Button
          size='sm' variant='ghost' className='h-6 w-6 p-0'
          onClick={() => onRemove(kw.id)}
          title='삭제'
        >
          <X className='h-3 w-3 text-muted-foreground' />
        </Button>
      </div>
    </div>
  )
}


function ToggleBtn({ label, icon: Icon, active, warn, onClick, tooltip }: {
  label: string
  icon?: React.ElementType
  active: boolean
  warn?: boolean
  onClick: () => void
  tooltip?: string
}) {
  return (
    <button
      type='button'
      onClick={onClick}
      title={tooltip}
      className={`px-1.5 py-0.5 rounded border transition-colors ${
        active
          ? warn
            ? 'border-amber-500/50 bg-amber-500/15 text-amber-600 dark:text-amber-400'
            : 'border-emerald-500/50 bg-emerald-500/15 text-emerald-600 dark:text-emerald-400'
          : 'border-border bg-background text-muted-foreground/60 hover:text-muted-foreground'
      }`}
    >
      {Icon && <Icon className='h-3 w-3 inline mr-0.5' />}
      {label}
    </button>
  )
}
