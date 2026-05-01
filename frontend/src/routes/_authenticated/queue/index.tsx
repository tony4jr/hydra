import { createFileRoute } from '@tanstack/react-router'
import QueuePage from '@/features/queue'

export const Route = createFileRoute('/_authenticated/queue/')({
  component: QueuePage,
})
