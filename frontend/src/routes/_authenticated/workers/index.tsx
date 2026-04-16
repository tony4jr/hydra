import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/features/placeholder'

export const Route = createFileRoute('/_authenticated/workers/')({
  component: () => <PlaceholderPage title='워커' />,
})
