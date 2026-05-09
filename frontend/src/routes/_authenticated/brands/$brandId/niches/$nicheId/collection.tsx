import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute(
  '/_authenticated/brands/$brandId/niches/$nicheId/collection',
)({
  beforeLoad: () => {
    throw redirect({ to: '/videos' })
  },
})
