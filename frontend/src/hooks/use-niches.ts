/**
 * Niche API hooks (PR-3c).
 *
 * 백엔드: PR-3b 의 /api/admin/niches CRUD.
 * 코드베이스 패턴: fetchApi + useEffect (TanStack Query 미도입 영역).
 */
import { useEffect, useState } from 'react'

import { fetchApi } from '@/lib/api'
import type { Niche, NicheOverview } from '@/types/niche'

export function useNiches(brandId?: number) {
  const [niches, setNiches] = useState<Niche[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    const qs = brandId !== undefined ? `?brand_id=${brandId}` : ''
    fetchApi<Niche[]>(`/api/admin/niches${qs}`)
      .then((data) => {
        if (cancelled) return
        setNiches(Array.isArray(data) ? data : [])
        setError(null)
      })
      .catch((e) => {
        if (cancelled) return
        setNiches([])
        setError(e)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [brandId])

  return { niches, loading, error }
}

export function useNicheOverview(nicheId: number | string) {
  const [overview, setOverview] = useState<NicheOverview | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<unknown>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchApi<NicheOverview>(`/api/admin/niches/${nicheId}/overview`)
      .then((data) => {
        if (cancelled) return
        setOverview(data)
        setError(null)
      })
      .catch((e) => {
        if (cancelled) return
        setOverview(null)
        setError(e)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [nicheId])

  return { overview, loading, error }
}

export function useNicheCountByBrand(): Record<number, number> {
  const { niches } = useNiches()
  const counts: Record<number, number> = {}
  for (const n of niches) {
    if (n.state === 'archived') continue
    counts[n.brand_id] = (counts[n.brand_id] ?? 0) + 1
  }
  return counts
}
