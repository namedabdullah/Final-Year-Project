import { ActivityIndicator, Pressable, Text } from 'react-native';

import { cn } from '@/lib/utils';

type Variant = 'default' | 'secondary' | 'destructive' | 'outline';

const container: Record<Variant, string> = {
  default: 'bg-primary',
  secondary: 'bg-secondary',
  destructive: 'bg-destructive',
  outline: 'border border-border bg-transparent',
};
const labelClass: Record<Variant, string> = {
  default: 'text-primary-foreground',
  secondary: 'text-secondary-foreground',
  destructive: 'text-destructive-foreground',
  outline: 'text-foreground',
};
const spinnerColor: Record<Variant, string> = {
  default: '#f9fcff',
  secondary: '#19232a',
  destructive: '#f9fcff',
  outline: '#19232a',
};

export function Button({
  label,
  onPress,
  variant = 'default',
  loading = false,
  disabled = false,
  className,
}: {
  label: string;
  onPress?: () => void;
  variant?: Variant;
  loading?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const off = disabled || loading;
  return (
    <Pressable
      onPress={onPress}
      disabled={off}
      className={cn(
        'flex-row items-center justify-center rounded-lg px-4 py-3',
        container[variant],
        off && 'opacity-50',
        className,
      )}
    >
      {loading ? <ActivityIndicator color={spinnerColor[variant]} style={{ marginRight: 8 }} /> : null}
      <Text className={cn('text-base font-semibold', labelClass[variant])}>{label}</Text>
    </Pressable>
  );
}
