import { Link } from 'expo-router';
import { useState } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, Text, View } from 'react-native';
import { toast } from 'sonner-native';

import { apiErrorDetail, authApi } from '@/api/sampai';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Screen } from '@/components/ui/screen';
import { ScreenGradient } from '@/components/ui/screen-gradient';
import { emailValid, passwordChecks, usernameValid } from '@/features/auth/validation';
import { useAuth } from '@/stores/auth';

function Rule({ ok, text }: { ok: boolean; text: string }) {
  return (
    <Text className={ok ? 'text-xs text-foreground' : 'text-xs text-muted-foreground'}>
      {ok ? '✓' : '○'} {text}
    </Text>
  );
}

export default function Signup() {
  const setAuth = useAuth((s) => s.setAuth);
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);

  const pc = passwordChecks(password);
  const match = password.length > 0 && password === confirm;
  const canSubmit =
    usernameValid(username) && emailValid(email) && pc.length && pc.letter && pc.number && match && !busy;

  const submit = async () => {
    setBusy(true);
    try {
      await authApi.signup({ username: username.trim(), email: email.trim(), password });
      // Auto-login for a smoother mobile flow (backend signup returns the user, not a token).
      const res = await authApi.login({ email: email.trim(), password });
      await setAuth(res.access_token, res.user);
    } catch (e) {
      toast.error(apiErrorDetail(e, 'Sign up failed'));
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
        <ScrollView
          contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', gap: 12, padding: 24 }}
          keyboardShouldPersistTaps="handled"
        >
          <View className="mb-2 gap-1">
            <Text className="text-3xl font-bold text-foreground">Create account</Text>
            <Text className="text-muted-foreground">Join SAMpai</Text>
          </View>
          <Input placeholder="Username" autoCapitalize="none" value={username} onChangeText={setUsername} />
          <Input
            placeholder="Email"
            autoCapitalize="none"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
          />
          <Input placeholder="Password" secureTextEntry value={password} onChangeText={setPassword} />
          <Input
            placeholder="Confirm password"
            secureTextEntry
            value={confirm}
            onChangeText={setConfirm}
          />
          <View className="gap-1">
            <Rule ok={usernameValid(username)} text="Username 3–50 chars (letters, numbers, _ -)" />
            <Rule ok={pc.length} text="At least 8 characters" />
            <Rule ok={pc.letter && pc.number} text="Contains a letter and a number" />
            <Rule ok={match} text="Passwords match" />
          </View>
          <Button
            label="Create account"
            onPress={submit}
            loading={busy}
            disabled={!canSubmit}
            className="mt-2"
          />
          <View className="mt-4 flex-row justify-center gap-1">
            <Text className="text-muted-foreground">Have an account?</Text>
            <Link href="/login">
              <Text className="font-semibold text-foreground">Sign in</Text>
            </Link>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </Screen>
  );
}
