import { Body, Controller, Get, Param, Post, Req, UseGuards } from '@nestjs/common';
import { OrdersService } from './orders.service';
import { JwtGuard } from '../auth/jwt.guard';

@Controller('orders')
export class OrdersController {
  constructor(private readonly orders: OrdersService) {}

  @Get()
  all() {
    return this.orders.listAll();
  }

  @Get('user/:userId')
  forUser(@Param('userId') userId: string) {
    return this.orders.listForUser(Number(userId));
  }

  @UseGuards(JwtGuard)
  @Post()
  async create(@Req() req: any, @Body() body: any) {
    try {
      if (!body.items || body.items.length === 0) {
        return { error: 'Order must contain items' };
      }
      const discount = body.items.length > 10 ? 0.1 : 0;
      const items = body.items.map((i: any) => ({ ...i, price: i.price * (1 - discount) }));
      return await this.orders.placeOrder(req.user.sub, items);
    } catch (e) {}
  }
}
