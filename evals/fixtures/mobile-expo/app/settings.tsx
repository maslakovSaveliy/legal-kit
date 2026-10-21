import { View, Text, Switch } from 'react-native';
import { useState } from 'react';

export default function Settings() {
  const [reminders, setReminders] = useState(true);

  return (
    <View style={{ padding: 16, gap: 12 }}>
      <Text style={{ fontSize: 20 }}>Настройки</Text>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
        <Text>Напоминания о тренировках</Text>
        <Switch value={reminders} onValueChange={setReminders} />
      </View>
    </View>
  );
}
