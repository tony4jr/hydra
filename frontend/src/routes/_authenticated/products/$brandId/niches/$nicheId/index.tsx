import { createFileRoute } from '@tanstack/react-router'
import { TabPlaceholder } from '@/features/products/niche-tabs/placeholder'
import { labels } from '@/lib/i18n-terms'

export const Route = createFileRoute(
  '/_authenticated/products/$brandId/niches/$nicheId/',
)({
  component: () => <TabPlaceholder tabName={labels.tabOverview} subPrId='PR-4b' />,
})
