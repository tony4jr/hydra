/**
 * Scope bar (PR-8a → PR-B 확장).
 *
 * 활성 브랜드 컨텍스트를 모든 페이지에서 항상 보여줌.
 * 사이드바 접혔을 때도 운영자가 스코프 인지.
 *
 * PR-B: 브랜드명 클릭 → 브랜드 상세, 작업 큐 카운트 노출.
 */
import { Link } from '@tanstack/react-router'

import { useQueue } from '@/hooks/use-feed'
import { useNiches } from '@/hooks/use-niches'
import { useActiveBrand } from '@/lib/active-brand'
import { labels } from '@/lib/i18n-terms'

export function ScopeBar() {
  const { activeBrand, loading } = useActiveBrand()
  const { niches } = useNiches(activeBrand?.id)
  const { data: queue } = useQueue(activeBrand?.id ?? null)

  if (loading || !activeBrand) return null

  const activeNicheCount = niches.filter((n) => n.state === 'active').length
  const queueTotal = queue?.total ?? 0

  return (
    <div className='border-b border-border bg-muted/20 px-4 py-2 text-[12px] text-muted-foreground flex items-center gap-2'>
      <Link
        to='/brands/$brandId'
        params={{ brandId: String(activeBrand.id) }}
        className='font-medium text-foreground hover:underline'
      >
        {activeBrand.name}
        {activeBrand.product_name && (
          <span className='text-muted-foreground font-normal'> — {activeBrand.product_name}</span>
        )}
      </Link>
      {activeBrand.product_category && (
        <>
          <span>·</span>
          <span>{activeBrand.product_category}</span>
        </>
      )}
      <span>·</span>
      <span>
        {labels.niche} {activeNicheCount}개
      </span>
      <span>·</span>
      <span>예정 작업 {queueTotal}건 (24h)</span>
    </div>
  )
}
