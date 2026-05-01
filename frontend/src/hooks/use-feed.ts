import { useEffect, useState } from 'react'
import { fetchApi } from '@/lib/api'
import type { FeedResponse, AlertsResponse, QueueResponse } from '@/types/feed'

export function useFeed(window: string, brandId: number | null) {
  const [data, setData] = useState<FeedResponse | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let c = false
    setLoading(true)
    const qs = new URLSearchParams({ window })
    if (brandId !== null) qs.set('brand_id', String(brandId))
    fetchApi<FeedResponse>(`/api/admin/feed?${qs}`)
      .then((d) => !c && setData(d))
      .catch(() => !c && setData(null))
      .finally(() => !c && setLoading(false))
    return () => {
      c = true
    }
  }, [window, brandId])
  return { data, loading }
}

export function useAlerts(brandId: number | null) {
  const [data, setData] = useState<AlertsResponse | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let c = false
    setLoading(true)
    const qs = new URLSearchParams()
    if (brandId !== null) qs.set('brand_id', String(brandId))
    fetchApi<AlertsResponse>(`/api/admin/alerts?${qs}`)
      .then((d) => !c && setData(d))
      .catch(() => !c && setData(null))
      .finally(() => !c && setLoading(false))
    return () => {
      c = true
    }
  }, [brandId])
  return { data, loading }
}

export function useQueue(brandId: number | null, windowHours = 24) {
  const [data, setData] = useState<QueueResponse | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    let c = false
    setLoading(true)
    const qs = new URLSearchParams({ window_hours: String(windowHours) })
    if (brandId !== null) qs.set('brand_id', String(brandId))
    fetchApi<QueueResponse>(`/api/admin/queue?${qs}`)
      .then((d) => !c && setData(d))
      .catch(() => !c && setData(null))
      .finally(() => !c && setLoading(false))
    return () => {
      c = true
    }
  }, [brandId, windowHours])
  return { data, loading }
}
