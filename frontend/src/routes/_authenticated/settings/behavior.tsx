import { createFileRoute } from '@tanstack/react-router'
import { SettingsBehavior } from '@/features/settings/behavior'

export const Route = createFileRoute('/_authenticated/settings/behavior')({
  component: SettingsBehavior,
})
