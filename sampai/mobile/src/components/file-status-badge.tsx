import { Text } from 'react-native';

// Class strings are written as literals so NativeWind's content scanner sees them.
const MAP: Record<string, { label: string; cls: string }> = {
  pending: { label: 'Queued', cls: 'text-muted-foreground' },
  processing: { label: 'Processing…', cls: 'text-chart-2' },
  naive_ready: { label: 'Chat ready', cls: 'text-chart-2' },
  completed: { label: 'Ready', cls: 'text-chart-4' },
  failed: { label: 'Failed', cls: 'text-destructive' },
};

export function FileStatusBadge({ status }: { status: string }) {
  const s = MAP[status] ?? { label: status, cls: 'text-muted-foreground' };
  return <Text className={`text-xs font-medium ${s.cls}`}>{s.label}</Text>;
}
