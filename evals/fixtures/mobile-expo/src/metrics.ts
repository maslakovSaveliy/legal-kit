import AppMetrica from '@appmetrica/react-native-analytics';

// Starts the AppMetrica SDK. Called once from the root layout.
export function initMetrics() {
  AppMetrica.activate({
    apiKey: '00000000-0000-0000-0000-000000000000',
    sessionTimeout: 120,
    firstActivationAsUpdate: false,
  });
}

export function track(event: string, params?: Record<string, string>) {
  AppMetrica.reportEvent(event, params);
}
