import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Plus, ChevronLeft, ChevronRight, Download, RefreshCw } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from '@/components/ui/dialog'
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { useCountUp } from '@/hooks/use-count-up'
import { VideoPoolPanel } from './video-pool-panel'
import { KeywordPollingPanel } from './keyword-polling-panel'
import { TargetConfigPanel } from './target-config-panel'

interface BrandRow {
  id: number
  name: string
}

interface CollectionStatus {
  brand_id: number
  brand_name: string
  collection_depth: string
  longtail_count: number
  preset_video_limit: number
  stats: {
    total: number
    fresh: number
    popular_backlog: number
    worked: number
    untouched: number
    progress_pct: number
  }
  keywords: Array<{
    keyword: string
    videos_direct: number
    variant_count: number
    total_videos_found: number
  }>
  in_progress: {
    running?: boolean
    started_at?: string
    finished_at?: string
    result?: { keywords_processed: number; videos_added: number; variants_created: number }
    error?: string
  }
}

interface Video {
  id: string
  title: string
  channel_title: string
  view_count: number
  comment_count: number
  status: string
  is_short: boolean
  campaign_name?: string
  collected_at: string
}

const statusLabels: Record<string, string> = {
  available: '대기', completed: '완료', in_progress: '진행중',
}
const statusTag: Record<string, string> = {
  available: 'hydra-tag-muted', completed: 'hydra-tag-success', in_progress: 'hydra-tag-primary',
}

function StatCard({ label, value }: { label: string; value: number | string }) {
  const isNum = typeof value === 'number'
  const animated = useCountUp(isNum ? value : 0)
  return (
    <div className='bg-card rounded-xl border border-border p-4'>
      <span className='text-muted-foreground text-[12px]'>{label}</span>
      <div className='text-[28px] font-bold'>
        {isNum ? animated : value}
      </div>
    </div>
  )
}

