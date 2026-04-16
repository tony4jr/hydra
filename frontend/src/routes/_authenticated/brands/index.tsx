import { createFileRoute } from '@tanstack/react-router'
import { PlaceholderPage } from '@/features/placeholder'

export const Route = createFileRoute('/_authenticated/brands/')({
  component: () => <PlaceholderPage title='브랜드' />,
})
