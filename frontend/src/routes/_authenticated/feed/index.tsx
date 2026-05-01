import { createFileRoute } from '@tanstack/react-router'
import FeedPage from '@/features/feed'

export const Route = createFileRoute('/_authenticated/feed/')({
  component: FeedPage,
})
