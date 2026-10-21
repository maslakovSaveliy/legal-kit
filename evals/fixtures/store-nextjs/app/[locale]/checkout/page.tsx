import { useTranslations } from 'next-intl';
import CheckoutForm from '@/components/CheckoutForm';

export default function CheckoutPage() {
  const t = useTranslations('checkout');
  return (
    <main>
      <h1>{t('title')}</h1>
      <CheckoutForm />
    </main>
  );
}
