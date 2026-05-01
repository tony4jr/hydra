/**
 * 시장 개요 탭 (PR-4b).
 *
 * 백엔드: GET /api/admin/niches/{id}/overview (PR-4b).
 * spec: redesign/PR-4-niche-tabs.md §4.
 */
import { useNicheOverview } from '@/hooks/use-niches'
import { labels } from '@/lib/i18n-terms'
import { Skeleton } from '@/components/ui/skeleton'

interface Props {
  nicheId: string
}

export function OverviewTab({ nicheId }: Props) {
  const { overview, loading, error } = useNicheOverview(nicheId)

  if (loading) {
    return (
      <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-4'>
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className='h-24 rounded-xl' />
        ))}
      </div>
    )
  }

  if (error || !overview) {
    return (
      <div className='bg-card border border-border rounded-xl py-16 text-center'>
        <p className='text-muted-foreground text-[14px]'>개요를 불러오지 못했어요</p>
      </div>
    )
  }

  const { stats, active_campaigns, niche } = overview

  return (
    <div className='space-y-5'>
      <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-4'>
        <StatCard label='영상 풀' value={stats.video_pool_size} />
        <StatCard label='활성 키워드' value={stats.keywords_count} />
        <StatCard label='진행 캠페인' value={stats.active_campaigns} />
        <StatCard label='7일 댓글' value={stats.comments_7d} />
      </div>

      <div className='grid gap-3 md:grid-cols-2'>
        <div className='bg-card border border-border rounded-xl p-5'>
          <p className='text-muted-foreground text-[12px] mb-2'>{labels.marketDefinition}</p>
          <p className='text-foreground text-[14px] line-clamp-3'>
            {niche.market_definition || '비어있음 — 수집 탭에서 설정하세요'}
          </p>
          <p className='text-muted-foreground/60 text-[12px] mt-3'>
            적합도 임계값 {niche.embedding_threshold} · 수집 깊이 {niche.collection_depth}
          </p>
        </div>
        <div className='bg-card border border-border rounded-xl p-5'>
          <p className='text-muted-foreground text-[12px] mb-2'>임계값 요약</p>
          <ul className='text-[13px] text-foreground space-y-1'>
            <li>트렌딩 VPH ≥ {niche.trending_vph_threshold}</li>
            <li>신규 영상 윈도우 {niche.new_video_hours}h</li>
            <li>장기 점수 ≥ {niche.long_term_score_threshold}</li>
            <li>키워드 변형 {niche.keyword_variation_count}개</li>
            <li>영상당 프리셋 {niche.preset_per_video_limit}회</li>
          </ul>
        </div>
      </div>

      <div className='bg-card border border-border rounded-xl p-5'>
        <p className='text-muted-foreground text-[12px] mb-3'>진행 중 캠페인</p>
        {active_campaigns.length === 0 ? (
          <p className='text-muted-foreground/60 text-[13px]'>활성 캠페인이 없어요</p>
        ) : (
          <ul className='space-y-2'>
            {active_campaigns.map((c) => (
              <li
                key={c.id}
                className='flex items-center justify-between border-b border-border last:border-0 py-2'
              >
                <div>
                  <p className='text-foreground text-[14px] font-medium'>
                    {c.name || `캠페인 #${c.id}`}
                  </p>
                  <p className='text-muted-foreground/60 text-[11px]'>
                    {c.scenario} · 목표 {c.target_count ?? '-'}
                  </p>
                </div>
                <span className='hydra-tag hydra-tag-primary'>{c.status}</span>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}

function StatCard({ label, value }: { label: string; value: number }) {
  return (
    <div className='bg-card border border-border rounded-xl p-4'>
      <p className='text-muted-foreground text-[12px]'>{label}</p>
      <p className='text-foreground font-semibold mt-1 text-[32px] leading-none'>{value}</p>
    </div>
  )
}
