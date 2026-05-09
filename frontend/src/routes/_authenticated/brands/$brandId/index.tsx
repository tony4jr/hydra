import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/brands/$brandId/')({
  beforeLoad: () => {
    throw redirect({ to: '/brands' })
  },
})
