import { Link } from 'react-router-dom';

export default function Pricing() {
  return (
    <main>
      <h1>Тариф Pro</h1>
      <p>14 дней бесплатно, затем 990 ₽ в месяц. Подписка продлевается автоматически.</p>
      <Link to="/register">Начать бесплатный период</Link>
    </main>
  );
}
