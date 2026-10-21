import { Injectable } from '@nestjs/common';
import { PrismaService } from '../prisma/prisma.service';

@Injectable()
export class ChatService {
  constructor(private readonly prisma: PrismaService) {}

  // Answers come from a hosted foundation model (YandexGPT); the dialogue is stored per user.
  async ask(userId: string, text: string) {
    await this.prisma.chatMessage.create({ data: { userId, role: 'user', text } });

    const res = await fetch('https://llm.api.cloud.yandex.net/foundationModels/v1/completion', {
      method: 'POST',
      headers: { authorization: `Api-Key ${process.env.YC_API_KEY}`, 'content-type': 'application/json' },
      body: JSON.stringify({
        modelUri: `gpt://${process.env.YC_FOLDER_ID}/yandexgpt/latest`,
        messages: [{ role: 'user', text }],
      }),
    });
    const data = await res.json();
    const answer: string = data.result.alternatives[0].message.text;

    await this.prisma.chatMessage.create({ data: { userId, role: 'assistant', text: answer } });
    return { answer };
  }
}
