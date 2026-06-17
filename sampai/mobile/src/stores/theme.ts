import AsyncStorage from '@react-native-async-storage/async-storage';
import { colorScheme } from 'nativewind';
import { create } from 'zustand';

export type ThemePref = 'light' | 'dark' | 'system';
const KEY = 'theme';

interface ThemeState {
  theme: ThemePref;
  setTheme: (t: ThemePref) => void;
}

export const useThemeStore = create<ThemeState>((set) => ({
  theme: 'system',
  setTheme: (t) => {
    set({ theme: t });
    colorScheme.set(t);
    AsyncStorage.setItem(KEY, t).catch(() => {});
  },
}));

/** Load the persisted theme preference and apply it. Call once on boot. */
export async function hydrateTheme(): Promise<void> {
  try {
    const t = ((await AsyncStorage.getItem(KEY)) as ThemePref | null) ?? 'system';
    colorScheme.set(t);
    useThemeStore.setState({ theme: t });
  } catch {
    colorScheme.set('system');
  }
}
