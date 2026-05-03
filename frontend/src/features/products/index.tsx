/**
 * /brands — 제품 목록 (Brand list).
 *
 * 카드 클릭 → /brands/$brandId 디테일.
 * 카드 안의 편집 버튼은 stopPropagation 으로 nav 차단.
 * 편집·삭제는 BrandFormDialog (기존 /brands 페이지 패턴 재사용).
 */
import { useEffect, useState, type MouseEvent } from 'react'
import { Link } from '@tanstack/react-router'
import { Pencil, Plus } from 'lucide-react'

import { fetchApi } from '@/lib/api'
import { useNicheCountByBrand } from '@/hooks/use-niches'
import { labels } from '@/lib/i18n-terms'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { BrandFormDialog } from '@/features/brands/brand-form-dialog'

interface Brand {
  id: number
  name: string
  product_category: string | null
  core_message: string | null
  promo_keywords: string[] | null
  status: string
  collection_depth?: string
  longtail_count?: number
  preset_video_limit?: number
}

export default function ProductsPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [loading, setLoading] = useState(true)
  const [editBrand, setEditBrand] = useState<Brand | null>(null)
  const [createOpen, setCreateOpen] = useState(false)
  const nicheCountByBrand = useNicheCountByBrand()

  const loadBrands = () => {
    setLoading(true)
    fetchApi<Array<{ id: number; name: string; product_category: string | null; status: string }>>(
      '/brands/api/list',
    )
      .then((rows) =>
        setBrands(
          rows.map((r) => ({
            ...r,
            core_message: null,
            promo_keywords: null,
          })),
        ),
      )
      .catch(() => setBrands([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadBrands()
  }, [])

  const openEdit = (e: MouseEvent, brand: Brand) => {
    e.preventDefault()
    e.stopPropagation()
    setEditBrand(brand)
  }

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div>
          <div className='mb-5 flex flex-wrap items-start justify-between gap-2'>
            <div>
              <h1 className='hydra-page-h'>{labels.pageProducts}</h1>
              <p className='hydra-page-sub'>
                브랜드와 시장을 한눈에 보고 상세 페이지로 이동하세요
              </p>
            </div>
            <Button onClick={() => setCreateOpen(true)} className='hydra-btn-press'>
              <Plus className='mr-2 h-4 w-4' /> 브랜드 추가
            </Button>
          </div>

          {loading ? (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className='h-40 rounded-xl' />
              ))}
            </div>
          ) : brands.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px] mb-3'>등록된 브랜드가 없어요</p>
              <Button onClick={() => setCreateOpen(true)} className='hydra-btn-press'>
                <Plus className='mr-2 h-4 w-4' /> 첫 브랜드 추가
              </Button>
            </div>
          ) : (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {brands.map((brand) => {
                const nicheCount = nicheCountByBrand[brand.id] ?? 0
                return (
                  <Link
                    key={brand.id}
                    to='/brands/$brandId'
                    params={{ brandId: String(brand.id) }}
                    className='bg-card border border-border rounded-xl p-5 hydra-card-hover relative'
                  >
                    <div className='flex items-start justify-between mb-2 gap-2'>
                      <h3 className='text-foreground font-semibold text-[16px] truncate'>
                        {brand.name}
                      </h3>
                      <button
                        type='button'
                        onClick={(e) => openEdit(e, brand)}
                        aria-label='편집'
                        className='inline-flex items-center justify-center w-7 h-7 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted/60 transition-colors shrink-0'
                      >
                        <Pencil className='w-3.5 h-3.5' />
                      </button>
                    </div>
                    <div className='flex flex-wrap gap-1.5 mb-3'>
                      {nicheCount > 0 ? (
                        <span className='hydra-tag hydra-tag-primary'>
                          {labels.niche} {nicheCount}개
                        </span>
                      ) : (
                        <span className='hydra-tag hydra-tag-muted'>{labels.niche} 없음</span>
                      )}
                      {brand.product_category && (
                        <span className='hydra-tag hydra-tag-muted'>{brand.product_category}</span>
                      )}
                    </div>
                    <p className='text-muted-foreground/60 text-[12px]'>
                      클릭해서 시장 목록 보기
                    </p>
                  </Link>
                )
              })}
            </div>
          )}
        </div>
      </Main>

      <BrandFormDialog
        open={editBrand !== null}
        onOpenChange={(open) => {
          if (!open) setEditBrand(null)
        }}
        mode='edit'
        brand={editBrand}
        onSuccess={() => {
          setEditBrand(null)
          loadBrands()
        }}
      />

      <BrandFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        mode='create'
        brand={null}
        onSuccess={() => {
          setCreateOpen(false)
          loadBrands()
        }}
      />
    </>
  )
}
