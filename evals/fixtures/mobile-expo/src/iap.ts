import { initConnection, requestSubscription } from 'react-native-iap';

const PREMIUM_SKU = 'begom_premium_month';

export async function buyPremium() {
  await initConnection();
  // Auto-renewing subscription, 299 RUB per month.
  await requestSubscription({ sku: PREMIUM_SKU });
}
