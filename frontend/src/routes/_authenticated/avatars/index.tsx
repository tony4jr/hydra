import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/avatars/')({
  beforeLoad: () => {
    throw redirect({ to: '/accounts' })
  },
})
