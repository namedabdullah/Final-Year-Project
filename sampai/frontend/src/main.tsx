import React from 'react'
import ReactDOM from 'react-dom/client'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { RouterProvider, createBrowserRouter, Navigate } from 'react-router-dom'
import { Toaster } from '@/components/ui/sonner'
import './index.css'
import ProtectedRoute from '@/components/ProtectedRoute'
import LandingPage from '@/pages/LandingPage'
import LoginPage from '@/pages/LoginPage'
import SignupPage from '@/pages/SignupPage'
import DashboardPage from '@/pages/DashboardPage'
import ClassroomPage from '@/pages/ClassroomPage'
import FolderPage from '@/pages/FolderPage'
import FilePage from '@/pages/FilePage'
import GroupChatThreadPage from '@/pages/GroupChatThreadPage'
import CreatedPage from '@/pages/CreatedPage'
import JoinedPage from '@/pages/JoinedPage'
import CrossFileQuizPage from '@/pages/CrossFileQuizPage'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } },
})

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  { path: '/signup', element: <SignupPage /> },
  {
    element: <ProtectedRoute />,
    children: [
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/created', element: <CreatedPage /> },
      { path: '/joined', element: <JoinedPage /> },
      { path: '/classroom/:id', element: <ClassroomPage /> },
      { path: '/classroom/:id/folder/:folderId', element: <FolderPage /> },
      { path: '/classroom/:id/folder/:folderId/file/:fileId', element: <FilePage /> },
      { path: '/classroom/:id/folder/:folderId/cross-quiz', element: <CrossFileQuizPage /> },
      { path: '/thread/:threadId', element: <GroupChatThreadPage /> },
    ],
  },
  { path: '/', element: <LandingPage /> },
  { path: '*', element: <Navigate to="/dashboard" replace /> },
])

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
      <Toaster richColors position="top-right" />
    </QueryClientProvider>
  </React.StrictMode>,
)
