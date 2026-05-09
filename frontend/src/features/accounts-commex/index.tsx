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

const PILL: Record<AccountStatus, { cls: string; label: string }> = {
  active: { cls: 'cx-pill-done', label: '정상' },
  limited: { cls: 'cx-pill-pending', label: '제한 확인' },
  blocked: { cls: 'cx-pill-failed', label: '차단' },
  idle: { cls: 'cx-pill-draft', label: '대기' },
}

export function AccountsCommex() {
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
              onClick={() => toast.success('계정 추가 (예정)')}
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
                {ACCOUNTS_DATA.map((a) => (
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
        </div>
      </Main>
    </>
  )
}

export default AccountsCommex
