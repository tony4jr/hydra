import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/workers/ip-monitor')({
  beforeLoad: () => {
    throw redirect({ to: '/workers' })
  },
})
