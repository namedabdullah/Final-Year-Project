import { LinearGradient } from 'expo-linear-gradient';

// Subtle brand-tinted band behind a screen's content (decorative, non-interactive).
export function ScreenGradient() {
  return (
    <LinearGradient
      colors={['rgba(28,105,227,0.18)', 'rgba(28,105,227,0)']}
      style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 320 }}
      pointerEvents="none"
    />
  );
}
