import { View, Text } from 'react-native';
import { Link } from 'expo-router';
import { Button } from '../components/ui/Button';
import { buyPremium } from '../src/iap';

export default function Home() {
  return (
    <View style={{ padding: 16, gap: 12 }}>
      <Text style={{ fontSize: 24 }}>Бегом</Text>
      <Text>Трекер пробежек. Premium: планы тренировок и статистика, 299 ₽ в месяц.</Text>
      <Button title="Оформить Premium" onPress={buyPremium} />
      <Link href="/signup">Создать аккаунт</Link>
      <Link href="/settings">Настройки</Link>
    </View>
  );
}
