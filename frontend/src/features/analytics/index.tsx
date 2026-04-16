import { useEffect, useState } from 'react'
import {
  MessageSquare,
  ThumbsUp,
  TrendingUp,
  Ghost,
  CalendarDays,
  BarChart3,
} from 'lucide-react'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'

interface AnalyticsStats {
  total_comments: number
  total_likes: number
  success_rate: number
  ghost_rate: number
}

export default function AnalyticsPage() {
  const [stats, setStats] = useState<AnalyticsStats>({
    total_comments: 0,
    total_likes: 0,
    success_rate: 0,
    ghost_rate: 0,
  })

  useEffect(() => {
    fetchApi<AnalyticsStats>('/analytics/api/stats')
      .then(setStats)
      .catch(() => {})
  }, [])

  const statCards = [
    {
      title: '총 댓글',
      value: stats.total_comments.toLocaleString(),
      icon: MessageSquare,
      color: 'text-blue-500',
    },
    {
      title: '총 좋아요',
      value: stats.total_likes.toLocaleString(),
      icon: ThumbsUp,
      color: 'text-green-500',
    },
    {
      title: '성공률',
      value: `${stats.success_rate}%`,
      icon: TrendingUp,
      color: 'text-emerald-500',
    },
    {
      title: '고스트율',
      value: `${stats.ghost_rate}%`,
      icon: Ghost,
      color: 'text-orange-500',
    },
  ]

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
            <h2 className='text-2xl font-bold tracking-tight'>분석</h2>
            <p className='text-muted-foreground'>
              댓글 성과, 계정 건강도, 기간별 추세
            </p>
          </div>
        </div>

        <Tabs defaultValue='dashboard'>
          <TabsList>
            <TabsTrigger value='dashboard'>
              <BarChart3 className='mr-2 h-4 w-4' />
              대시보드
            </TabsTrigger>
            <TabsTrigger value='calendar'>
              <CalendarDays className='mr-2 h-4 w-4' />
              캘린더
            </TabsTrigger>
            <TabsTrigger value='detail'>상세</TabsTrigger>
          </TabsList>

          <TabsContent value='dashboard' className='mt-4 space-y-6'>
            {/* Stat cards */}
            <div className='grid gap-4 sm:grid-cols-2 lg:grid-cols-4'>
              {statCards.map((card) => (
                <Card key={card.title}>
                  <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                    <CardTitle className='text-sm font-medium'>
                      {card.title}
                    </CardTitle>
                    <card.icon className={`h-4 w-4 ${card.color}`} />
                  </CardHeader>
                  <CardContent>
                    <div className='text-2xl font-bold'>{card.value}</div>
                  </CardContent>
                </Card>
              ))}
            </div>

            {/* Chart placeholder */}
            <Card>
              <CardHeader>
                <CardTitle className='text-base'>기간별 추세</CardTitle>
              </CardHeader>
              <CardContent>
                <div className='flex h-[300px] items-center justify-center rounded-lg border border-dashed'>
                  <p className='text-muted-foreground'>
                    기간별 차트 (API 연결 후 표시)
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value='calendar' className='mt-4'>
            <Card>
              <CardContent className='flex h-[400px] items-center justify-center'>
                <div className='text-center'>
                  <CalendarDays className='mx-auto mb-4 h-12 w-12 text-muted-foreground' />
                  <p className='text-muted-foreground'>
                    캘린더 뷰 (구현 예정)
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>

          <TabsContent value='detail' className='mt-4'>
            <Card>
              <CardContent className='flex h-[400px] items-center justify-center'>
                <div className='text-center'>
                  <BarChart3 className='mx-auto mb-4 h-12 w-12 text-muted-foreground' />
                  <p className='text-muted-foreground'>
                    브랜드별/캠페인별 상세 (구현 예정)
                  </p>
                </div>
              </CardContent>
            </Card>
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}
