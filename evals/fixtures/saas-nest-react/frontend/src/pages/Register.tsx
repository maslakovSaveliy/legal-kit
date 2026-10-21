import { useForm } from 'react-hook-form';

type Values = { name: string; email: string; password: string };

export default function Register() {
  const { register, handleSubmit } = useForm<Values>();

  async function onSubmit(values: Values) {
    await fetch(`${import.meta.env.VITE_API_URL}/auth/register`, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(values),
    });
  }

  return (
    <main>
      <h1>Регистрация</h1>
      <form onSubmit={handleSubmit(onSubmit)}>
        <input {...register('name')} placeholder="Имя" />
        <input {...register('email')} type="email" placeholder="E-mail" />
        <input {...register('password')} type="password" placeholder="Пароль" />
        <button type="submit">Создать аккаунт</button>
      </form>
    </main>
  );
}
