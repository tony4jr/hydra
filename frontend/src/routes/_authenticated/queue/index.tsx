import { createFileRoute } from '@tanstack/react-router'
import { QueueCommex } from '@/features/queue-commex'

export const Route = createFileRoute('/_authenticated/queue/')({
  component: QueueCommex,
})
