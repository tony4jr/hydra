import { createFileRoute, useParams } from '@tanstack/react-router'
import { OverviewTab } from '@/features/products/niche-tabs/overview'

function OverviewRoute() {
  const { nicheId } = useParams({
    from: '/_authenticated/products/$brandId/niches/$nicheId/',
  })
  return <OverviewTab nicheId={nicheId} />
}

export const Route = createFileRoute(
  '/_authenticated/products/$brandId/niches/$nicheId/',
)({
  component: OverviewRoute,
})
