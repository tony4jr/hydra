import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/workers/errors')({
  beforeLoad: () => {
    throw redirect({ to: '/workers' })
  },
})
