import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/errors/$error')({
  beforeLoad: () => {
    throw redirect({ to: '/audit' })
  },
})
