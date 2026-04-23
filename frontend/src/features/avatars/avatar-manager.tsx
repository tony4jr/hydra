import { useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Upload, Trash2, ChevronRight, ChevronDown } from 'lucide-react'
import axios from 'axios'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Card } from '@/components/ui/card'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'
import { cn } from '@/lib/utils'
import { toast } from 'sonner'

const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

type TreeNode = {
  [key: string]: TreeNode | string[]
  __files__?: string[] | any
}

async function fetchTree(): Promise<TreeNode> {
  const r = await axios.get<TreeNode>(`${API_BASE}/api/admin/avatars/list`)
  return r.data
}

async function uploadFile(category: string, file: File) {
  const fd = new FormData()
  fd.append('category', category)
  fd.append('file', file)
  return (await axios.post(`${API_BASE}/api/admin/avatars/upload`, fd)).data
}

async function uploadZip(category: string, file: File) {
  const fd = new FormData()
  fd.append('category', category)
  fd.append('file', file)
  return (await axios.post(`${API_BASE}/api/admin/avatars/upload-zip`, fd))
    .data
}

async function deleteFile(path: string) {
  return (
    await axios.delete(
      `${API_BASE}/api/admin/avatars/${encodeURI(path).replace(/%2F/gi, '/')}`,
    )
  ).data
}

// ── upload zone ──
function UploadZone({
  category,
  onDone,
}: {
  category: string
  onDone: () => void
}) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  const mutation = useMutation({
    mutationFn: async (files: FileList) => {
      let ok = 0
      let fail = 0
      for (const f of Array.from(files)) {
        try {
          if (f.name.toLowerCase().endsWith('.zip')) {
            await uploadZip(category, f)
          } else {
            await uploadFile(category, f)
          }
          ok++
        } catch {
          fail++
        }
      }
      return { ok, fail }
    },
    onSuccess: ({ ok, fail }) => {
      if (ok > 0) toast.success(`업로드 완료 ${ok}건`)
      if (fail > 0) toast.error(`실패 ${fail}건`)
      onDone()
    },
  })

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault()
        setDragOver(true)
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(e) => {
        e.preventDefault()
        setDragOver(false)
        if (!category) {
          toast.error('카테고리를 먼저 선택/입력하세요')
          return
        }
        if (e.dataTransfer.files?.length) {
          mutation.mutate(e.dataTransfer.files)
        }
      }}
      onClick={() => inputRef.current?.click()}
      className={cn(
        'cursor-pointer rounded-lg border-2 border-dashed p-8 text-center transition-colors',
        dragOver ? 'border-primary bg-primary/5' : 'border-border bg-muted/20',
        !category && 'opacity-60',
      )}
    >
      <Upload className='mx-auto mb-2 h-6 w-6 text-muted-foreground' />
      <p className='text-sm'>이미지 파일을 드래그하거나 클릭</p>
      <p className='mt-1 text-xs text-muted-foreground'>
        .png / .jpg / .jpeg / .webp · .zip 일괄 업로드 지원
      </p>
      <input
        ref={inputRef}
        type='file'
        multiple
        accept='image/*,application/zip'
        className='hidden'
        onChange={(e) => {
          if (e.target.files?.length) mutation.mutate(e.target.files)
          e.target.value = ''
        }}
      />
      {mutation.isPending && (
        <p className='mt-3 text-sm text-primary'>업로드 중…</p>
      )}
    </div>
  )
}

// ── tree view ──
type FlatFile = { path: string; name: string }

