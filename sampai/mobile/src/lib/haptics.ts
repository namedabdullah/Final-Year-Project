import * as Haptics from 'expo-haptics';

export const tapLight = () => {
  Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light).catch(() => {});
};

export const tapSuccess = () => {
  Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success).catch(() => {});
};
