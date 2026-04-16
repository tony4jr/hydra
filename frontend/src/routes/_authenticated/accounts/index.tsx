import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/features/placeholder'

export const Route = createFileRoute('/_authenticated/accounts/')({
  component: () => <PlaceholderPage title='계정' />,
})
