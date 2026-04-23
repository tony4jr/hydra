import { createFileRoute } from '@tanstack/react-router'
import { AvatarManager } from '@/features/avatars/avatar-manager'

export const Route = createFileRoute('/_authenticated/avatars/')({
  component: AvatarManager,
})
