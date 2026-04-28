/**
 * Phase 1 — 영상 풀 패널.
 *
 * Brand(=Target)별 영상 풀 조회 + state/L tier/phase 필터 + 수동 토글 UI.
 * LLM/임베딩 오분류 즉시 대응 (운영 첫날 필수).
 */
import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Check, X, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { fetchApi } from '@/lib/api'

interface PoolVideo {
  id: string
  url: string
  title: string
  channel_title: string
  view_count: number
  duration_sec: number | null
  is_short: boolean
  state: string
  blacklist_reason: string | null
  l_tier: string | null
  lifecycle_phase: number | null
  embedding_score: number | null
  popularity_score: number | null
  top_comment_likes: number
  collected_at: string | null
  next_revisit_at: string | null
}

const stateLabels: Record<string, string> = {
  pending: '대기', active: '활성', blacklisted: '차단', paused: '일시정지', completed: '완료',
}
const stateTag: Record<string, string> = {
  active: 'hydra-tag-success', pending: 'hydra-tag-muted', blacklisted: 'hydra-tag-danger',
  paused: 'hydra-tag-warning', completed: 'hydra-tag-blue',
}
const tierColor: Record<string, string> = {
  L1: 'text-emerald-500', L2: 'text-blue-500', L3: 'text-orange-500', L4: 'text-muted-foreground',
}

