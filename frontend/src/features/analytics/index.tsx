import { useEffect, useState, useMemo } from 'react'
import {
  MessageSquare,
  ThumbsUp,
  TrendingUp,
  Ghost,
  CalendarDays,
  BarChart3,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  AreaChart,
  Area,
} from 'recharts'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Button } from '@/components/ui/button'
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

interface DailyData {
  date: string
  comments: number
  likes: number
}

interface BrandPerformance {
  brand: string
  campaigns: number
  comments: number
  likes: number
  ghosts: number
  success_rate: number
}

interface CalendarDay {
  date: string
  comments: number
  likes: number
}

// Mock data for charts when API is unavailable
const mockDailyData: DailyData[] = Array.from({ length: 14 }, (_, i) => {
  const d = new Date()
  d.setDate(d.getDate() - 13 + i)
  return {
    date: `${d.getMonth() + 1}/${d.getDate()}`,
    comments: Math.floor(Math.random() * 15) + 2,
    likes: Math.floor(Math.random() * 25) + 5,
  }
})

const mockBrandData: BrandPerformance[] = [
  { brand: 'Brand A', campaigns: 3, comments: 45, likes: 120, ghosts: 2, success_rate: 95.6 },
  { brand: 'Brand B', campaigns: 2, comments: 28, likes: 85, ghosts: 1, success_rate: 96.4 },
  { brand: 'Brand C', campaigns: 1, comments: 12, likes: 38, ghosts: 0, success_rate: 100 },
]