export default function TargetsPage() {
  const [videos, setVideos] = useState<Video[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [page, setPage] = useState(1)
  const [addOpen, setAddOpen] = useState(false)
  const [urlInput, setUrlInput] = useState('')
  const [adding, setAdding] = useState(false)
  const [campaignFilter, setCampaignFilter] = useState('all')
  const perPage = 20

  // Brand 선택 + 수집 상태
  const [brands, setBrands] = useState<BrandRow[]>([])
  const [selectedBrand, setSelectedBrand] = useState<number | null>(null)
  const [status, setStatus] = useState<CollectionStatus | null>(null)
  const [collectStarting, setCollectStarting] = useState(false)
  const [dailyTriggerLoading, setDailyTriggerLoading] = useState(false)

  const loadVideos = () => {
    setLoading(true)
    fetchApi<{ items: Video[]; total: number }>('/videos/api/list')
      .then(data => { setVideos(data.items || []); setTotal(data.total || 0) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadVideos() }, [])

  // Brand 목록 로드
  useEffect(() => {
    fetchApi<{ items: BrandRow[] }>('/brands/api/list')
      .then(d => {
        const items = d.items || []
        setBrands(items)
        if (items.length > 0) setSelectedBrand(items[0].id)
      })
      .catch(() => {})
  }, [])

  // 선택된 brand 의 수집 상태 폴링
  useEffect(() => {
    if (!selectedBrand) return
    const load = () => {
      fetchApi<CollectionStatus>(`/api/admin/collection/status/${selectedBrand}`)
        .then(setStatus)
        .catch(() => setStatus(null))
    }
    load()
    const id = setInterval(load, 5000)
    return () => clearInterval(id)
  }, [selectedBrand])

  const handleStartCollection = async () => {
    if (!selectedBrand) return
    setCollectStarting(true)
    try {
      await fetchApi(`/api/admin/collection/start/${selectedBrand}`, { method: 'POST' })
      toast.success('수집 시작', { description: '백그라운드에서 진행. 풀이 채워지는 중.' })
    } catch (e) {
      toast.error('수집 시작 실패', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      setCollectStarting(false)
    }
  }

  const handleDailyTrigger = async () => {
    if (!selectedBrand) return
    setDailyTriggerLoading(true)
    try {
      const r = await fetchApi<{ videos_added: number }>(`/api/admin/collection/daily-new/${selectedBrand}`, { method: 'POST' })
      toast.success(`신규 ${r.videos_added}개 추가됨`)
    } catch (e) {
      toast.error('실패', { description: e instanceof Error ? e.message : String(e) })
    } finally {
      setDailyTriggerLoading(false)
    }
  }

  const completed = videos.filter(v => v.status === 'completed').length
  const pending = videos.filter(v => v.status === 'available').length
  const lastCollect = videos.length > 0 ? videos[0]?.collected_at : null

  const filtered = campaignFilter === 'all' ? videos : videos.filter(v => v.campaign_name === campaignFilter)
  const totalPages = Math.ceil(filtered.length / perPage)
  const pagedVideos = filtered.slice((page - 1) * perPage, page * perPage)

  const campaigns = [...new Set(videos.filter(v => v.campaign_name).map(v => v.campaign_name!))]

  const handleAddUrl = async () => {
    const url = urlInput.trim()
    if (!url) return
    setAdding(true)
    try {
      await fetchApi('/videos/api/add-manual', {
        method: 'POST',
        body: JSON.stringify({ url }),
      })
      setUrlInput('')
      setAddOpen(false)
      loadVideos()
    } catch (e) { toast.error("오류", { description: e instanceof Error ? e.message : String(e) }) }
    finally { setAdding(false) }
  }

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div >
          <div className='mb-5 flex flex-wrap items-center justify-between gap-2'>
            <div>
              <h2 className='text-[22px] font-bold hydra-page-h'>타겟</h2>
              <p className='text-muted-foreground text-[13px]'>수집된 영상 목록 확인 및 관리</p>
            </div>
            <div className='flex gap-2'>
              {campaigns.length > 0 && (
                <Select value={campaignFilter} onValueChange={v => { setCampaignFilter(v); setPage(1) }}>
                  <SelectTrigger className='w-40'>
                    <SelectValue placeholder='캠페인 필터' />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value='all'>전체</SelectItem>
                    {campaigns.map(c => <SelectItem key={c} value={c}>{c}</SelectItem>)}
                  </SelectContent>
                </Select>
              )}
              <Button onClick={() => setAddOpen(true)} className='hydra-btn-press'>
                <Plus className='mr-2 h-4 w-4' /> URL 추가
              </Button>
            </div>
          </div>

          {/* Brand 선택 + 수집 상태 패널 */}
          {brands.length > 0 && (
            <div className='mb-5 rounded-xl border border-border bg-card p-5'>
              <div className='flex items-center justify-between mb-4 flex-wrap gap-2'>
                <div className='flex items-center gap-3'>
                  <span className='text-foreground text-[14px] font-medium'>브랜드</span>
                  <Select
                    value={selectedBrand?.toString() || ''}
                    onValueChange={(v) => setSelectedBrand(parseInt(v))}
                  >
                    <SelectTrigger className='w-48'>
                      <SelectValue placeholder='브랜드 선택' />
                    </SelectTrigger>
                    <SelectContent>
                      {brands.map(b => (
                        <SelectItem key={b.id} value={b.id.toString()}>{b.name}</SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  {status && (
                    <span className='text-muted-foreground text-[12px]'>
                      깊이: <b className='text-foreground'>{status.collection_depth}</b> ·
                      변형: <b className='text-foreground'>{status.longtail_count}</b> ·
                      프리셋한도: <b className='text-foreground'>{status.preset_video_limit}</b>
                    </span>
                  )}
                </div>
                <div className='flex gap-2'>
                  <Button
                    size='sm' variant='outline' className='hydra-btn-press'
                    onClick={handleDailyTrigger}
                    disabled={dailyTriggerLoading || !selectedBrand}
                  >
                    <RefreshCw className='mr-1.5 h-3.5 w-3.5' />
                    {dailyTriggerLoading ? '...' : '매일 신규 갱신'}
                  </Button>
                  <Button
                    size='sm' className='hydra-btn-press'
                    onClick={handleStartCollection}
                    disabled={collectStarting || !selectedBrand || status?.in_progress?.running}
                  >
                    <Download className='mr-1.5 h-3.5 w-3.5' />
                    {status?.in_progress?.running ? '수집 중…' :
                     collectStarting ? '시작 중…' : '깊은 수집 시작'}
                  </Button>
                </div>
              </div>

              {status && (
                <>
                  <div className='grid grid-cols-2 lg:grid-cols-5 gap-3 mb-4'>
                    <div>
                      <div className='text-muted-foreground text-[11px]'>전체 풀</div>
                      <div className='text-[22px] font-bold'>{status.stats.total.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className='text-muted-foreground text-[11px]'>신규 (7일내)</div>
                      <div className='text-[22px] font-bold text-blue-500'>{status.stats.fresh.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className='text-muted-foreground text-[11px]'>인기 백로그</div>
                      <div className='text-[22px] font-bold text-orange-500'>{status.stats.popular_backlog.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className='text-muted-foreground text-[11px]'>작업 완료</div>
                      <div className='text-[22px] font-bold text-emerald-500'>{status.stats.worked.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className='text-muted-foreground text-[11px]'>진행률</div>
                      <div className='text-[22px] font-bold'>{status.stats.progress_pct}%</div>
                    </div>
                  </div>

                  {/* 진행 바 */}
                  <div className='h-1.5 bg-muted rounded-full overflow-hidden mb-4'>
                    <div
                      className='h-full bg-gradient-to-r from-emerald-400 to-emerald-600 transition-all'
                      style={{ width: `${status.stats.progress_pct}%` }}
                    />
                  </div>

                  {/* 키워드 breakdown */}
                  {status.keywords.length > 0 && (
                    <div className='space-y-1'>
                      <div className='text-muted-foreground text-[11px] font-medium'>키워드별 풀</div>
                      <div className='grid grid-cols-2 lg:grid-cols-3 gap-1.5'>
                        {status.keywords.map(k => (
                          <div key={k.keyword} className='text-[12px] flex justify-between rounded-md bg-muted/30 px-2 py-1'>
                            <span className='font-medium truncate mr-2'>{k.keyword}</span>
                            <span className='text-muted-foreground whitespace-nowrap'>
                              {k.total_videos_found}개 · 변형 {k.variant_count}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* in-progress 세부 */}
                  {status.in_progress?.running && (
                    <div className='mt-3 rounded-md bg-blue-500/10 border border-blue-500/30 p-2.5 text-[12px]'>
                      <span className='font-medium text-blue-600 dark:text-blue-400'>⏳ 깊은 수집 진행 중</span>
                      <span className='text-muted-foreground ml-2'>
                        시작: {status.in_progress.started_at && new Date(status.in_progress.started_at).toLocaleString('ko')}
                      </span>
                    </div>
                  )}
                  {status.in_progress?.error && (
                    <div className='mt-3 rounded-md bg-red-500/10 border border-red-500/30 p-2.5 text-[12px]'>
                      <span className='text-red-600 dark:text-red-400'>❌ 에러: {status.in_progress.error}</span>
                    </div>
                  )}
                  {status.in_progress?.result && !status.in_progress.running && (
                    <div className='mt-3 rounded-md bg-emerald-500/10 border border-emerald-500/30 p-2.5 text-[12px]'>
                      <span className='text-emerald-600 dark:text-emerald-400'>
                        ✅ 마지막 수집: 키워드 {status.in_progress.result.keywords_processed}개 처리, 영상 {status.in_progress.result.videos_added}개 추가, 변형 {status.in_progress.result.variants_created}개 생성
                      </span>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {/* Phase 1: 분류 설정 (embedding reference + 임계값) */}
          <TargetConfigPanel brandId={selectedBrand} />

          {/* Phase 1: 키워드 폴링 토글 */}
          <KeywordPollingPanel brandId={selectedBrand} />

          {/* Phase 1: 영상 풀 패널 (state/L tier 필터 + 수동 토글) */}
          <VideoPoolPanel brandId={selectedBrand} />

          {/* Stat cards */}
          {loading ? (
            <div className='grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5'>
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className='h-24 rounded-xl' />)}
            </div>
          ) : (
            <div className='grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5'>
              <StatCard label='전체 영상' value={total} />
              <StatCard label='완료' value={completed} />
              <StatCard label='대기' value={pending} />
              <StatCard
                label='마지막 수집'
                value={lastCollect ? new Date(lastCollect).toLocaleDateString('ko') : '-'}
              />
            </div>
          )}

          {/* Video table */}
          {loading ? (
            <Skeleton className='h-64 rounded-xl' />
          ) : pagedVideos.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px] mb-1'>타겟 영상이 없어요</p>
              <p className='text-muted-foreground/60 text-[12px] mb-4'>캠페인의 타겟 키워드로 영상이 자동 수집됩니다</p>
              <Button onClick={() => setAddOpen(true)} variant='outline' className='hydra-btn-press'>
                <Plus className='mr-2 h-4 w-4' /> URL 수동 추가
              </Button>
            </div>
          ) : (
            <>
              <div className='bg-card border border-border rounded-xl overflow-hidden'>
                <div className='overflow-x-auto'>
                  <table className='w-full text-sm'>
                    <thead>
                      <tr className='border-b border-border bg-muted/30'>
                        <th className='p-3 text-left font-medium text-[12px] text-muted-foreground'>제목</th>
                        <th className='p-3 text-left font-medium text-[12px] text-muted-foreground'>채널</th>
                        <th className='p-3 text-right font-medium text-[12px] text-muted-foreground'>조회수</th>
                        <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>캠페인</th>
                        <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>상태</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pagedVideos.map(v => (
                        <tr key={v.id} className='border-b border-border/30 hydra-row-hover'>
                          <td className='p-3 max-w-[300px]'>
                            <span className='text-foreground text-[13px] truncate block'>{v.title}</span>
                          </td>
                          <td className='p-3 text-muted-foreground text-[13px]'>{v.channel_title}</td>
                          <td className='p-3 text-right text-[13px]'>{v.view_count?.toLocaleString()}</td>
                          <td className='p-3 text-center text-muted-foreground text-[12px]'>{v.campaign_name || '-'}</td>
                          <td className='p-3 text-center'>
                            <span className={`hydra-tag ${statusTag[v.status] || 'hydra-tag-muted'}`}>
                              {statusLabels[v.status] || v.status}
                            </span>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {totalPages > 1 && (
                <div className='flex items-center justify-center gap-2 mt-4'>
                  <Button variant='outline' size='icon' className='h-8 w-8' disabled={page <= 1} onClick={() => setPage(p => p - 1)}>
                    <ChevronLeft className='h-4 w-4' />
                  </Button>
                  <span className='text-muted-foreground text-[13px]'>{page} / {totalPages}</span>
                  <Button variant='outline' size='icon' className='h-8 w-8' disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}>
                    <ChevronRight className='h-4 w-4' />
                  </Button>
                </div>
              )}
            </>
          )}
        </div>
      </Main>

      {/* URL Add Dialog */}
      <Dialog open={addOpen} onOpenChange={setAddOpen}>
        <DialogContent className='sm:max-w-sm'>
          <DialogHeader>
            <DialogTitle>영상 URL 추가</DialogTitle>
          </DialogHeader>
          <div className='mb-5 py-2'>
            <label className='text-foreground text-sm font-medium mb-1.5'>YouTube URL</label>
            <p className='text-muted-foreground text-xs mb-2'>작업할 영상의 URL을 입력하세요</p>
            <Input
              value={urlInput}
              onChange={e => setUrlInput(e.target.value)}
              placeholder='https://youtube.com/watch?v=...'
              onKeyDown={e => { if (e.key === 'Enter') handleAddUrl() }}
            />
          </div>
          <DialogFooter>
            <Button variant='outline' onClick={() => setAddOpen(false)} className='hydra-btn-press'>취소</Button>
            <Button onClick={handleAddUrl} disabled={adding || !urlInput.trim()} className='hydra-btn-press'>
              {adding ? '추가 중...' : '추가'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}
