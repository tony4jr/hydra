import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/features/placeholder'

export const Route = createFileRoute('/_authenticated/analytics/')({
  component: () => <PlaceholderPage title='분석' />,
})
