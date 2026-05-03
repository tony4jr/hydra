/**
 * /brands/$brandId — Brand 디테일 (타겟 리스트).
 */
import { useState } from 'react'
import { Link, useParams } from '@tanstack/react-router'
import { Plus } from 'lucide-react'

import { useNiches } from '@/hooks/use-niches'
import { useSyncActiveBrand } from '@/hooks/use-sync-active-brand'
import { labels } from '@/lib/i18n-terms'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { NicheCreateDialog } from './niche-create-dialog'

export default function BrandDetailPage() {
  const { brandId } = useParams({ from: '/_authenticated/brands/$brandId/' })
  const brandIdNum = Number(brandId)
  useSyncActiveBrand(brandIdNum)
  const { niches, loading, refresh } = useNiches(brandIdNum)
  const [createOpen, setCreateOpen] = useState(false)

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
              <Link to='/brands' className='text-muted-foreground text-[12px] hover:underline'>
                ← {labels.pageProducts}
              </Link>
              <h1 className='hydra-page-h mt-1'>타겟</h1>
              <p className='hydra-page-sub'>이 브랜드가 노릴 시장(타겟)을 추가·관리합니다</p>
            </div>
            <Button onClick={() => setCreateOpen(true)} className='hydra-btn-press'>
              <Plus className='mr-2 h-4 w-4' /> 타겟 추가
            </Button>
          </div>

          <div className='mb-5 flex flex-wrap gap-2 text-[12px]'>
            <Link
              to='/targets'
              className='rounded-md border border-border px-2.5 py-1 hover:bg-muted/50'
            >
              영상 풀 · 수집 →
            </Link>
            <Link
              to='/campaigns'
              className='rounded-md border border-border px-2.5 py-1 hover:bg-muted/50'
            >
              캠페인 →
            </Link>
            <Link
              to='/tasks'
              className='rounded-md border border-border px-2.5 py-1 hover:bg-muted/50'
            >
              작업 큐 →
            </Link>
          </div>

          {loading ? (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {[1, 2].map((i) => (
                <Skeleton key={i} className='h-32 rounded-xl' />
              ))}
            </div>
          ) : niches.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px] mb-3'>아직 타겟이 없어요</p>
              <Button onClick={() => setCreateOpen(true)} className='hydra-btn-press'>
                <Plus className='mr-2 h-4 w-4' /> 첫 타겟 추가
              </Button>
            </div>
          ) : (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {niches.map((niche) => (
                <Link
                  key={niche.id}
                  to='/brands/$brandId/niches/$nicheId'
                  params={{ brandId, nicheId: String(niche.id) }}
                  className='bg-card border border-border rounded-xl p-5 hydra-card-hover'
                >
                  <div className='flex items-center justify-between mb-2'>
                    <h3 className='text-foreground font-semibold text-[16px]'>{niche.name}</h3>
                    <span className='hydra-tag hydra-tag-muted'>{niche.state}</span>
                  </div>
                  <p className='text-muted-foreground text-[12px] line-clamp-2'>
                    {niche.market_definition || '오디언스를 채워보세요'}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </div>
      </Main>

      <NicheCreateDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        brandId={brandIdNum}
        onSuccess={() => {
          setCreateOpen(false)
          refresh()
        }}
      />
    </>
  )
}
