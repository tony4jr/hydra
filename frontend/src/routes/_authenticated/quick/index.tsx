import { createFileRoute } from '@tanstack/react-router'
import { QuickWork } from '@/features/quick'

export const Route = createFileRoute('/_authenticated/quick/')({
  component: QuickWork,
})
