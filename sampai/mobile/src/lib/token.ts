import * as SecureStore from 'expo-secure-store';

const KEY = 'token';

// In-memory cache so the axios interceptor, SSE (`expo/fetch`) and `wsUrl`
// can read the token synchronously, while SecureStore persistence is async.
let _token: string | null = null;

export const getToken = (): string | null => _token;

export async function setToken(token: string | null): Promise<void> {
  _token = token;
  if (token) await SecureStore.setItemAsync(KEY, token);
  else await SecureStore.deleteItemAsync(KEY);
}

/** Load the persisted token into the in-memory cache. Call once on app boot. */
export async function hydrateToken(): Promise<string | null> {
  _token = await SecureStore.getItemAsync(KEY);
  return _token;
}
