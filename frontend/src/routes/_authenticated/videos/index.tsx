import { createFileRoute } from '@tanstack/react-router'
import { VideosCommex } from '@/features/videos-commex'

export const Route = createFileRoute('/_authenticated/videos/')({
  component: VideosCommex,
})
