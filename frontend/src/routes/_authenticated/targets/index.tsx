import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/features/placeholder'

export const Route = createFileRoute('/_authenticated/targets/')({
  component: () => <PlaceholderPage title='타겟' />,
})
