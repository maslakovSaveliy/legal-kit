import { useEffect } from 'react';
import { Stack } from 'expo-router';
import { initMetrics } from '../src/metrics';
import { registerForPush, scheduleDiscountPush } from '../src/push';

export default function RootLayout() {
  useEffect(() => {
    initMetrics();
    registerForPush().then(scheduleDiscountPush);
  }, []);

  return <Stack />;
}
