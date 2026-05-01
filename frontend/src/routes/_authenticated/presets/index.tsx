import { createFileRoute } from '@tanstack/react-router'
import CommentPresetsPage from '@/features/comment-presets'

export const Route = createFileRoute('/_authenticated/presets/')({
  component: CommentPresetsPage,
})
