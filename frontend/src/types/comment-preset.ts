export interface CommentPresetSummary {
  id: number
  name: string
  description: string | null
  is_global: boolean
  is_default: boolean
  slot_count: number
  used_by_niches: number
  created_at: string | null
  updated_at: string | null
}

export type CommentSlotLength = 'short' | 'medium' | 'long'
export type CommentSlotEmoji = 'none' | 'sometimes' | 'often'
export type CommentSlotDistribution = 'adaptive' | 'burst' | 'spread' | 'slow'

export interface CommentTreeSlot {
  id: number
  slot_label: string
  reply_to_slot_label: string | null
  same_account_as_slot_label: string | null
  position: number
  text_template: string | null
  // PR-D: 의도 설명형 슬롯 필드
  intent: string | null
  tone_anchor: string | null  // JSON list (string[]) 직렬화
  mention_brand: boolean
  mention_solution: boolean
  length: CommentSlotLength
  emoji: CommentSlotEmoji
  ai_variation: number
  like_min: number
  like_max: number
  like_distribution: CommentSlotDistribution
}

export interface CommentPresetDetail extends CommentPresetSummary {
  slots: CommentTreeSlot[]
}
