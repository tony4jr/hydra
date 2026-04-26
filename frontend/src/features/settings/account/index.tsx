import { ContentSection } from '../components/content-section'
import { AccountForm } from './account-form'

export function SettingsAccount() {
  return (
    <ContentSection
      title='계정'
      desc='언어와 시간대 등 운영자 계정 정보를 관리합니다.'
    >
      <AccountForm />
    </ContentSection>
  )
}
