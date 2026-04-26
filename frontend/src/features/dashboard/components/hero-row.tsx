/**
 * Hero row — dashboard's primary stat.
 *
 *   "오늘 댓글"
 *   [   64   ] (큰 숫자)        [sparkline last 24h]      +12% vs 어제
 *
 * Big-number aesthetic — Linear/Vercel inspired.
 */
import { useEffect, useState } from 'react'
import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { useCountUp } from '@/hooks/use-count-up'
import { Sparkline } from '@/components/sparkline'
import { fetchApi } from '@/lib/api'

interface DailySeries {
  hours: number[]    // last 24 hourly counts
  total: number
  yesterday: number
}

export function DashboardHero() {
  const [series, setSeries] = useState<DailySeries | null>(null)
  const animated = useCountUp(series?.total ?? 0)

  useEffect(() => {
    let cancelled = false
    async function load() {
      try {
        const data = await fetchApi<DailySeries>('/api/stats/comments-24h').catch(() => null)
        if (!cancelled && data) setSeries(data)
      } catch { /* ignore */ }
    }
    load()
    const id = setInterval(load, 30_000)
    return () => { cancelled = true; clearInterval(id) }
  }, [])

  // Fallback: synthetic series until endpoint exists
  const hours = series?.hours ?? Array.from({ length: 24 }, () => 0)
  const total = series?.total ?? 0
  const yesterday = series?.yesterday ?? 0
  const delta = yesterday > 0 ? Math.round(((total - yesterday) / yesterday) * 100) : 0
  const trend = total > yesterday ? 'up' : total < yesterday ? 'down' : 'flat'

  return (
    <div className='hydra-hero'>
      <div className='hydra-hero-label'>오늘 댓글</div>
      <div className='hydra-hero-flex'>
        <div className='hydra-hero-num'>{animated}</div>
        <div className='hydra-hero-spark'>
          <Sparkline data={hours} width={140} height={36} color='var(--hydra-blue)' fillOpacity={0.16} />
          <div className='hydra-hero-period'>최근 24시간</div>
        </div>
        <div className={`hydra-hero-delta ${trend}`}>
          {trend === 'up' && <ArrowUpRight className='size-4' />}
          {trend === 'down' && <ArrowDownRight className='size-4' />}
          {trend === 'flat' && <Minus className='size-4' />}
          <span>
            {delta === 0 ? '변화 없음' : `${delta > 0 ? '+' : ''}${delta}% vs 어제`}
          </span>
        </div>
      </div>
    </div>
  )
}
