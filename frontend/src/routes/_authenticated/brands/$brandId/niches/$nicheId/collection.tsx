import { createFileRoute, useParams } from '@tanstack/react-router'
import { CollectionTab } from '@/features/products/niche-tabs/collection'

function CollectionRoute() {
  const { nicheId } = useParams({
    from: '/_authenticated/brands/$brandId/niches/$nicheId/collection',
  })
  return <CollectionTab nicheId={nicheId} />
}

export const Route = createFileRoute(
  '/_authenticated/brands/$brandId/niches/$nicheId/collection',
)({
  component: CollectionRoute,
})
