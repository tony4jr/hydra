/**
 * Active brand context (PR-8a).
 *
 * 브랜드 스위처가 선택한 브랜드를 모든 페이지에서 공유.
 * localStorage 영속, 사이드바 + scope bar 가 source-of-truth.
 */
import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

import { fetchApi } from '@/lib/api'

const STORAGE_KEY = 'hydra_active_brand_id'

export interface ActiveBrand {
  id: number
  name: string
  product_category: string | null
}

interface ActiveBrandContextValue {
  brands: ActiveBrand[]
  activeBrand: ActiveBrand | null
  setActiveBrandId: (id: number) => void
  loading: boolean
  refresh: () => void
}

const Ctx = createContext<ActiveBrandContextValue | null>(null)

export function ActiveBrandProvider({ children }: { children: ReactNode }) {
  const [brands, setBrands] = useState<ActiveBrand[]>([])
  const [activeId, setActiveId] = useState<number | null>(() => {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? Number(raw) : null
  })
  const [loading, setLoading] = useState(true)
  const [version, setVersion] = useState(0)

  const refresh = () => setVersion((v) => v + 1)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchApi<ActiveBrand[]>('/brands/api/list')
      .then((rows) => {
        if (cancelled) return
        const arr = Array.isArray(rows) ? rows : []
        setBrands(arr)
        // 활성 브랜드가 list 에 없으면 첫 번째로 fallback
        if (arr.length > 0 && (activeId === null || !arr.some((b) => b.id === activeId))) {
          setActiveId(arr[0].id)
          localStorage.setItem(STORAGE_KEY, String(arr[0].id))
        }
      })
      .catch(() => !cancelled && setBrands([]))
      .finally(() => !cancelled && setLoading(false))
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [version])

  const setActiveBrandId = (id: number) => {
    setActiveId(id)
    localStorage.setItem(STORAGE_KEY, String(id))
  }

  const activeBrand = brands.find((b) => b.id === activeId) ?? null

  return (
    <Ctx.Provider
      value={{ brands, activeBrand, setActiveBrandId, loading, refresh }}
    >
      {children}
    </Ctx.Provider>
  )
}

export function useActiveBrand(): ActiveBrandContextValue {
  const v = useContext(Ctx)
  if (!v) throw new Error('useActiveBrand must be used inside ActiveBrandProvider')
  return v
}
