import { createFileRoute } from '@tanstack/react-router'
import CommentPresetDetailPage from '@/features/comment-presets/preset-detail'

export const Route = createFileRoute('/_authenticated/presets/$presetId')({
  component: CommentPresetDetailPage,
})
