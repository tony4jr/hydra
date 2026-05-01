import { createFileRoute } from '@tanstack/react-router'
import VideoTimelinePage from '@/features/videos/timeline'

export const Route = createFileRoute('/_authenticated/videos/$videoId')({
  component: VideoTimelinePage,
})
