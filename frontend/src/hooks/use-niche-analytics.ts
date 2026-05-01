/**
 * 분석 탭 (PR-4f) hook.
 * 백엔드: GET /api/admin/niches/{id}/analytics?window_days=N
 */
import { useEffect, useState } from 'react'

import { fetchApi } from '@/lib/api'
import type { NicheAnalytics } from '@/types/niche'

export function useNicheAnalytics(nicheId: number | string, windowDays = 7) {
  const [analytics, setAnalytics] = useState<NicheAnalytics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchApi<NicheAnalytics>(
      `/api/admin/niches/${nicheId}/analytics?window_days=${windowDays}`,
    )
      .then((d) => !cancelled && setAnalytics(d))
      .catch(() => !cancelled && setAnalytics(null))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [nicheId, windowDays])

  return { analytics, loading }
}
