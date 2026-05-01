/**
 * 수집 탭 (PR-4c) hooks. 백엔드: /api/admin/niches/{id}/collection/flow,
 * /keywords, /recent-videos.
 */
import { useCallback, useEffect, useState } from 'react'

import { fetchApi, http } from '@/lib/api'
import type {
  CollectionFlow,
  KeywordWithMetrics,
  RecentVideo,
} from '@/types/niche'

export function useCollectionFlow(nicheId: number | string, windowHours = 24) {
  const [flow, setFlow] = useState<CollectionFlow | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    fetchApi<CollectionFlow>(
      `/api/admin/niches/${nicheId}/collection/flow?window_hours=${windowHours}`,
    )
      .then((d) => !cancelled && setFlow(d))
      .catch(() => !cancelled && setFlow(null))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [nicheId, windowHours])
  return { flow, loading }
}

export function useNicheKeywords(nicheId: number | string) {
  const [keywords, setKeywords] = useState<KeywordWithMetrics[]>([])
  const [loading, setLoading] = useState(true)
  const [version, setVersion] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchApi<KeywordWithMetrics[]>(`/api/admin/niches/${nicheId}/keywords`)
      .then((d) => !cancelled && setKeywords(Array.isArray(d) ? d : []))
      .catch(() => !cancelled && setKeywords([]))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [nicheId, version])

  const refresh = useCallback(() => setVersion((v) => v + 1), [])

  const updatePolling = useCallback(
    async (kwId: number, polling: '5min' | '30min' | 'daily') => {
      await http.patch(`/api/admin/niches/${nicheId}/keywords/${kwId}`, { polling })
      refresh()
    },
    [nicheId, refresh],
  )

  return { keywords, loading, refresh, updatePolling }
}

export function useRecentVideos(nicheId: number | string, limit = 50) {
  const [videos, setVideos] = useState<RecentVideo[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let cancelled = false
    fetchApi<RecentVideo[]>(
      `/api/admin/niches/${nicheId}/recent-videos?limit=${limit}`,
    )
      .then((d) => !cancelled && setVideos(Array.isArray(d) ? d : []))
      .catch(() => !cancelled && setVideos([]))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [nicheId, limit])
  return { videos, loading }
}
