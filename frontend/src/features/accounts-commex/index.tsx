import { useState } from 'react'
import { Plus } from 'lucide-react'
import { toast } from 'sonner'
import { Header } from '@/components/layout/header'
import { Main } from '@/components/layout/main'
import { ProfileDropdown } from '@/components/profile-dropdown'
import { ThemeSwitch } from '@/components/theme-switch'

type AccountStatus = 'active' | 'limited' | 'blocked' | 'idle'
type Account = {
  id: string
  name: string
  brand: string
  status: AccountStatus
  lastUsed: string
  note: string
}

const ACCOUNTS_DATA: Account[] = [
  { id: 'a1', name: 'acc_main_01', brand: '모렉신', status: 'active', lastUsed: '2분 전', note: '공식 운영 계정' },
  { id: 'a2', name: 'acc_main_02', brand: '노마셀', status: 'limited', lastUsed: '15분 전', note: '리뷰 대응 중심' },
  { id: 'a3', name: 'acc_sub_01', brand: '모렉신', status: 'active', lastUsed: '32분 전', note: '답글 전용' },
  { id: 'a4', name: 'acc_sub_02', brand: '픽셀브루', status: 'active', lastUsed: '1시간 전', note: '루틴 컨텐츠 답글' },
  { id: 'a5', name: 'acc_test_01', brand: '루미핏', status: 'idle', lastUsed: '어제', note: '드라이런용' },
  { id: 'a6', name: 'acc_block_01', brand: '모렉신', status: 'blocked', lastUsed: '3일 전', note: '경고 누적 — 휴면 중' },
  { id: 'a7', name: 'acc_helix_01', brand: '헬릭스코어', status: 'active', lastUsed: '8분 전', note: '건기식 정보형' },
  { id: 'a8', name: 'acc_nomacell_03', brand: '노마셀', status: 'active', lastUsed: '20분 전', note: '뷰티 후기' },
]
const STORAGE_KEY = 'commex-accounts-v1'

const PILL: Record<AccountStatus, { cls: string; label: string }> = {
  active: { cls: 'cx-pill-done', label: '정상' },
  limited: { cls: 'cx-pill-pending', label: '제한 확인' },
  blocked: { cls: 'cx-pill-failed', label: '차단' },
  idle: { cls: 'cx-pill-draft', label: '대기' },
}

export function AccountsCommex() {
  const [accounts, setAccounts] = useState<Account[]>(loadAccounts)
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ name: '', brand: '', note: '' })

  const addAccount = () => {
    const name = form.name.trim()
    const brand = form.brand.trim()
    if (!name || !brand) {
      toast.warning('계정명과 브랜드를 입력하세요')
      return
    }
    const next: Account[] = [
      {
        id: `a-${Date.now().toString(36)}`,
        name,
        brand,
        status: 'idle',
        lastUsed: '방금 등록',
        note: form.note.trim() || '신규 등록 계정',
      },
      ...accounts,
    ]
    setAccounts(next)
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setForm({ name: '', brand: '', note: '' })
    setOpen(false)
    toast.success(`${name} 계정을 추가했습니다`)
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
        <div
          className='hydra-page'
          style={{ display: 'flex', flexDirection: 'column', gap: 18 }}
        >
          <div className='flex items-end justify-between flex-wrap gap-3'>
            <div>
              <h1 className='cx-page-h'>계정 · 아바타</h1>
              <p className='cx-page-sub'>
                브랜드 매핑, 상태, 제한 여부를 확인하고 관리합니다.
              </p>
            </div>
            <button
              className='cx-btn-primary'
              onClick={() => setOpen(true)}
            >
              <Plus className='inline h-4 w-4 mr-1' />계정 추가
            </button>
          </div>

          <div className='cx-card' style={{ overflow: 'hidden' }}>
            <table className='cx-table'>
              <thead>
                <tr>
                  <th style={{ paddingLeft: 18 }}>계정</th>
                  <th>브랜드</th>
                  <th>상태</th>
                  <th>최근 사용</th>
                  <th style={{ paddingRight: 18 }}>비고</th>
                </tr>
              </thead>
              <tbody>
                {accounts.map((a) => (
                  <tr key={a.id}>
                    <td style={{ paddingLeft: 18, fontWeight: 700, fontFamily: 'monospace', fontSize: 13 }}>
                      {a.name}
                    </td>
                    <td>{a.brand}</td>
                    <td>
                      <span className={`cx-pill ${PILL[a.status].cls}`}>
                        {PILL[a.status].label}
                      </span>
                    </td>
                    <td style={{ color: 'var(--cx-sub)' }}>{a.lastUsed}</td>
                    <td style={{ paddingRight: 18, color: 'var(--cx-sub)' }}>{a.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {open && (
            <div
              style={{
                position: 'fixed',
                inset: 0,
                zIndex: 60,
                background: 'rgba(15,23,42,0.35)',
                display: 'grid',
                placeItems: 'center',
                padding: 20,
              }}
              onClick={() => setOpen(false)}
            >
              <div
                className='cx-card cx-card-pad'
                style={{ width: 'min(480px, 100%)', display: 'flex', flexDirection: 'column', gap: 14 }}
                onClick={(e) => e.stopPropagation()}
              >
                <div className='cx-section-head'>
                  <div className='cx-section-title'>계정 추가</div>
                  <button className='cx-btn-mini' onClick={() => setOpen(false)}>
                    닫기
                  </button>
                </div>
                <Field label='계정명'>
                  <input
                    className='cx-input'
                    value={form.name}
                    onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
                    autoFocus
                    placeholder='예: acc_main_03'
                  />
                </Field>
                <Field label='브랜드'>
                  <input
                    className='cx-input'
                    value={form.brand}
                    onChange={(e) => setForm((f) => ({ ...f, brand: e.target.value }))}
                    placeholder='예: 모렉신'
                  />
                </Field>
                <Field label='비고'>
                  <input
                    className='cx-input'
                    value={form.note}
                    onChange={(e) => setForm((f) => ({ ...f, note: e.target.value }))}
                    placeholder='운영 용도'
                  />
                </Field>
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: 8 }}>
                  <button className='cx-btn-soft' onClick={() => setOpen(false)}>
                    취소
                  </button>
                  <button className='cx-btn-primary' onClick={addAccount}>
                    추가
                  </button>
                </div>
              </div>
            </div>
          )}
        </div>
      </Main>
    </>
  )
}

function loadAccounts(): Account[] {
  if (typeof window === 'undefined') return ACCOUNTS_DATA
  const raw = window.localStorage.getItem(STORAGE_KEY)
  if (!raw) return ACCOUNTS_DATA
  try {
    return JSON.parse(raw) as Account[]
  } catch {
    return ACCOUNTS_DATA
  }
}

function Field({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      <span style={{ fontSize: 12, color: 'var(--cx-sub)', fontWeight: 800 }}>
        {label}
      </span>
      {children}
    </label>
  )
}

export default AccountsCommex
