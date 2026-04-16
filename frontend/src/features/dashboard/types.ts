export interface DashboardStats {
  accounts: Record<string, number>
  today: {
    comments: number
    likes: number
    total_actions: number
  }
  campaigns: {
    active: number
    total: number
  }
  errors: {
    unresolved: number
  }
  workers: {
    online: number
    total: number
  }
  tasks: {
    today_completed: number
    today_failed: number
    pending: number
    running: number
  }
}

export interface WorkerInfo {
  id: number
  name: string
  status: string
  last_heartbeat: string | null
  current_version: string | null
  os_type: string | null
}
