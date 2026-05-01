import { useEffect, useState, useCallback } from 'react'
import { fetchApi, http } from '@/lib/api'
import type { CommentPresetSummary, CommentPresetDetail } from '@/types/comment-preset'

export function useCommentPresets() {
  const [presets, setPresets] = useState<CommentPresetSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [version, setVersion] = useState(0)
  const refresh = useCallback(() => setVersion((v) => v + 1), [])

  useEffect(() => {
    let c = false
    setLoading(true)
    fetchApi<CommentPresetSummary[]>('/api/admin/comment-presets/list')
      .then((d) => !c && setPresets(Array.isArray(d) ? d : []))
      .catch(() => !c && setPresets([]))
      .finally(() => !c && setLoading(false))
    return () => {
      c = true
    }
  }, [version])

  const create = useCallback(
    async (data: { name: string; description?: string }) => {
      await http.post('/api/admin/comment-presets', data)
      refresh()
    },
    [refresh],
  )

  const clone = useCallback(
    async (presetId: number) => {
      await http.post(`/api/admin/comment-presets/${presetId}/clone`)
      refresh()
    },
    [refresh],
  )

  const remove = useCallback(
    async (presetId: number, force = false) => {
      await http.delete(`/api/admin/comment-presets/${presetId}${force ? '?force=true' : ''}`)
      refresh()
    },
    [refresh],
  )

  return { presets, loading, refresh, create, clone, remove }
}

export function useCommentPreset(presetId: number | string | null) {
  const [detail, setDetail] = useState<CommentPresetDetail | null>(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    if (presetId === null) return
    let c = false
    setLoading(true)
    fetchApi<CommentPresetDetail>(`/api/admin/comment-presets/${presetId}`)
      .then((d) => !c && setDetail(d))
      .catch(() => !c && setDetail(null))
      .finally(() => !c && setLoading(false))
    return () => {
      c = true
    }
  }, [presetId])
  return { detail, loading }
}
