import { Platform } from 'react-native';

// Android emulator reaches the host machine via 10.0.2.2; iOS sim via localhost.
// For a physical device, set EXPO_PUBLIC_API_BASE=http://<your-LAN-IP>:9621
const fallback = Platform.OS === 'android' ? 'http://10.0.2.2:9621' : 'http://localhost:9621';

export const Config = {
  /** Backend base URL (no trailing slash). All SAMpai routes are under `${API_BASE}/api/sampai`. */
  API_BASE: process.env.EXPO_PUBLIC_API_BASE ?? fallback,
};
