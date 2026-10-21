import { Body, Controller, Post } from '@nestjs/common';
import { createHash } from 'crypto';
import { PrismaService } from '../prisma/prisma.service';
import { BillingService } from '../billing/billing.service';
import { RegisterDto } from './register.dto';

@Controller('auth')
export class AuthController {
  constructor(
    private readonly prisma: PrismaService,
    private readonly billing: BillingService,
  ) {}

  @Post('register')
  async register(@Body() dto: RegisterDto) {
    const user = await this.prisma.user.create({
      data: {
        email: dto.email,
        name: dto.name,
        passwordHash: createHash('sha256').update(dto.password).digest('hex'),
      },
    });
    await this.billing.startTrial(user.id);
    return { id: user.id };
  }
}
