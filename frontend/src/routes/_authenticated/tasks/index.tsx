import { createFileRoute } from '@tanstack/react-router'
import TasksQueuePage from '@/features/tasks-queue'

export const Route = createFileRoute('/_authenticated/tasks/')({
  component: TasksQueuePage,
})
