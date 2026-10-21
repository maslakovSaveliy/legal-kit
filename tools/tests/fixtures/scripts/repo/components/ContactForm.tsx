import { Checkbox } from '@/components/ui/checkbox';

export default function ContactForm() {
  return (
    <form onSubmit={() => {}}>
      <input name="name" type="text" />
      <input name="phone" type="tel" />
      <textarea name="comment" />
      <label>
        <Checkbox id="consent-pd" defaultChecked />
        Я согласен на обработку персональных данных
      </label>
      <label>
        <Checkbox id="newsletter" checked={subscribed} onCheckedChange={setSubscribed} />
        Подписаться на рассылку
      </label>
      <button type="submit">Отправить</button>
    </form>
  );
}
