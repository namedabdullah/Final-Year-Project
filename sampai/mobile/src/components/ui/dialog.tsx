import type { ReactNode } from 'react';
import { Modal, Pressable, Text, View } from 'react-native';

export function Dialog({
  visible,
  onClose,
  title,
  children,
}: {
  visible: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
}) {
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose} statusBarTranslucent>
      <Pressable
        onPress={onClose}
        className="flex-1 items-center justify-center bg-black/50 p-6"
      >
        {/* Inner Pressable claims the touch so taps inside the card don't dismiss. */}
        <Pressable onPress={() => {}} className="w-full rounded-xl border border-border bg-card p-5">
          {title ? <Text className="mb-3 text-lg font-bold text-foreground">{title}</Text> : null}
          {children}
        </Pressable>
      </Pressable>
    </Modal>
  );
}
