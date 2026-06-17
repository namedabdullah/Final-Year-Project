import { create } from 'zustand';

import { authApi } from '@/api/sampai';
import { hydrateToken, setToken } from '@/lib/token';
import type { User } from '@/lib/types';

// Ported from sampai/frontend/src/stores/auth.ts.
// Web kept token+user in localStorage (sync). RN keeps the token in SecureStore
// (via the token cache) and re-validates the user through /auth/me on boot.
interface AuthState {
  user: User | null;
  /** True once boot hydration + validation has finished. */
  isReady: boolean;
  setAuth: (token: string, user: User) => Promise<void>;
  logout: () => Promise<void>;
  bootstrap: () => Promise<void>;
}

export const useAuth = create<AuthState>((set) => ({
  user: null,
  isReady: false,
  setAuth: async (token, user) => {
    await setToken(token);
    set({ user });
  },
  logout: async () => {
    await setToken(null);
    set({ user: null });
  },
  bootstrap: async () => {
    try {
      const token = await hydrateToken();
      if (!token) {
        set({ user: null, isReady: true });
        return;
      }
      const user = await authApi.me();
      set({ user, isReady: true });
    } catch {
      // invalid/expired token — clear and continue unauthenticated
      await setToken(null);
      set({ user: null, isReady: true });
    }
  },
}));
