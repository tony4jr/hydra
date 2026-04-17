import { useEffect, useState } from 'react'
import { Plus, ChevronLeft, ChevronRight } from 'lucide-react'
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

  const loadVideos = () => {
    setLoading(true)
    fetchApi<{ items: Video[]; total: number }>('/videos/api/list')
      .then(data => { setVideos(data.items || []); setTotal(data.total || 0) })
      .catch(() => {})
      .finally(() => setLoading(false))
  }

  useEffect(() => { loadVideos() }, [])

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
    } catch { /* error */ }
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
              <h2 className='text-[22px] font-bold'>타겟</h2>
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
