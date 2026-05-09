import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute(
  '/_authenticated/brands/$brandId/niches/$nicheId/campaigns',
)({
  beforeLoad: () => {
    throw redirect({ to: '/campaigns' })
  },
})
