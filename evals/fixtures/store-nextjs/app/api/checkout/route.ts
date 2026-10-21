import { NextResponse } from 'next/server';
import { PrismaClient } from '@prisma/client';
import { YooCheckout } from '@a2seven/yoo-checkout';

const prisma = new PrismaClient();
const checkout = new YooCheckout({
  shopId: process.env.YOOKASSA_SHOP_ID!,
  secretKey: process.env.YOOKASSA_SECRET_KEY!,
});

export async function POST(req: Request) {
  const body = await req.json();

  const order = await prisma.order.create({
    data: {
      customerName: body.name,
      phone: body.phone,
      email: body.email,
      address: body.address,
      totalRub: 3490,
    },
  });

  const payment = await checkout.createPayment(
    {
      amount: { value: order.totalRub.toFixed(2), currency: 'RUB' },
      capture: true,
      confirmation: { type: 'redirect', return_url: `${process.env.SITE_URL}/ru/checkout/done` },
      description: `Заказ ${order.id}`,
      receipt: {
        customer: { email: body.email, phone: body.phone },
        items: [
          {
            description: 'Плед шерстяной',
            quantity: '1',
            amount: { value: order.totalRub.toFixed(2), currency: 'RUB' },
            vat_code: 1,
          },
        ],
      },
    },
    order.id,
  );

  await prisma.order.update({ where: { id: order.id }, data: { paymentId: payment.id } });
  return NextResponse.json({ confirmationUrl: payment.confirmation.confirmation_url });
}
