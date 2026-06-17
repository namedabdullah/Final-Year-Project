import { Text } from 'react-native';

import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { Screen } from '@/components/ui/screen';
import { Segmented } from '@/components/ui/segmented';
import { useAuth } from '@/stores/auth';
import { type ThemePref, useThemeStore } from '@/stores/theme';

export default function Profile() {
  const user = useAuth((s) => s.user);
  const logout = useAuth((s) => s.logout);
  const theme = useThemeStore((s) => s.theme);
  const setTheme = useThemeStore((s) => s.setTheme);

  return (
    <Screen className="gap-4 p-6" edges={['top']}>
      <Text className="text-2xl font-bold text-foreground">Profile</Text>
      <Card className="gap-1">
        <Text className="text-lg font-semibold text-foreground">{user?.username}</Text>
        <Text className="text-muted-foreground">{user?.email}</Text>
      </Card>
      <Card className="gap-2">
        <Text className="text-sm font-semibold text-foreground">Appearance</Text>
        <Segmented<ThemePref>
          value={theme}
          onChange={setTheme}
          options={[
            { key: 'system', label: 'System' },
            { key: 'light', label: 'Light' },
            { key: 'dark', label: 'Dark' },
          ]}
        />
      </Card>
      <Button label="Log out" variant="destructive" onPress={() => void logout()} />
    </Screen>
  );
}
