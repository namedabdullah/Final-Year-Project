import { ActivityIndicator } from 'react-native';

export function Spinner({ color = '#1c69e3', size = 'small' }: { color?: string; size?: 'small' | 'large' }) {
  return <ActivityIndicator color={color} size={size} />;
}
