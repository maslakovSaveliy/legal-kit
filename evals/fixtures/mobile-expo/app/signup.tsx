import { useState } from 'react';
import { View, TextInput } from 'react-native';
import { Button } from '../components/ui/Button';
import { track } from '../src/metrics';

export default function Signup() {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');

  async function submit() {
    await fetch('https://api.begom.test/v1/users', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify({ name, email }),
    });
    track('signup', { source: 'app' });
  }

  return (
    <View style={{ padding: 16, gap: 12 }}>
      <TextInput value={name} onChangeText={setName} placeholder="Имя" />
      <TextInput value={email} onChangeText={setEmail} placeholder="E-mail" keyboardType="email-address" />
      <Button title="Создать аккаунт" onPress={submit} />
    </View>
  );
}
