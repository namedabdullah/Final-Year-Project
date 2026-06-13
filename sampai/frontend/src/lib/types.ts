export interface User {
  id: number
  username: string
  email: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
  user: User
}

export interface FileItem {
  id: number
  filename: string
  file_url: string
  file_type: string | null
  file_size: number | null
  processing_status: 'pending' | 'processing' | 'naive_ready' | 'completed' | 'failed'
  description: string | null
  folder_id: number
  uploaded_at: string
  processed_at: string | null
}

export interface Folder {
  id: number
  name: string
  classroom_id: number
  files: FileItem[]
}

export interface Classroom {
  id: number
  name: string
  description: string | null
  code: string
  owner_id: number
  members: User[]
}
