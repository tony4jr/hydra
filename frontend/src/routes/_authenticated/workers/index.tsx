import { createFileRoute } from '@tanstack/react-router'
import { WorkersCommex } from '@/features/workers-commex'

export const Route = createFileRoute('/_authenticated/workers/')({
  component: WorkersCommex,
})
