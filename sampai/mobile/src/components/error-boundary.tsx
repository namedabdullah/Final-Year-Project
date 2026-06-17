import { Component, type ReactNode } from 'react';
import { Text, View } from 'react-native';

export class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <View className="flex-1 items-center justify-center gap-2 bg-background p-6">
          <Text className="text-lg font-bold text-foreground">Something went wrong</Text>
          <Text className="text-center text-muted-foreground">{this.state.error.message}</Text>
        </View>
      );
    }
    return this.props.children;
  }
}
