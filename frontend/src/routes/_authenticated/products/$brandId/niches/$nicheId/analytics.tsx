import { createFileRoute, useParams } from '@tanstack/react-router'
import { AnalyticsTab } from '@/features/products/niche-tabs/analytics'

function AnalyticsRoute() {
  const { nicheId } = useParams({
    from: '/_authenticated/products/$brandId/niches/$nicheId/analytics',
  })
  return <AnalyticsTab nicheId={nicheId} />
}

export const Route = createFileRoute(
  '/_authenticated/products/$brandId/niches/$nicheId/analytics',
)({
  component: AnalyticsRoute,
})
