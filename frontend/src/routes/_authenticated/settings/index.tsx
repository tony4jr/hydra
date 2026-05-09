import { createFileRoute } from '@tanstack/react-router'
import { SettingsCommex } from '@/features/settings-commex'

export const Route = createFileRoute('/_authenticated/settings/')({
  component: SettingsCommex,
})
