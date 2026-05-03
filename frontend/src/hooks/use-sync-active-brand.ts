import { useEffect } from 'react'
import { useActiveBrand } from '@/lib/active-brand'

/**
 * URL의 brandId를 활성 브랜드로 동기화.
 *
 * 브랜드 스코프 페이지(/products/$brandId, /products/$brandId/niches/...) 진입 시,
 * ScopeBar/사이드바가 가리키는 활성 브랜드와 URL이 어긋나지 않도록 맞춰줌.
 */
export function useSyncActiveBrand(brandId: number | null | undefined) {
  const { brands, activeBrand, setActiveBrandId } = useActiveBrand()
  useEffect(() => {
    if (!brandId || Number.isNaN(brandId)) return
    if (activeBrand?.id === brandId) return
    if (!brands.some((b) => b.id === brandId)) return
    setActiveBrandId(brandId)
  }, [brandId, brands, activeBrand?.id, setActiveBrandId])
}