function flattenTree(tree: TreeNode, prefix = ''): FlatFile[] {
  const out: FlatFile[] = []
  for (const [key, val] of Object.entries(tree)) {
    if (key === '__files__' && Array.isArray(val)) {
      for (const f of val) {
        out.push({ path: `${prefix}/${f}`.replace(/^\//, ''), name: f })
      }
    } else if (val && typeof val === 'object' && !Array.isArray(val)) {
      out.push(...flattenTree(val as TreeNode, `${prefix}/${key}`))
    }
  }
  return out
}

function TreeBranch({
  tree,
  prefix = '',
  depth = 0,
  onDelete,
}: {
  tree: TreeNode
  prefix?: string
  depth?: number
  onDelete: (path: string) => void
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({})

  const subdirs = Object.keys(tree).filter(
    (k) => k !== '__files__' && typeof tree[k] === 'object',
  )
  const files = (tree.__files__ as string[] | undefined) || []

  return (
    <ul className={cn('space-y-0.5', depth > 0 && 'ml-4 border-l pl-2')}>
      {subdirs.map((dir) => {
        const isOpen = open[dir] !== false
        return (
          <li key={dir}>
            <button
              type='button'
              onClick={() => setOpen((s) => ({ ...s, [dir]: !isOpen }))}
              className='flex w-full items-center gap-1 rounded px-1 py-1 text-sm hover:bg-muted/50'
            >
              {isOpen ? (
                <ChevronDown className='h-3.5 w-3.5 text-muted-foreground' />
              ) : (
                <ChevronRight className='h-3.5 w-3.5 text-muted-foreground' />
              )}
              <span className='font-medium'>{dir}/</span>
              <span className='ml-1 text-xs text-muted-foreground'>
                ({flattenTree({ [dir]: tree[dir] } as TreeNode).length})
              </span>
            </button>
            {isOpen && (
              <TreeBranch
                tree={tree[dir] as TreeNode}
                prefix={prefix ? `${prefix}/${dir}` : dir}
                depth={depth + 1}
                onDelete={onDelete}
              />
            )}
          </li>
        )
      })}
      {files.map((f) => {
        const path = prefix ? `${prefix}/${f}` : f
        return (
          <li
            key={f}
            className='flex items-center justify-between rounded px-1 py-0.5 text-sm hover:bg-muted/40'
          >
            <span className='truncate font-mono text-xs'>{f}</span>
            <Button
              size='sm'
              variant='ghost'
              className='h-6 w-6 p-0 text-muted-foreground hover:text-destructive'
              onClick={() => onDelete(path)}
              title='삭제'
            >
              <Trash2 className='h-3.5 w-3.5' />
            </Button>
          </li>
        )
      })}
      {subdirs.length === 0 && files.length === 0 && depth === 0 && (
        <li className='py-6 text-center text-sm text-muted-foreground'>
          아직 등록된 아바타가 없습니다
        </li>
      )}
    </ul>
  )
}

// ── main ──
export function AvatarManager() {
  const qc = useQueryClient()
  const [category, setCategory] = useState('female/20s')
  const { data: tree, isLoading } = useQuery({
    queryKey: ['avatars-tree'],
    queryFn: fetchTree,
  })

  const del = useMutation({
    mutationFn: (path: string) => deleteFile(path),
    onSuccess: () => {
      toast.success('삭제됨')
      qc.invalidateQueries({ queryKey: ['avatars-tree'] })
    },
    onError: (e) => toast.error((e as Error).message || '삭제 실패'),
  })

  const totalFiles = useMemo(() => {
    if (!tree) return 0
    return flattenTree(tree).length
  }, [tree])

  return (
    <>
      <Header fixed>
        <div className='ml-auto flex items-center space-x-4'>
          <ThemeSwitch />
          <ProfileDropdown />
        </div>
      </Header>
      <Main>
        <div className='space-y-5'>
          <div>
            <h1 className='text-2xl font-bold'>아바타</h1>
            <p className='text-sm text-muted-foreground'>
              총 {totalFiles}개 등록 · 워커가 계정 생성 시 사용
            </p>
          </div>

          <Card className='space-y-4 p-4'>
            <div className='space-y-2'>
              <Label htmlFor='category'>업로드 카테고리</Label>
              <Input
                id='category'
                value={category}
                onChange={(e) => setCategory(e.target.value)}
                placeholder='female/20s, male/30s, object/flower …'
                className='font-mono'
              />
              <p className='text-xs text-muted-foreground'>
                슬래시 (/) 로 중첩 가능. 경로 traversal 은 자동 차단됩니다.
              </p>
            </div>
            <UploadZone
              category={category}
              onDone={() =>
                qc.invalidateQueries({ queryKey: ['avatars-tree'] })
              }
            />
          </Card>

          <Card className='p-4'>
            <h2 className='mb-3 text-sm font-semibold'>저장된 파일</h2>
            {isLoading ? (
              <p className='py-6 text-center text-sm text-muted-foreground'>
                불러오는 중…
              </p>
            ) : (
              <TreeBranch
                tree={tree || {}}
                onDelete={(p) => {
                  if (window.confirm(`삭제하시겠습니까?\n${p}`)) del.mutate(p)
                }}
              />
            )}
          </Card>
        </div>
      </Main>
    </>
  )
}
