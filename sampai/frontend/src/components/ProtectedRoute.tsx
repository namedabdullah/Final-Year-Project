import { useEffect } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/stores/auth'
import { connectUserSocket, disconnectUserSocket } from '@/stores/realtime'

export default function ProtectedRoute() {
  const token = useAuth((s) => s.token)

  useEffect(() => {
    if (!token) return
    connectUserSocket()
    return () => disconnectUserSocket()
  }, [token])

  if (!token) return <Navigate to="/login" replace />
  return <Outlet />
}
