import { createFileRoute } from '@tanstack/react-router'
import WorkerErrorsPage from '@/features/workers/errors-page'

export const Route = createFileRoute('/_authenticated/workers/errors')({
  component: WorkerErrorsPage,
})
