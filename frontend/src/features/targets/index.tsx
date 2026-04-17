import { useEffect, useState } from 'react'
import { Download, Plus, RefreshCw } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent } from '@/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'

interface Brand {
  id: number
  name: string
}

interface Video {
  id: string
  title: string
  channel_title: string
  view_count: number
  comment_count: number
  status: string
  is_short: boolean
  collected_at: string
}

interface VideoListResponse {
  items: Video[]
  total: number
}

export default function TargetsPage() {
  const [videos, setVideos] = useState<Video[]>([])
  const [total, setTotal] = useState(0)
  const [brands, setBrands] = useState<Brand[]>([])
  const [initialBrandId, setInitialBrandId] = useState('')
  const [initialLoading, setInitialLoading] = useState(false)
  const [initialMsg, setInitialMsg] = useState('')

  useEffect(() => {
    fetchApi<VideoListResponse>('/videos/api/list')
      .then((data) => {
        setVideos(data.items || [])
        setTotal(data.total || 0)
      })
      .catch(() => {})
    fetchApi<Brand[]>('/brands/api/list')
      .then(setBrands)
      .catch(() => setBrands([]))
  }, [])

  const handleInitialCollect = async () => {
    if (!initialBrandId) return
    setInitialLoading(true)
    setInitialMsg('')
    try {
      await fetchApi(
        `/videos/api/collect/initial?brand_id=${initialBrandId}`,
        { method: 'POST' }
      )
      setInitialMsg('초기 수집 시작됨')
      // reload video list
      const data = await fetchApi<VideoListResponse>('/videos/api/list')
      setVideos(data.items || [])
      setTotal(data.total || 0)
    } catch {
      setInitialMsg('초기 수집 실패')
    } finally {
      setInitialLoading(false)
    }
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
        <div className='mb-2 flex flex-wrap items-center justify-between space-y-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>타겟</h2>
            <p className='text-muted-foreground'>
              타겟 영상 수집 + 관리 ({total}개)
            </p>
          </div>
          <div className='flex flex-wrap items-center gap-2'>
            <Select value={initialBrandId} onValueChange={setInitialBrandId}>
              <SelectTrigger className='w-40'>
                <SelectValue placeholder='브랜드 선택' />
              </SelectTrigger>
              <SelectContent>
                {brands.map((b) => (
                  <SelectItem key={b.id} value={String(b.id)}>
                    {b.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant='outline'
              disabled={!initialBrandId || initialLoading}
              onClick={handleInitialCollect}
            >
              <Download className='mr-2 h-4 w-4' />
              {initialLoading ? '수집 중...' : '초기 수집'}
            </Button>
            <Button variant='outline'>
              <RefreshCw className='mr-2 h-4 w-4' /> 정기 수집
            </Button>
            <Button>
              <Plus className='mr-2 h-4 w-4' /> URL 추가
            </Button>
            {initialMsg && (
              <span className='text-sm text-muted-foreground'>
                {initialMsg}
              </span>
            )}
          </div>
        </div>

        <Card>
          <CardContent className='p-0'>
            <div className='overflow-auto'>
              <table className='w-full text-sm'>
                <thead>
                  <tr className='border-b bg-muted/50'>
                    <th className='p-3 text-left font-medium'>제목</th>
                    <th className='p-3 text-left font-medium'>채널</th>
                    <th className='p-3 text-right font-medium'>조회수</th>
                    <th className='p-3 text-right font-medium'>댓글수</th>
                    <th className='p-3 text-center font-medium'>유형</th>
                    <th className='p-3 text-center font-medium'>상태</th>
                  </tr>
                </thead>
                <tbody>
                  {videos.length === 0 ? (
                    <tr>
                      <td
                        colSpan={6}
                        className='p-10 text-center text-muted-foreground'
                      >
                        타겟 영상이 없습니다. 서버 연결 후 표시됩니다.
                      </td>
                    </tr>
                  ) : (
                    videos.map((v) => (
                      <tr
                        key={v.id}
                        className='cursor-pointer border-b hover:bg-muted/50'
                      >
                        <td className='max-w-[300px] truncate p-3'>
                          {v.title}
                        </td>
                        <td className='p-3 text-muted-foreground'>
                          {v.channel_title}
                        </td>
                        <td className='p-3 text-right'>
                          {v.view_count?.toLocaleString()}
                        </td>
                        <td className='p-3 text-right'>
                          {v.comment_count?.toLocaleString()}
                        </td>
                        <td className='p-3 text-center'>
                          <Badge variant='outline'>
                            {v.is_short ? '숏폼' : '롱폼'}
                          </Badge>
                        </td>
                        <td className='p-3 text-center'>
                          <Badge
                            variant={
                              v.status === 'available'
                                ? 'default'
                                : 'secondary'
                            }
                          >
                            {v.status}
                          </Badge>
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </Main>
    </>
  )
}
