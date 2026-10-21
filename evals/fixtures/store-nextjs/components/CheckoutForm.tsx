'use client';

import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useTranslations } from 'next-intl';
import { Checkbox } from '@/components/ui/checkbox';

const schema = z.object({
  name: z.string().min(2),
  phone: z.string().min(10),
  email: z.string().email(),
  address: z.string().min(5),
  saveAddress: z.boolean().default(false),
});
type Values = z.infer<typeof schema>;

export default function CheckoutForm() {
  const t = useTranslations('checkout');
  const { register, control, handleSubmit } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { saveAddress: false },
  });

  async function onSubmit(values: Values) {
    const res = await fetch('/api/checkout', {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(values),
    });
    const { confirmationUrl } = await res.json();
    window.location.href = confirmationUrl;
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="grid gap-3 max-w-md">
      <input {...register('name')} placeholder={t('name')} />
      <input {...register('phone')} type="tel" placeholder={t('phone')} />
      <input {...register('email')} type="email" placeholder={t('email')} />
      <input {...register('address')} placeholder={t('address')} />

      <label className="flex items-center gap-2">
        <Controller
          name="saveAddress"
          control={control}
          render={({ field }) => (
            <Checkbox id="save-address" checked={field.value} onCheckedChange={field.onChange} />
          )}
        />
        <span>{t('saveAddress')}</span>
      </label>

      <button type="submit">{t('pay')}</button>
    </form>
  );
}