function DashboardTab({ stats }: { stats: AnalyticsStats }) {
  const [dailyData, setDailyData] = useState<DailyData[]>([])
  const [brandData, setBrandData] = useState<BrandPerformance[]>([])

  useEffect(() => {
    // /analytics/api/daily는 아직 없음 — mock 데이터 사용
    setDailyData(mockDailyData)

    fetchApi<BrandPerformance[]>('/brands/api/performance-summary')
      .then((data) => setBrandData(Array.isArray(data) ? data : []))
      .catch(() => setBrandData(mockBrandData))
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
    <div className='space-y-6'>
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

      {/* Daily trend chart */}
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>일별 댓글/좋아요 추이</CardTitle>
        </CardHeader>
        <CardContent>
          {dailyData.length === 0 ? (
            <div className='flex h-[300px] items-center justify-center rounded-lg border border-dashed'>
              <p className='text-muted-foreground'>데이터가 없습니다</p>
            </div>
          ) : (
            <ResponsiveContainer width='100%' height={300}>
              <AreaChart data={dailyData}>
                <CartesianGrid strokeDasharray='3 3' className='stroke-muted' />
                <XAxis dataKey='date' className='text-xs' />
                <YAxis className='text-xs' />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                />
                <Area
                  type='monotone'
                  dataKey='comments'
                  name='댓글'
                  stroke='hsl(217, 91%, 60%)'
                  fill='hsl(217, 91%, 60%)'
                  fillOpacity={0.2}
                />
                <Area
                  type='monotone'
                  dataKey='likes'
                  name='좋아요'
                  stroke='hsl(142, 71%, 45%)'
                  fill='hsl(142, 71%, 45%)'
                  fillOpacity={0.2}
                />
              </AreaChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>

      {/* Brand comparison chart */}
      <Card>
        <CardHeader>
          <CardTitle className='text-base'>브랜드별 성과 비교</CardTitle>
        </CardHeader>
        <CardContent>
          {brandData.length === 0 ? (
            <div className='flex h-[300px] items-center justify-center rounded-lg border border-dashed'>
              <p className='text-muted-foreground'>데이터가 없습니다</p>
            </div>
          ) : (
            <ResponsiveContainer width='100%' height={300}>
              <BarChart data={brandData}>
                <CartesianGrid strokeDasharray='3 3' className='stroke-muted' />
                <XAxis dataKey='brand' className='text-xs' />
                <YAxis className='text-xs' />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: '8px',
                    color: 'hsl(var(--popover-foreground))',
                  }}
                />
                <Bar dataKey='comments' name='댓글' fill='hsl(217, 91%, 60%)' radius={[4, 4, 0, 0]} />
                <Bar dataKey='likes' name='좋아요' fill='hsl(142, 71%, 45%)' radius={[4, 4, 0, 0]} />
                <Bar dataKey='ghosts' name='고스트' fill='hsl(25, 95%, 53%)' radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </CardContent>
      </Card>
    </div>
  )
}

function CalendarTab() {
  const [year, setYear] = useState(() => new Date().getFullYear())
  const [month, setMonth] = useState(() => new Date().getMonth() + 1)
  const [calendarData, setCalendarData] = useState<CalendarDay[]>([])

  useEffect(() => {
    fetchApi<CalendarDay[]>(
      `/api/calendar?year=${year}&month=${month}`
    )
      .then((data) => setCalendarData(Array.isArray(data) ? data : []))
      .catch(() => setCalendarData([]))
  }, [year, month])

  const dayNames = ['일', '월', '화', '수', '목', '금', '토']

  const calendarGrid = useMemo(() => {
    const firstDay = new Date(year, month - 1, 1)
    const lastDay = new Date(year, month, 0)
    const startDow = firstDay.getDay()
    const totalDays = lastDay.getDate()

    const dataMap = new Map<number, CalendarDay>()
    calendarData.forEach((d) => {
      const day = parseInt(d.date.split('-')[2], 10)
      dataMap.set(day, d)
    })

    const cells: { day: number; data?: CalendarDay }[] = []
    // Empty cells before first day
    for (let i = 0; i < startDow; i++) {
      cells.push({ day: 0 })
    }
    for (let d = 1; d <= totalDays; d++) {
      cells.push({ day: d, data: dataMap.get(d) })
    }
    return cells
  }, [year, month, calendarData])

  const prevMonth = () => {
    if (month === 1) {
      setYear(year - 1)
      setMonth(12)
    } else {
      setMonth(month - 1)
    }
  }

  const nextMonth = () => {
    if (month === 12) {
      setYear(year + 1)
      setMonth(1)
    } else {
      setMonth(month + 1)
    }
  }

  const today = new Date()
  const isToday = (day: number) =>
    year === today.getFullYear() &&
    month === today.getMonth() + 1 &&
    day === today.getDate()

  return (
    <Card>
      <CardHeader>
        <div className='flex items-center justify-between'>
          <Button variant='ghost' size='icon' onClick={prevMonth}>
            <ChevronLeft className='h-4 w-4' />
          </Button>
          <CardTitle className='text-base'>
            {year}년 {month}월
          </CardTitle>
          <Button variant='ghost' size='icon' onClick={nextMonth}>
            <ChevronRight className='h-4 w-4' />
          </Button>
        </div>
      </CardHeader>
      <CardContent>
        <div className='grid grid-cols-7 gap-1'>
          {/* Day headers */}
          {dayNames.map((name) => (
            <div
              key={name}
              className='py-2 text-center text-xs font-medium text-muted-foreground'
            >
              {name}
            </div>
          ))}

          {/* Day cells */}
          {calendarGrid.map((cell, i) => (
            <div
              key={i}
              className={`min-h-[72px] rounded-md border p-1 text-xs ${
                cell.day === 0
                  ? 'border-transparent'
                  : isToday(cell.day)
                    ? 'border-primary bg-primary/5'
                    : 'border-border'
              }`}
            >
              {cell.day > 0 && (
                <>
                  <div
                    className={`mb-1 font-medium ${isToday(cell.day) ? 'text-primary' : ''}`}
                  >
                    {cell.day}
                  </div>
                  {cell.data && (cell.data.comments > 0 || cell.data.likes > 0) && (
                    <div className='space-y-0.5'>
                      {cell.data.comments > 0 && (
                        <div className='flex items-center gap-1 text-blue-500'>
                          <MessageSquare className='h-3 w-3' />
                          <span>{cell.data.comments}</span>
                        </div>
                      )}
                      {cell.data.likes > 0 && (
                        <div className='flex items-center gap-1 text-green-500'>
                          <ThumbsUp className='h-3 w-3' />
                          <span>{cell.data.likes}</span>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  )
}

function DetailTab() {
  const [brands, setBrands] = useState<BrandPerformance[]>([])

  useEffect(() => {
    fetchApi<BrandPerformance[]>('/brands/api/performance-summary')
      .then((data) => setBrands(Array.isArray(data) ? data : []))
      .catch(() => setBrands(mockBrandData))
  }, [])

  return (
    <Card>
      <CardHeader>
        <CardTitle className='text-base'>브랜드별 성과</CardTitle>
      </CardHeader>
      <CardContent>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>브랜드</TableHead>
              <TableHead className='text-center'>캠페인 수</TableHead>
              <TableHead className='text-center'>댓글 수</TableHead>
              <TableHead className='text-center'>좋아요 수</TableHead>
              <TableHead className='text-center'>고스트 수</TableHead>
              <TableHead className='text-center'>성공률</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {brands.length === 0 ? (
              <TableRow>
                <TableCell
                  colSpan={6}
                  className='py-10 text-center text-muted-foreground'
                >
                  데이터가 없습니다
                </TableCell>
              </TableRow>
            ) : (
              brands.map((b) => (
                <TableRow key={b.brand}>
                  <TableCell className='font-medium'>{b.brand}</TableCell>
                  <TableCell className='text-center'>{b.campaigns}</TableCell>
                  <TableCell className='text-center'>{b.comments}</TableCell>
                  <TableCell className='text-center'>{b.likes}</TableCell>
                  <TableCell className='text-center'>{b.ghosts}</TableCell>
                  <TableCell className='text-center'>
                    {b.success_rate}%
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export default function AnalyticsPage() {
  const [stats, setStats] = useState<AnalyticsStats>({
    total_comments: 0,
    total_likes: 0,
    success_rate: 0,
    ghost_rate: 0,
  })

  useEffect(() => {
    // /analytics/api/stats는 아직 없음 — /api/stats 사용
    fetchApi<any>('/api/stats')
      .then((data) => setStats({
        total_comments: data?.today?.comments || 0,
        total_likes: data?.today?.likes || 0,
        success_rate: 0,
        ghost_rate: 0,
      }))
      .catch(() => {})
  }, [])

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

          <TabsContent value='dashboard' className='mt-4'>
            <DashboardTab stats={stats} />
          </TabsContent>

          <TabsContent value='calendar' className='mt-4'>
            <CalendarTab />
          </TabsContent>

          <TabsContent value='detail' className='mt-4'>
            <DetailTab />
          </TabsContent>
        </Tabs>
      </Main>
    </>
  )
}
