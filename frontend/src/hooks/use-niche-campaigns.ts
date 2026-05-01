/**
 * 캠페인 탭 (PR-4e) hook.
 * 백엔드: GET /api/admin/niches/{id}/campaigns,
 *         POST /campaigns/api/{cp_id}/{pause|resume}.
 */
import { useCallback, useEffect, useState } from 'react'

import { fetchApi, http } from '@/lib/api'
import type { NicheCampaign } from '@/types/niche'

export function useNicheCampaigns(nicheId: number | string) {
  const [campaigns, setCampaigns] = useState<NicheCampaign[]>([])
  const [loading, setLoading] = useState(true)
  const [version, setVersion] = useState(0)
  const refresh = useCallback(() => setVersion((v) => v + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchApi<NicheCampaign[]>(`/api/admin/niches/${nicheId}/campaigns`)
      .then((d) => !cancelled && setCampaigns(Array.isArray(d) ? d : []))
      .catch(() => !cancelled && setCampaigns([]))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [nicheId, version])

  const pause = useCallback(
    async (cpId: number) => {
      await http.post(`/campaigns/api/${cpId}/pause`)
      refresh()
    },
    [refresh],
  )
  const resume = useCallback(
    async (cpId: number) => {
      await http.post(`/campaigns/api/${cpId}/resume`)
      refresh()
    },
    [refresh],
  )

  return { campaigns, loading, refresh, pause, resume }
}
