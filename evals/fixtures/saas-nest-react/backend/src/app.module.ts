import { Module } from '@nestjs/common';
import { ConfigModule } from '@nestjs/config';
import { ScheduleModule } from '@nestjs/schedule';
import { PrismaService } from './prisma/prisma.service';
import { AuthController } from './auth/auth.controller';
import { BillingService } from './billing/billing.service';
import { ChatController } from './chat/chat.controller';
import { ChatService } from './chat/chat.service';

@Module({
  imports: [ConfigModule.forRoot({ isGlobal: true }), ScheduleModule.forRoot()],
  controllers: [AuthController, ChatController],
  providers: [PrismaService, BillingService, ChatService],
})
export class AppModule {}
