import * as Notifications from 'expo-notifications';

// Asks for the OS permission on the first launch and returns the Expo push token.
export async function registerForPush() {
  const { status } = await Notifications.requestPermissionsAsync();
  if (status !== 'granted') return null;
  const token = await Notifications.getExpoPushTokenAsync();
  return token.data;
}

// Promotional reminder sent to everybody who has a token.
export async function scheduleDiscountPush() {
  await Notifications.scheduleNotificationAsync({
    content: { title: 'Скидка 30% на Premium', body: 'Только до воскресенья. Пробежки без ограничений.' },
    trigger: { seconds: 60 * 60 * 24 * 3 },
  });
}
