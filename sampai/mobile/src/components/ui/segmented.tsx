import { Pressable, Text, View } from 'react-native';

import { cn } from '@/lib/utils';

export function Segmented<T extends string>({
  options,
  value,
  onChange,
}: {
  options: { key: T; label: string }[];
  value: T;
  onChange: (key: T) => void;
}) {
  return (
    <View className="flex-row rounded-lg border border-border bg-secondary p-1">
      {options.map((o) => {
        const active = o.key === value;
        return (
          <Pressable
            key={o.key}
            onPress={() => onChange(o.key)}
            className={cn('flex-1 items-center rounded-md py-2', active && 'bg-card')}
          >
            <Text
              className={cn('text-xs font-medium', active ? 'text-foreground' : 'text-muted-foreground')}
            >
              {o.label}
            </Text>
          </Pressable>
        );
      })}
    </View>
  );
}
