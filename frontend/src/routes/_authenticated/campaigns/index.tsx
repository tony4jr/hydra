import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/features/placeholder'

export const Route = createFileRoute('/_authenticated/campaigns/')({
  component: () => <PlaceholderPage title='캠페인' />,
})
