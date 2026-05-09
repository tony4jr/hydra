import { createFileRoute } from '@tanstack/react-router'
import { PresetsCommex } from '@/features/presets-commex'

export const Route = createFileRoute('/_authenticated/presets/')({
  component: PresetsCommex,
})
