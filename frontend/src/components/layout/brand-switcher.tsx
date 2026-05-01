/**
 * 사이드바 최상단 브랜드 스위처 (PR-8a).
 *
 * 기존 TeamSwitcher 자리. 활성 브랜드 표시 + 드롭다운 + 신규 브랜드.
 */
import { ChevronsUpDown, Plus, Boxes } from 'lucide-react'
import { useState } from 'react'

import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  useSidebar,
} from '@/components/ui/sidebar'
import { useActiveBrand } from '@/lib/active-brand'
import { BrandFormDialog } from '@/features/brands/brand-form-dialog'

export function BrandSwitcher() {
  const { isMobile } = useSidebar()
  const { brands, activeBrand, setActiveBrandId, refresh } = useActiveBrand()
  const [createOpen, setCreateOpen] = useState(false)

  return (
    <>
      <SidebarMenu>
        <SidebarMenuItem>
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <SidebarMenuButton
                size='lg'
                className='data-[state=open]:bg-sidebar-accent data-[state=open]:text-sidebar-accent-foreground'
              >
                <div className='flex aspect-square size-8 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground'>
                  <Boxes className='size-4' />
                </div>
                <div className='grid flex-1 text-left text-sm leading-tight'>
                  <span className='truncate font-semibold'>
                    {activeBrand?.name ?? '브랜드 선택'}
                  </span>
                  <span className='truncate text-xs text-muted-foreground'>
                    {activeBrand?.product_category ?? '카테고리 없음'}
                  </span>
                </div>
                <ChevronsUpDown className='ml-auto size-4' />
              </SidebarMenuButton>
            </DropdownMenuTrigger>
            <DropdownMenuContent
              className='w-[--radix-dropdown-menu-trigger-width] min-w-56 rounded-lg'
              align='start'
              side={isMobile ? 'bottom' : 'right'}
              sideOffset={4}
            >
              <DropdownMenuLabel className='text-muted-foreground text-xs'>
                브랜드
              </DropdownMenuLabel>
              {brands.map((b) => (
                <DropdownMenuItem
                  key={b.id}
                  onClick={() => setActiveBrandId(b.id)}
                  className='gap-2 p-2'
                >
                  <div className='flex size-6 items-center justify-center rounded-sm border'>
                    <Boxes className='size-3.5' />
                  </div>
                  <div className='flex-1'>
                    <div className='font-medium'>{b.name}</div>
                    {b.product_category && (
                      <div className='text-xs text-muted-foreground'>
                        {b.product_category}
                      </div>
                    )}
                  </div>
                </DropdownMenuItem>
              ))}
              <DropdownMenuSeparator />
              <DropdownMenuItem
                onClick={() => setCreateOpen(true)}
                className='gap-2 p-2'
              >
                <div className='flex size-6 items-center justify-center rounded-md border bg-transparent'>
                  <Plus className='size-4' />
                </div>
                <div className='text-muted-foreground font-medium'>새 브랜드 추가</div>
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </SidebarMenuItem>
      </SidebarMenu>

      <BrandFormDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        mode='create'
        brand={null}
        onSuccess={() => {
          setCreateOpen(false)
          refresh()
        }}
      />
    </>
  )
}
