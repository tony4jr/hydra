/**
 * 분석 탭 (PR-4f). spec PR-4 §5.
 *
 * lean: daily / campaign / hourly / ranking. persona+preset performance 보류.
 * 차트 lib 도입 X (build 슬림). 막대 길이 = 비율 inline div.
 */
import { useState } from 'react'

import { useNicheAnalytics } from '@/hooks/use-niche-analytics'
import { Skeleton } from '@/components/ui/skeleton'

interface Props {
  nicheId: string
}

export function AnalyticsTab({ nicheId }: Props) {
  const [windowDays, setWindowDays] = useState<number>(7)
  const { analytics, loading } = useNicheAnalytics(nicheId, windowDays)

  if (loading) {
    return <Skeleton className='h-64 rounded-xl' />
  }

  if (!analytics) {
    return (
      <div className='bg-card border border-border rounded-xl py-16 text-center'>
        <p className='text-muted-foreground text-[14px]'>분석 데이터를 불러오지 못했어요</p>
      </div>
    )
  }

  const totalComments = analytics.daily_workload.reduce(
    (sum, d) => sum + d.comments,
    0,
  )
  const maxDaily = Math.max(1, ...analytics.daily_workload.map((d) => d.comments))
  const maxHourly = Math.max(1, ...analytics.hourly_pattern.map((h) => h.comments))

  return (
    <div className='space-y-5'>
      <div className='flex items-center justify-between'>
        <p className='text-muted-foreground text-[12px]'>
          기간 {analytics.window_days}일 · 총 댓글 {totalComments}
        </p>
        <select
          value={windowDays}
          onChange={(e) => setWindowDays(Number(e.target.value))}
          className='bg-background border border-border rounded-md text-[12px] px-2 py-1'
        >
          <option value={7}>7일</option>
          <option value={30}>30일</option>
          <option value={90}>90일</option>
        </select>
      </div>

      <div className='bg-card border border-border rounded-xl p-5'>
        <p className='text-muted-foreground text-[12px] mb-3'>일별 댓글</p>
        {analytics.daily_workload.length === 0 ? (
          <p className='text-muted-foreground/60 text-[13px]'>데이터가 없어요</p>
        ) : (
          <ul className='space-y-1.5'>
            {analytics.daily_workload.map((d) => (
              <li key={d.date} className='flex items-center gap-2 text-[12px]'>
                <span className='w-20 text-muted-foreground/70'>{d.date}</span>
                <div className='flex-1 bg-muted/40 rounded h-2 overflow-hidden'>
                  <div
                    className='bg-primary h-full'
                    style={{ width: `${(d.comments / maxDaily) * 100}%` }}
                  />
                </div>
                <span className='w-10 text-right text-foreground'>{d.comments}</span>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div className='grid gap-3 md:grid-cols-2'>
        <div className='bg-card border border-border rounded-xl p-5'>
          <p className='text-muted-foreground text-[12px] mb-3'>캠페인별 성과</p>
          {analytics.campaign_performance.length === 0 ? (
            <p className='text-muted-foreground/60 text-[13px]'>캠페인이 없어요</p>
          ) : (
            <ul className='divide-y divide-border'>
              {analytics.campaign_performance.map((c) => (
                <li
                  key={c.campaign_id}
                  className='py-2 flex items-center justify-between gap-2'
                >
                  <span className='text-foreground text-[13px] truncate'>
                    {c.name || `#${c.campaign_id}`}
                  </span>
                  <span className='text-muted-foreground/80 text-[12px]'>
                    {c.comments}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className='bg-card border border-border rounded-xl p-5'>
          <p className='text-muted-foreground text-[12px] mb-3'>시간대 분포</p>
          {analytics.hourly_pattern.length === 0 ? (
            <p className='text-muted-foreground/60 text-[13px]'>데이터가 없어요</p>
          ) : (
            <div className='grid grid-cols-12 gap-0.5 items-end h-24'>
              {Array.from({ length: 24 }, (_, h) => {
                const e = analytics.hourly_pattern.find((x) => x.hour === h)
                const count = e?.comments ?? 0
                return (
                  <div
                    key={h}
                    title={`${h}시: ${count}`}
                    className='bg-primary/70 rounded-t'
                    style={{ height: `${(count / maxHourly) * 100}%` }}
                  />
                )
              })}
            </div>
          )}
        </div>
      </div>

      {analytics.ranking_summary.best_campaign_id !== null && (
        <div className='bg-card border border-border rounded-xl p-5'>
          <p className='text-muted-foreground text-[12px]'>베스트 캠페인</p>
          <p className='text-foreground text-[14px] font-medium mt-1'>
            #{analytics.ranking_summary.best_campaign_id} · 댓글{' '}
            {analytics.ranking_summary.best_comments}
          </p>
        </div>
      )}
    </div>
  )
}
