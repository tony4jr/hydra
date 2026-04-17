import { useEffect, useState } from 'react'
import { Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { fetchApi } from '@/lib/api'
import { BrandFormDialog } from './brand-form-dialog'

interface Brand {
  id: number
  name: string
  product_category: string | null
  core_message: string | null
  promo_keywords: string[] | null
  status: string
}

export default function BrandsPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [loading, setLoading] = useState(true)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<'create' | 'edit'>('create')
  const [editBrand, setEditBrand] = useState<Brand | null>(null)

  const loadBrands = () => {
    setLoading(true)
    fetchApi<Brand[]>('/brands/api/list')
      .then(setBrands)
      .catch(() => setBrands([]))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    loadBrands()
  }, [])

  const openCreate = () => {
    setDialogMode('create')
    setEditBrand(null)
    setDialogOpen(true)
  }

  const openEdit = (brand: Brand) => {
    setDialogMode('edit')
    setEditBrand(brand)
    setDialogOpen(true)
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
        <div >
          <div className='mb-5 flex flex-wrap items-center justify-between gap-2'>
            <div>
              <h2 className='text-[22px] font-bold'>브랜드</h2>
              <p className='text-muted-foreground text-[13px]'>
                AI가 제품을 이해하기 위한 브랜드 정보를 관리하세요
              </p>
            </div>
            <Button size="lg" onClick={openCreate} className='hydra-btn-press'>
              <Plus className='mr-2 h-4 w-4' /> 브랜드 추가
            </Button>
          </div>

          {loading ? (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {[1, 2, 3].map(i => (
                <Skeleton key={i} className='h-40 rounded-xl' />
              ))}
            </div>
          ) : brands.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px] mb-1'>등록된 브랜드가 없어요</p>
              <p className='text-muted-foreground/60 text-[12px] mb-4'>브랜드를 추가하면 AI가 제품에 맞는 댓글을 생성합니다</p>
              <Button onClick={openCreate} variant='outline' className='hydra-btn-press'>
                <Plus className='mr-2 h-4 w-4' /> 첫 브랜드 추가하기
              </Button>
            </div>
          ) : (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {brands.map((brand) => (
                <div
                  key={brand.id}
                  className='bg-card border border-border rounded-xl p-5 cursor-pointer hydra-card-hover'
                  onClick={() => openEdit(brand)}
                >
                  <div className='flex items-center justify-between mb-2'>
                    <h3 className='text-foreground font-semibold text-[16px]'>{brand.name}</h3>
                    {brand.product_category && (
                      <span className='hydra-tag hydra-tag-muted'>{brand.product_category}</span>
                    )}
                  </div>

                  {brand.core_message && (
                    <p className='text-muted-foreground text-[13px] mb-3 line-clamp-2'>
                      {brand.core_message}
                    </p>
                  )}

                  {brand.promo_keywords && brand.promo_keywords.length > 0 && (
                    <div className='flex flex-wrap gap-1.5'>
                      {brand.promo_keywords.slice(0, 5).map((kw, i) => (
                        <span key={i} className='hydra-tag hydra-tag-primary'>{kw}</span>
                      ))}
                      {brand.promo_keywords.length > 5 && (
                        <span className='hydra-tag hydra-tag-muted'>+{brand.promo_keywords.length - 5}</span>
                      )}
                    </div>
                  )}

                  {!brand.core_message && (!brand.promo_keywords || brand.promo_keywords.length === 0) && (
                    <p className='text-muted-foreground/50 text-[12px]'>클릭해서 브랜드 정보를 입력하세요</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </Main>

      <BrandFormDialog
        open={dialogOpen}
        onOpenChange={setDialogOpen}
        mode={dialogMode}
        brand={editBrand}
        onSuccess={loadBrands}
      />
    </>
  )
}
