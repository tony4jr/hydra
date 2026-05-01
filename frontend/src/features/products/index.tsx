/**
 * /products — 제품 목록 (Brand list).
 *
 * PR-4a 골격. 카드 클릭 → /products/$brandId.
 * 백엔드 변경 0 (기존 /brands/api/list + PR-3c 의 useNicheCountByBrand 재사용).
 */
import { useEffect, useState } from 'react'
import { Link } from '@tanstack/react-router'

import { fetchApi } from '@/lib/api'
import { useNicheCountByBrand } from '@/hooks/use-niches'
import { labels } from '@/lib/i18n-terms'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'

interface Brand {
  id: number
  name: string
  product_category: string | null
  status: string
}

export default function ProductsPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [loading, setLoading] = useState(true)
  const nicheCountByBrand = useNicheCountByBrand()

  useEffect(() => {
    fetchApi<Brand[]>('/brands/api/list')
      .then(setBrands)
      .catch(() => setBrands([]))
      .finally(() => setLoading(false))
  }, [])

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
          <div className='mb-5'>
            <h1 className='hydra-page-h'>{labels.pageProducts}</h1>
            <p className='hydra-page-sub'>
              브랜드와 시장을 한눈에 보고 상세 페이지로 이동하세요
            </p>
          </div>

          {loading ? (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className='h-40 rounded-xl' />
              ))}
            </div>
          ) : brands.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px] mb-1'>등록된 브랜드가 없어요</p>
              <p className='text-muted-foreground/60 text-[12px]'>
                브랜드 페이지에서 추가하세요
              </p>
            </div>
          ) : (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {brands.map((brand) => {
                const nicheCount = nicheCountByBrand[brand.id] ?? 0
                return (
                  <Link
                    key={brand.id}
                    to='/products/$brandId'
                    params={{ brandId: String(brand.id) }}
                    className='bg-card border border-border rounded-xl p-5 hydra-card-hover'
                  >
                    <div className='flex items-center justify-between mb-2'>
                      <h3 className='text-foreground font-semibold text-[16px]'>{brand.name}</h3>
                      <div className='flex items-center gap-1.5'>
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
    </>
  )
}
