import { createFileRoute, useParams } from '@tanstack/react-router'
import { CampaignsTab } from '@/features/products/niche-tabs/campaigns'

function CampaignsRoute() {
  const { nicheId } = useParams({
    from: '/_authenticated/products/$brandId/niches/$nicheId/campaigns',
  })
  return <CampaignsTab nicheId={nicheId} />
}

export const Route = createFileRoute(
  '/_authenticated/products/$brandId/niches/$nicheId/campaigns',
)({
  component: CampaignsRoute,
})
