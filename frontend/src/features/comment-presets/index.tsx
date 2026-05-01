/**
 * /presets — 댓글 트리 프리셋 라이브러리.
 * 카드 클릭 → /presets/$presetId 편집 페이지 (PR-8e).
 */
import { useState, type MouseEvent } from 'react'
import { Link } from '@tanstack/react-router'
import { Plus, Copy, Trash2, Pencil } from 'lucide-react'

import { useCommentPresets } from '@/hooks/use-comment-presets'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { Skeleton } from '@/components/ui/skeleton'
import { Button } from '@/components/ui/button'

export default function CommentPresetsPage() {
  const { presets, loading, create, clone, remove } = useCommentPresets()
  const [creating, setCreating] = useState(false)
  const [name, setName] = useState('')

  const handleCreate = async () => {
    if (!name.trim()) return
    await create({ name: name.trim() })
    setName('')
    setCreating(false)
  }

  const stop = (e: MouseEvent) => {
    e.preventDefault()
    e.stopPropagation()
  }

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div>
          <div className='mb-5 flex items-center justify-between'>
            <div>
              <h1 className='hydra-page-h'>프리셋</h1>
              <p className='hydra-page-sub'>댓글 트리 양식 라이브러리 (전역, 모든 브랜드 공유)</p>
            </div>
            <Button onClick={() => setCreating(true)} className='hydra-btn-press'>
              <Plus className='mr-1 h-4 w-4' /> 새 프리셋
            </Button>
          </div>

          {creating && (
            <div className='bg-card border border-border rounded-xl p-4 mb-3 flex gap-2'>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder='프리셋 이름'
                className='flex-1 bg-background border border-border rounded-md text-[13px] px-2 py-1.5'
              />
              <Button size='sm' onClick={handleCreate} disabled={!name.trim()}>
                만들기
              </Button>
              <Button size='sm' variant='ghost' onClick={() => setCreating(false)}>
                취소
              </Button>
            </div>
          )}

          {loading ? (
            <Skeleton className='h-64 rounded-xl' />
          ) : presets.length === 0 ? (
            <div className='bg-card border border-border rounded-xl py-16 text-center'>
              <p className='text-muted-foreground text-[14px]'>등록된 프리셋이 없어요</p>
            </div>
          ) : (
            <div className='grid gap-3 md:grid-cols-2 lg:grid-cols-3'>
              {presets.map((p) => (
                <Link
                  key={p.id}
                  to='/presets/$presetId'
                  params={{ presetId: String(p.id) }}
                  className='bg-card border border-border rounded-xl p-5 hydra-card-hover block'
                >
                  <div className='flex items-start justify-between mb-2 gap-2'>
                    <h3 className='text-foreground font-semibold text-[16px] truncate'>{p.name}</h3>
                    {p.is_default && (
                      <span className='hydra-tag hydra-tag-muted shrink-0'>기본</span>
                    )}
                  </div>
                  {p.description && (
                    <p className='text-muted-foreground text-[12px] mb-3 line-clamp-2'>
                      {p.description}
                    </p>
                  )}
                  <p className='text-muted-foreground/70 text-[11px] mb-3'>
                    슬롯 {p.slot_count}개 · 사용 중 {p.used_by_niches} 타겟
                  </p>
                  <div className='flex items-center gap-1.5'>
                    <span className='inline-flex items-center gap-1 text-primary text-[12px] font-medium'>
                      <Pencil className='h-3.5 w-3.5' /> 편집
                    </span>
                    <Button
                      size='sm'
                      variant='ghost'
                      onClick={(e) => {
                        stop(e)
                        clone(p.id)
                      }}
                      title='복제'
                      className='ml-auto'
                    >
                      <Copy className='h-3.5 w-3.5' />
                    </Button>
                    <Button
                      size='sm'
                      variant='ghost'
                      onClick={(e) => {
                        stop(e)
                        if (confirm(`"${p.name}" 프리셋을 삭제할까요?`)) {
                          remove(p.id, p.is_default)
                        }
                      }}
                      title='삭제'
                    >
                      <Trash2 className='h-3.5 w-3.5' />
                    </Button>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </Main>
    </>
  )
}
