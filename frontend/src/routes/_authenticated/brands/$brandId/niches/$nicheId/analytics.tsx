import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute(
  '/_authenticated/brands/$brandId/niches/$nicheId/analytics',
)({
  beforeLoad: () => {
    throw redirect({ to: '/analytics' })
  },
})
