import { ContentSection } from '../components/content-section'
import { NotificationsForm } from './notifications-form'

export function SettingsNotifications() {
  return (
    <ContentSection
      title='알림'
      desc='Telegram·이메일 알림 채널과 빈도를 설정합니다.'
    >
      <NotificationsForm />
    </ContentSection>
  )
}
