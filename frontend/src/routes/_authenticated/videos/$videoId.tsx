import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/videos/$videoId')({
  beforeLoad: () => {
    throw redirect({ to: '/videos' })
  },
})
