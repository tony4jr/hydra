/**
 * /brands/$brandId — Brand 디테일 (Niche 리스트).
 *
 * PR-4a 골격. Niche 카드 클릭 → /brands/$brandId/niches/$nicheId.
 * 백엔드: PR-3b 의 /api/admin/niches?brand_id=X 사용.
 */
import { Link, useParams } from '@tanstack/react-router'

import { useNiches } from '@/hooks/use-niches'
import { useSyncActiveBrand } from '@/hooks/use-sync-active-brand'
import { labels } from '@/lib/i18n-terms'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'

export default function BrandDetailPage() {
  const { brandId } = useParams({ from: '/_authenticated/brands/$brandId/' })
  const brandIdNum = Number(brandId)
  useSyncActiveBrand(brandIdNum)
  const { niches, loading } = useNiches(brandIdNum)

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
            <Link to='/brands' className='text-muted-foreground text-[12px] hover:underline'>
              ← {labels.pageProducts}
            </Link>
            <h1 className='hydra-page-h mt-1'>{labels.niche} 목록</h1>
            <p className='hydra-page-sub'>
              브랜드의 시장을 선택해 5탭 (개요·수집·메시지·캠페인·분석) 으로 이동합니다
            </p>
            <div className='mt-3 flex flex-wrap gap-2 text-[12px]'>
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
          </div>

          {loading ? (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {[1, 2].map((i) => (
                <Skeleton key={i} className='h-32 rounded-xl' />
              ))}
            </div>
          ) : niches.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px] mb-1'>{labels.niche}이 없어요</p>
              <p className='text-muted-foreground/60 text-[12px]'>
                후속 PR (시장 추가 모달) 에서 생성 가능합니다
              </p>
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
                    {niche.market_definition || '시장 정의가 비어있어요'}
                  </p>
                  <p className='text-muted-foreground/60 text-[11px] mt-2'>
                    수집 깊이 {niche.collection_depth} · 임계값 {niche.embedding_threshold}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </div>
      </Main>
    </>
  )
}
