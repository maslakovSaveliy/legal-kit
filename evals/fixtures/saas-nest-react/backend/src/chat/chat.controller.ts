import { Body, Controller, Post } from '@nestjs/common';
import { IsString, MaxLength } from 'class-validator';
import { ChatService } from './chat.service';

class AskDto {
  @IsString() @MaxLength(4000) text: string;
}

@Controller('chat')
export class ChatController {
  constructor(private readonly chat: ChatService) {}

  @Post()
  ask(@Body() dto: AskDto) {
    // The user id comes from the auth guard in the real product; fixed here to keep the fixture small.
    return this.chat.ask('current-user', dto.text);
  }
}
