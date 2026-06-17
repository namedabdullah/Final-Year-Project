import axios from 'axios';

import { Config } from '@/config';
import { authEvents } from '@/lib/auth-events';
import { getToken, setToken } from '@/lib/token';

// Ported from sampai/frontend/src/api/client.ts.
// Web differences: baseURL from Config (not import.meta.env); token from the
// in-memory cache (not localStorage); 401 fires a logout event (not window.location).
const api = axios.create({ baseURL: Config.API_BASE });

api.interceptors.request.use((config) => {
  const token = getToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    if (error?.response?.status === 401) {
      void setToken(null);
      authEvents.emitLogout();
    }
    return Promise.reject(error);
  },
);

export default api;
