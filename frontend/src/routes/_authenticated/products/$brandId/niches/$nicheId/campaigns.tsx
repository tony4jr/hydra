import { createFileRoute } from '@tanstack/react-router'
import { TabPlaceholder } from '@/features/products/niche-tabs/placeholder'
import { labels } from '@/lib/i18n-terms'

export const Route = createFileRoute(
  '/_authenticated/products/$brandId/niches/$nicheId/campaigns',
)({
  component: () => <TabPlaceholder tabName={labels.tabCampaigns} subPrId='PR-4e' />,
})
