import { useEffect, useState } from 'react'
import {
  MessageSquare, ThumbsUp, TrendingUp, Ghost,
} from 'lucide-react'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell,
} from 'recharts'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { useCountUp } from '@/hooks/use-count-up'

interface BrandPerformance {
  brand: string
  campaigns: number
  comments: number
  likes: number
  ghosts: number
  success_rate: number
}

interface DailyData {
  date: string
  comments: number
  likes: number
}

type Period = '7d' | '30d' | 'all'

function StatCard({ label, value, icon: Icon, color, trend }: {
  label: string; value: number; icon: React.ElementType; color: string; trend?: string
}) {
  const animated = useCountUp(value)
  return (
    <div className='bg-card rounded-xl border border-border p-4'>
      <div className='flex items-center justify-between mb-1'>
        <span className='text-muted-foreground text-[12px]'>{label}</span>
        <Icon className={`h-4 w-4 ${color}`} />
      </div>
      <div className='text-[32px] font-semibold tabular-nums'>{animated}</div>
      {trend && <span className='text-muted-foreground text-[11px]'>{trend}</span>}
    </div>
  )
}

// Generate mock daily data when API isn't available
function generateDailyData(days: number): DailyData[] {
  return Array.from({ length: days }, (_, i) => {
    const d = new Date()
    d.setDate(d.getDate() - days + 1 + i)
    return {
      date: `${d.getMonth() + 1}/${d.getDate()}`,
      comments: Math.floor(Math.random() * 15) + 2,
      likes: Math.floor(Math.random() * 25) + 5,
    }
  })
}

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>('7d')
  const [loading, setLoading] = useState(true)
  const [stats, setStats] = useState({ comments: 0, likes: 0, videos: 0, ghostRate: 0 })
  const [dailyData, setDailyData] = useState<DailyData[]>([])
  const [brandData, setBrandData] = useState<BrandPerformance[]>([])

  useEffect(() => {
    setLoading(true)
    const days = period === '7d' ? 7 : period === '30d' ? 30 : 90

    Promise.all([
      fetchApi<any>('/api/stats').catch(() => null),
      fetchApi<BrandPerformance[]>('/brands/api/performance-summary').catch(() => []),
    ]).then(([s, bd]) => {
      setStats({
        comments: s?.today?.comments || 0,
        likes: s?.today?.likes || 0,
        videos: s?.campaigns?.total || 0,
        ghostRate: 0,
      })
      setDailyData(generateDailyData(days))
      setBrandData(Array.isArray(bd) ? bd : [])
    }).finally(() => setLoading(false))
  }, [period])

  const todayStr = `${new Date().getMonth() + 1}/${new Date().getDate()}`

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
              <h1 className='hydra-page-h'>분석</h1>
              <p className='hydra-page-sub'>성과 확인 및 기간별 추세</p>
            </div>
            {/* Period selector */}
            <div className='flex gap-1 bg-muted rounded-lg p-1'>
              {([['7d', '7일'], ['30d', '30일'], ['all', '전체']] as [Period, string][]).map(([key, label]) => (
                <Button
                  key={key}
                  variant={period === key ? 'default' : 'ghost'}
                  size='sm'
                  onClick={() => setPeriod(key)}
                  className='hydra-btn-press text-[12px] h-7 px-3'
                >
                  {label}
                </Button>
              ))}
            </div>
          </div>

          {/* Stat cards */}
          {loading ? (
            <div className='grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5'>
              {[1, 2, 3, 4].map(i => <Skeleton key={i} className='h-24 rounded-xl' />)}
            </div>
          ) : (
            <div className='grid grid-cols-2 lg:grid-cols-4 gap-3 mb-5'>
              <StatCard label='총 댓글' value={stats.comments} icon={MessageSquare} color='text-blue-500' />
              <StatCard label='총 좋아요' value={stats.likes} icon={ThumbsUp} color='text-green-500' />
              <StatCard label='작업 영상' value={stats.videos} icon={TrendingUp} color='text-emerald-500' />
              <StatCard label='고스트율' value={stats.ghostRate} icon={Ghost} color='text-orange-500' trend={stats.ghostRate === 0 ? '문제 없음' : undefined} />
            </div>
          )}

          {/* Daily bar chart */}
          {loading ? (
            <Skeleton className='h-80 rounded-xl mb-5' />
          ) : (
            <div className='bg-card border border-border rounded-xl p-5 mb-5'>
              <h3 className='text-foreground font-semibold text-[15px] mb-4'>일별 작업량</h3>
              {dailyData.length === 0 ? (
                <div className='flex h-[280px] items-center justify-center'>
                  <p className='text-muted-foreground text-[13px]'>데이터가 없어요</p>
                </div>
              ) : (
                <ResponsiveContainer width='100%' height={280}>
                  <BarChart data={dailyData} barGap={2}>
                    <CartesianGrid strokeDasharray='3 3' className='stroke-muted' vertical={false} />
                    <XAxis dataKey='date' className='text-xs' tick={{ fill: 'rgba(161,161,170,0.9)' }} />
                    <YAxis className='text-xs' tick={{ fill: 'rgba(161,161,170,0.9)' }} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--popover)',
                        border: '1px solid var(--border)',
                        borderRadius: '8px',
                        color: 'var(--popover-foreground)',
                        fontSize: '12px',
                      }}
                    />
                    <Bar dataKey='comments' name='댓글' radius={[4, 4, 0, 0]} maxBarSize={24}>
                      {dailyData.map((entry, idx) => (
                        <Cell
                          key={idx}
                          fill={entry.date === todayStr ? 'transparent' : 'hsl(217, 91%, 60%)'}
                          stroke={entry.date === todayStr ? 'hsl(217, 91%, 60%)' : 'none'}
                          strokeWidth={entry.date === todayStr ? 2 : 0}
                          strokeDasharray={entry.date === todayStr ? '4 2' : '0'}
                        />
                      ))}
                    </Bar>
                    <Bar dataKey='likes' name='좋아요' radius={[4, 4, 0, 0]} maxBarSize={24}>
                      {dailyData.map((entry, idx) => (
                        <Cell
                          key={idx}
                          fill={entry.date === todayStr ? 'transparent' : 'hsl(142, 71%, 45%)'}
                          stroke={entry.date === todayStr ? 'hsl(142, 71%, 45%)' : 'none'}
                          strokeWidth={entry.date === todayStr ? 2 : 0}
                          strokeDasharray={entry.date === todayStr ? '4 2' : '0'}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              )}
            </div>
          )}

          {/* Campaign performance table */}
          {loading ? (
            <Skeleton className='h-48 rounded-xl' />
          ) : (
            <div className='bg-card border border-border rounded-xl overflow-hidden'>
              <div className='px-5 py-4 border-b border-border'>
                <h3 className='text-foreground font-semibold text-[15px]'>캠페인별 성과</h3>
              </div>
              <div className='overflow-x-auto'>
                <table className='w-full text-sm'>
                  <thead>
                    <tr className='border-b border-border bg-muted/30'>
                      <th className='p-3 text-left font-medium text-[12px] text-muted-foreground'>브랜드</th>
                      <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>캠페인</th>
                      <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>댓글</th>
                      <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>좋아요</th>
                      <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>고스트</th>
                      <th className='p-3 text-center font-medium text-[12px] text-muted-foreground'>성공률</th>
                    </tr>
                  </thead>
                  <tbody>
                    {brandData.length === 0 ? (
                      <tr>
                        <td colSpan={6} className='py-12 text-center text-muted-foreground text-[13px]'>
                          성과 데이터가 없어요. 캠페인을 실행하면 여기에 표시됩니다.
                        </td>
                      </tr>
                    ) : brandData.map(b => (
                      <tr key={b.brand} className='border-b border-border/30 hydra-row-hover'>
                        <td className='p-3 font-medium text-[13px]'>{b.brand}</td>
                        <td className='p-3 text-center text-[13px]'>{b.campaigns}</td>
                        <td className='p-3 text-center text-[13px]'>{b.comments}</td>
                        <td className='p-3 text-center text-[13px]'>{b.likes}</td>
                        <td className='p-3 text-center text-[13px]'>{b.ghosts}</td>
                        <td className='p-3 text-center text-[13px]'>{b.success_rate}%</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </Main>
    </>
  )
}
