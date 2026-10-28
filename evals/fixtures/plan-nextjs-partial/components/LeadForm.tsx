"use client";

export function LeadForm() {
  return (
    <form action="/api/lead" method="post">
      <input name="name" placeholder="Имя" />
      <input name="phone" type="tel" placeholder="Телефон" />
      <button type="submit">Оставить заявку</button>
    </form>
  );
}
