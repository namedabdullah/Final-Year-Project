import { Link } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail, authApi } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Screen } from '@/components/ui/screen';
import { ScreenGradient } from '@/components/ui/screen-gradient';
import { emailValid } from '@/features/auth/validation';
import { useAuth } from '@/stores/auth';

export default function Login() {
  const setAuth = useAuth((s) => s.setAuth);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);

  const canSubmit = emailValid(email) && password.length > 0 && !busy;

  const submit = async () => {
    setBusy(true);
    try {
      const res = await authApi.login({ email: email.trim(), password });
      await setAuth(res.access_token, res.user);
      // (public) layout redirects to "/" once `user` is set.
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Login failed'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <ScreenGradient />
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === 'ios' ? 'padding' : undefined}
      >
        <View className="flex-1 justify-center gap-4 p-6">
          <View className="mb-2 gap-1">
            <Text className="text-3xl font-bold text-foreground">Welcome back</Text>
            <Text className="text-muted-foreground">Sign in to your SAMpai account</Text>
          </View>
          <Input
            placeholder="Email"
            autoCapitalize="none"
            keyboardType="email-address"
            autoComplete="email"
            value={email}
            onChangeText={setEmail}
          />
          <Input placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} />
          <Button label="Sign in" onPress={submit} loading={busy} disabled={!canSubmit} className="mt-2" />
          <View className="mt-4 flex-row justify-center gap-1">
            <Text className="text-muted-foreground">No account?</Text>
            <Link href="/signup">
              <Text className="font-semibold text-foreground">Sign up</Text>
            </Link>
          </View>
        </View>
      </KeyboardAvoidingView>
    </Screen>
  );
}