export function VideoPoolPanel({ brandId }: { brandId: number | null }) {
  const [videos, setVideos] = useState<PoolVideo[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(false)
  const [stateFilter, setStateFilter] = useState<string>('all')
  const [tierFilter, setTierFilter] = useState<string>('all')

  const load = () => {
    if (!brandId) { setVideos([]); setTotal(0); return }
    setLoading(true)
    const params = new URLSearchParams({ target_id: String(brandId), limit: '100' })
    if (stateFilter !== 'all') params.set('state', stateFilter)
    if (tierFilter !== 'all') params.set('l_tier', tierFilter)

    fetchApi<{ total: number; items: PoolVideo[] }>(`/api/admin/video-pool/list?${params.toString()}`)
      .then(d => { setVideos(d.items || []); setTotal(d.total || 0) })
      .catch(() => { setVideos([]); setTotal(0) })
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [brandId, stateFilter, tierFilter])

  const handleToggle = async (videoId: string, newState: 'active' | 'blacklisted') => {
    try {
      await fetchApi(`/api/admin/video-pool/${videoId}/toggle-state`, {
        method: 'POST',
        body: JSON.stringify({ state: newState, reason: newState === 'blacklisted' ? 'manual' : null }),
      })
      toast.success(`${stateLabels[newState]} 처리됨`)
      load()
    } catch (e) {
      toast.error('상태 변경 실패', { description: e instanceof Error ? e.message : String(e) })
    }
  }

  const handleReclassify = async (videoId: string) => {
    if (!brandId) return
    try {
      await fetchApi(`/api/admin/video-pool/${videoId}/reclassify?target_id=${brandId}`, {
        method: 'POST',
      })
      toast.success('재분류 완료')
      load()
    } catch (e) {
      toast.error('재분류 실패', { description: e instanceof Error ? e.message : String(e) })
    }
  }

  if (!brandId) return null

  return (
    <div className='mb-5 rounded-xl border border-border bg-card p-5'>
      <div className='flex items-center justify-between mb-3 flex-wrap gap-2'>
        <div className='flex items-center gap-3'>
          <span className='text-foreground text-[14px] font-medium'>영상 풀 (Phase 1)</span>
          <span className='text-muted-foreground text-[12px]'>{total.toLocaleString()}개</span>
        </div>
        <div className='flex gap-2 items-center'>
          <Select value={stateFilter} onValueChange={setStateFilter}>
            <SelectTrigger className='w-32 h-8 text-xs'>
              <SelectValue placeholder='상태' />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>전체</SelectItem>
              <SelectItem value='active'>활성</SelectItem>
              <SelectItem value='pending'>대기</SelectItem>
              <SelectItem value='blacklisted'>차단</SelectItem>
              <SelectItem value='paused'>일시정지</SelectItem>
              <SelectItem value='completed'>완료</SelectItem>
            </SelectContent>
          </Select>
          <Select value={tierFilter} onValueChange={setTierFilter}>
            <SelectTrigger className='w-24 h-8 text-xs'>
              <SelectValue placeholder='티어' />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value='all'>모든 티어</SelectItem>
              <SelectItem value='L1'>L1 (영구 자산)</SelectItem>
              <SelectItem value='L2'>L2 (신규)</SelectItem>
              <SelectItem value='L3'>L3 (트렌딩)</SelectItem>
              <SelectItem value='L4'>L4 (롱테일)</SelectItem>
            </SelectContent>
          </Select>
          <Button size='sm' variant='outline' className='h-8' onClick={load}>
            <RefreshCw className='h-3.5 w-3.5' />
          </Button>
        </div>
      </div>

      {loading ? (
        <Skeleton className='h-48 rounded-md' />
      ) : videos.length === 0 ? (
        <div className='text-center py-12 text-muted-foreground text-[13px]'>
          {stateFilter !== 'all' || tierFilter !== 'all'
            ? '필터 결과 없음 — 다른 필터 시도'
            : '영상 풀이 비어있어요. 깊은 수집을 시작하세요.'}
        </div>
      ) : (
        <div className='overflow-x-auto'>
          <table className='w-full text-[12px]'>
            <thead>
              <tr className='border-b border-border bg-muted/30 text-muted-foreground'>
                <th className='p-2 text-left font-medium'>제목</th>
                <th className='p-2 text-center font-medium w-12'>티어</th>
                <th className='p-2 text-center font-medium w-12'>Phase</th>
                <th className='p-2 text-right font-medium w-20'>조회수</th>
                <th className='p-2 text-right font-medium w-20'>임베딩</th>
                <th className='p-2 text-right font-medium w-20'>1등 좋아요</th>
                <th className='p-2 text-center font-medium w-20'>상태</th>
                <th className='p-2 text-center font-medium w-32'>액션</th>
              </tr>
            </thead>
            <tbody>
              {videos.map(v => (
                <tr key={v.id} className='border-b border-border/30 hover:bg-muted/20'>
                  <td className='p-2 max-w-[280px]'>
                    <a
                      href={v.url}
                      target='_blank'
                      rel='noopener noreferrer'
                      className='text-foreground hover:text-primary truncate block'
                      title={v.title}
                    >
                      {v.title || v.id}
                    </a>
                    <div className='text-muted-foreground text-[10px] truncate'>{v.channel_title}</div>
                  </td>
                  <td className={`p-2 text-center font-bold ${tierColor[v.l_tier || ''] || ''}`}>
                    {v.l_tier || '-'}
                  </td>
                  <td className='p-2 text-center text-muted-foreground'>
                    {v.lifecycle_phase || '-'}
                  </td>
                  <td className='p-2 text-right'>{v.view_count?.toLocaleString() || '-'}</td>
                  <td className='p-2 text-right'>
                    {v.embedding_score != null ? v.embedding_score.toFixed(3) : '-'}
                  </td>
                  <td className='p-2 text-right'>
                    {v.top_comment_likes?.toLocaleString() || '-'}
                  </td>
                  <td className='p-2 text-center'>
                    <span className={`hydra-tag ${stateTag[v.state] || 'hydra-tag-muted'}`} title={v.blacklist_reason || ''}>
                      {stateLabels[v.state] || v.state}
                    </span>
                  </td>
                  <td className='p-2 text-center'>
                    <div className='flex justify-center gap-1'>
                      {v.state === 'blacklisted' ? (
                        <Button
                          size='sm' variant='ghost'
                          className='h-6 w-6 p-0'
                          title='활성으로 풀어주기'
                          onClick={() => handleToggle(v.id, 'active')}
                        >
                          <Check className='h-3.5 w-3.5 text-emerald-500' />
                        </Button>
                      ) : (
                        <Button
                          size='sm' variant='ghost'
                          className='h-6 w-6 p-0'
                          title='차단 (오분류 등)'
                          onClick={() => handleToggle(v.id, 'blacklisted')}
                        >
                          <X className='h-3.5 w-3.5 text-red-500' />
                        </Button>
                      )}
                      <Button
                        size='sm' variant='ghost'
                        className='h-6 w-6 p-0'
                        title='재분류'
                        onClick={() => handleReclassify(v.id)}
                      >
                        <RefreshCw className='h-3.5 w-3.5 text-muted-foreground' />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
