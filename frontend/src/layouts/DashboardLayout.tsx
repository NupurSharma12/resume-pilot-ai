import { Outlet } from 'react-router-dom'
import Sidebar from '../components/Sidebar'
import HelpButton from '../components/HelpButton'

export default function DashboardLayout() {
  return (
    <div className="flex h-screen bg-[#f7f8fa]">
      <Sidebar />
      <main className="flex-1 overflow-y-auto">
        <Outlet />
      </main>
      <HelpButton />
    </div>
  )
}
