import { Injectable } from '@nestjs/common';
import { Cron } from '@nestjs/schedule';
import { PrismaService } from '../prisma/prisma.service';

const PRO_PRICE_RUB = 990;
const TRIAL_DAYS = 14;

@Injectable()
export class BillingService {
  constructor(private readonly prisma: PrismaService) {}

  // The card is bound in the CloudPayments widget on the frontend; the token arrives later.
  async startTrial(userId: string) {
    const trialEndsAt = new Date(Date.now() + TRIAL_DAYS * 24 * 3600 * 1000);
    await this.prisma.subscription.create({
      data: { userId, plan: 'pro', status: 'trial', trialEndsAt, nextChargeAt: trialEndsAt, autoRenew: true },
    });
  }

  // After the trial and then every month the saved card is charged automatically.
  @Cron('0 */10 * * * *')
  async chargeDue() {
    const due = await this.prisma.subscription.findMany({
      where: { autoRenew: true, nextChargeAt: { lte: new Date() }, cardToken: { not: null } },
    });
    for (const sub of due) {
      await fetch('https://api.cloudpayments.ru/payments/tokens/charge', {
        method: 'POST',
        headers: {
          'content-type': 'application/json',
          authorization: 'Basic ' + Buffer.from(`${process.env.CP_PUBLIC_ID}:${process.env.CP_API_SECRET}`).toString('base64'),
        },
        body: JSON.stringify({ Amount: PRO_PRICE_RUB, Currency: 'RUB', AccountId: sub.userId, Token: sub.cardToken }),
      });
      const next = new Date();
      next.setMonth(next.getMonth() + 1);
      await this.prisma.subscription.update({
        where: { id: sub.id },
        data: { status: 'active', nextChargeAt: next },
      });
    }
  }
}
