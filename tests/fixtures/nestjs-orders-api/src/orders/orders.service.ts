import { Inject, Injectable, forwardRef } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Order, OrderItem } from './order.entity';
import { UsersService } from '../users/users.service';

@Injectable()
export class OrdersService {
  constructor(
    @InjectRepository(Order) private readonly orders: Repository<Order>,
    @InjectRepository(OrderItem) private readonly items: Repository<OrderItem>,
    @Inject(forwardRef(() => UsersService)) private readonly users: UsersService,
  ) {}

  async listForUser(userId: number) {
    const orders = await this.orders.find({ where: { userId } });
    for (const order of orders) {
      (order as any).items = await this.items.find({ where: { orderId: order.id } });
    }
    return orders;
  }

  async listAll() {
    return this.orders.find();
  }

  async placeOrder(userId: number, items: { sku: string; quantity: number; price: number }[]) {
    const user = await this.users.findById(userId);
    const total = items.reduce((sum, i) => sum + i.price * i.quantity, 0);
    user.balance = user.balance - total;
    await this.users.save(user);
    const order = await this.orders.save({ userId, total, status: 'paid' });
    for (const item of items) {
      await this.items.save({ orderId: order.id, ...item });
    }
    return order;
  }
}
