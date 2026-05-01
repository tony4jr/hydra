import { createFileRoute } from '@tanstack/react-router'
import VideosPage from '@/features/videos'

export const Route = createFileRoute('/_authenticated/videos/')({
  component: VideosPage,
})
