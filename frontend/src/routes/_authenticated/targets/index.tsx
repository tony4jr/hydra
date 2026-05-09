import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/targets/')({
  beforeLoad: () => {
    throw redirect({ to: '/queue' })
  },
})
