import { useEffect, useState } from 'react'
import { Pencil, Plus } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
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
  tone_guide: string | null
  promo_keywords: string[] | null
  target_keywords: string[] | null
  selected_presets: string[] | null
  status: string
  weekly_campaign_target: number
  auto_campaign_enabled: boolean
  keywords?: string[]
}

export default function BrandsPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [dialogOpen, setDialogOpen] = useState(false)
  const [dialogMode, setDialogMode] = useState<'create' | 'edit'>('create')
  const [editBrand, setEditBrand] = useState<Brand | null>(null)

  const loadBrands = () => {
    fetchApi<Brand[]>('/brands/api/list')
      .then(setBrands)
      .catch(() => setBrands([]))
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
        <div className='mb-2 flex flex-wrap items-center justify-between space-y-2'>
          <div>
            <h2 className='text-2xl font-bold tracking-tight'>브랜드</h2>
            <p className='text-muted-foreground'>
              브랜드/상품 관리, 홍보 키워드, AI 가이드
            </p>
          </div>
          <Button onClick={openCreate}>
            <Plus className='mr-2 h-4 w-4' /> 브랜드 추가
          </Button>
        </div>

        <div className='grid gap-4 md:grid-cols-2 lg:grid-cols-3'>
          {brands.length === 0 ? (
            <Card className='col-span-full'>
              <CardContent className='flex items-center justify-center py-10'>
                <p className='text-muted-foreground'>
                  등록된 브랜드가 없습니다. 서버 연결 후 표시됩니다.
                </p>
              </CardContent>
            </Card>
          ) : (
            brands.map((brand) => (
              <Card
                key={brand.id}
                className='cursor-pointer transition-colors hover:border-primary'
              >
                <CardHeader className='flex flex-row items-center justify-between space-y-0 pb-2'>
                  <CardTitle className='text-lg'>{brand.name}</CardTitle>
                  <div className='flex items-center gap-2'>
                    <Button
                      variant='ghost'
                      size='icon'
                      className='h-7 w-7'
                      onClick={(e) => {
                        e.stopPropagation()
                        openEdit(brand)
                      }}
                    >
                      <Pencil className='h-3.5 w-3.5' />
                    </Button>
                    <Badge
                      variant={
                        brand.status === 'active' ? 'default' : 'secondary'
                      }
                    >
                      {brand.status}
                    </Badge>
                  </div>
                </CardHeader>
                <CardContent>
                  <p className='text-sm text-muted-foreground'>
                    {brand.product_category || '카테고리 미설정'}
                  </p>
                  <div className='mt-3 flex items-center gap-4 text-sm'>
                    <span>
                      주간 목표:{' '}
                      <strong>{brand.weekly_campaign_target || '-'}</strong>
                    </span>
                    {brand.auto_campaign_enabled && (
                      <Badge variant='outline' className='text-xs'>
                        자동
                      </Badge>
                    )}
                  </div>
                  {brand.keywords && brand.keywords.length > 0 && (
                    <div className='mt-3'>
                      <p className='mb-1 text-xs font-medium text-muted-foreground'>
                        키워드
                      </p>
                      <div className='flex flex-wrap gap-1'>
                        {brand.keywords.map((kw, i) => (
                          <Badge key={i} variant='outline' className='text-xs'>
                            {kw}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}
                </CardContent>
              </Card>
            ))
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
