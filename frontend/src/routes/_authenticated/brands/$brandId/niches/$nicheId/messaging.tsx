import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute(
  '/_authenticated/brands/$brandId/niches/$nicheId/messaging',
)({
  beforeLoad: () => {
    throw redirect({ to: '/brands' })
  },
})
