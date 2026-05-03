import { createFileRoute, useParams } from '@tanstack/react-router'
import { MessagingTab } from '@/features/products/niche-tabs/messaging'

function MessagingRoute() {
  const { nicheId } = useParams({
    from: '/_authenticated/brands/$brandId/niches/$nicheId/messaging',
  })
  return <MessagingTab nicheId={nicheId} />
}

export const Route = createFileRoute(
  '/_authenticated/brands/$brandId/niches/$nicheId/messaging',
)({
  component: MessagingRoute,
})
