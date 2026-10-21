import { NextIntlClientProvider } from 'next-intl';
import { getMessages, getTranslations } from 'next-intl/server';
import Link from 'next/link';
import Metrika from '@/components/Metrika';

export default async function LocaleLayout({
  children,
  params,
}: {
  children: React.ReactNode;
  params: Promise<{ locale: string }>;
}) {
  const { locale } = await params;
  const messages = await getMessages();
  const t = await getTranslations('footer');

  return (
    <html lang={locale}>
      <body>
        <NextIntlClientProvider messages={messages}>
          <header>
            <Link href={`/${locale}`}>Тёплый дом</Link>
          </header>
          {children}
          <footer className="site-footer">
            <p>{t('copyright')}</p>
            <nav>
              <Link href={`/${locale}/offer`}>{t('offer')}</Link>
            </nav>
          </footer>
        </NextIntlClientProvider>
        <Metrika />
      </body>
    </html>
  );
}
