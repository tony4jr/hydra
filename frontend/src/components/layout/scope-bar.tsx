/**
 * Scope bar (PR-8a) — 페이지 헤더 바로 아래.
 *
 * 활성 브랜드 컨텍스트를 모든 페이지에서 항상 보여줌.
 * 사이드바 접혔을 때도 운영자가 스코프 인지.
 */
import { useNiches } from '@/hooks/use-niches'
import { useActiveBrand } from '@/lib/active-brand'
import { labels } from '@/lib/i18n-terms'

export function ScopeBar() {
  const { activeBrand, loading } = useActiveBrand()
  const { niches } = useNiches(activeBrand?.id)

  if (loading || !activeBrand) return null

  const activeNicheCount = niches.filter((n) => n.state === 'active').length

  return (
    <div className='border-b border-border bg-muted/20 px-4 py-2 text-[12px] text-muted-foreground flex items-center gap-2'>
      <span className='font-medium text-foreground'>{activeBrand.name}</span>
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
    </div>
  )
}
