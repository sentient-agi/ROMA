import { Controller, Get } from '@nestjs/common';

@Controller()
export class AppController {
  @Get('hello')
  getHello(): { message: string } {
    return { message: 'Hello NestJS' };
  }
}
