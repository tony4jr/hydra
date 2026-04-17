import { createFileRoute } from '@tanstack/react-router'
import { SettingsPresets } from '@/features/settings/presets'

export const Route = createFileRoute('/_authenticated/settings/presets')({
  component: SettingsPresets,
})
