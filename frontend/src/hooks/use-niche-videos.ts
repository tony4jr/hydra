import { useEffect, useState } from 'react'
import { fetchApi } from '@/lib/api'

export interface NicheVideoRow {
  video_id: string
  title: string | null
  channel: string | null
  view_count: number | null
  url: string
  state: string | null
  tier: string | null
  market_fitness: number | null
  blacklist_reason: string | null
  collected_at: string | null
}

export function useNicheVideos(
  nicheId: number | string,
  sort: string = 'recent',
  filter: string | null = null,
) {
  const [videos, setVideos] = useState<NicheVideoRow[]>([])
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let c = false
    setLoading(true)
    const qs = new URLSearchParams({ sort })
    if (filter) qs.set('filter', filter)
    fetchApi<NicheVideoRow[]>(`/api/admin/niches/${nicheId}/videos?${qs}`)
      .then((d) => !c && setVideos(Array.isArray(d) ? d : []))
      .catch(() => !c && setVideos([]))
      .finally(() => !c && setLoading(false))
    return () => {
      c = true
    }
  }, [nicheId, sort, filter])
  return { videos, loading }
}
