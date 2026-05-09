import { createFileRoute, redirect } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/presets/$presetId')({
  beforeLoad: () => {
    throw redirect({ to: '/presets' })
  },
})
