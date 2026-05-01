/**
 * 메시지 탭 (PR-4d) hooks. 백엔드: /api/admin/niches/{id}/messaging,
 * /api/admin/niches/{id}/personas.
 */
import { useCallback, useEffect, useState } from 'react'

import { fetchApi, http } from '@/lib/api'
import type { NicheMessaging, NichePersona } from '@/types/niche'

export function useNicheMessaging(nicheId: number | string) {
  const [messaging, setMessaging] = useState<NicheMessaging | null>(null)
  const [loading, setLoading] = useState(true)
  const [version, setVersion] = useState(0)
  const refresh = useCallback(() => setVersion((v) => v + 1), [])

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchApi<NicheMessaging>(`/api/admin/niches/${nicheId}/messaging`)
      .then((d) => !cancelled && setMessaging(d))
      .catch(() => !cancelled && setMessaging(null))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
  }, [nicheId, version])

  const update = useCallback(
    async (patch: Partial<Omit<NicheMessaging, 'niche_id' | 'personas'>>) => {
      await http.patch(`/api/admin/niches/${nicheId}/messaging`, patch)
      refresh()
    },
    [nicheId, refresh],
  )

  const addPersona = useCallback(
    async (persona: NichePersona) => {
      await http.post(`/api/admin/niches/${nicheId}/personas`, persona)
      refresh()
    },
    [nicheId, refresh],
  )

  const removePersona = useCallback(
    async (personaId: string) => {
      await http.delete(`/api/admin/niches/${nicheId}/personas/${personaId}`)
      refresh()
    },
    [nicheId, refresh],
  )

  return { messaging, loading, refresh, update, addPersona, removePersona }
}
