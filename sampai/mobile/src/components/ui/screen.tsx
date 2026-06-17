import type { ReactNode } from 'react';
import { View } from 'react-native';
import { type Edge, SafeAreaView } from 'react-native-safe-area-context';

import { cn } from '@/lib/utils';

// Wraps content with the themed background + safe-area insets. Uses a plain
// style on SafeAreaView (no reliance on NativeWind interop for third-party
// components) and applies Tailwind classes to inner Views.
export function Screen({
  children,
  className,
  edges = ['top', 'bottom'],
}: {
  children: ReactNode;
  className?: string;
  edges?: Edge[];
}) {
  return (
    <View className="flex-1 bg-background">
      <SafeAreaView style={{ flex: 1 }} edges={edges}>
        <View className={cn('flex-1', className)}>{children}</View>
      </SafeAreaView>
    </View>
  );
}
