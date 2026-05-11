import { createFileRoute, Outlet } from '@tanstack/react-router'

export const Route = createFileRoute('/_authenticated/brands/$brandId/niches/$nicheId')({
  // 자식 라우트(preset-edit 등)로 위임. legacy 자식(index/analytics/campaigns/collection/messaging) 은
  // 각자 redirect 처리되어 있음.
  component: () => <Outlet />,
})
