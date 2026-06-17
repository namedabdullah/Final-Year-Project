import { Text, View } from 'react-native';

export function EmptyState({ title, subtitle }: { title: string; subtitle?: string }) {
  return (
    <View className="items-center justify-center gap-1 py-12">
      <Text className="text-base font-semibold text-foreground">{title}</Text>
      {subtitle ? <Text className="text-center text-muted-foreground">{subtitle}</Text> : null}
    </View>
  );
}
