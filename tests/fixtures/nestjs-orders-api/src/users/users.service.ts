import { Inject, Injectable, forwardRef } from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { DataSource, Repository } from 'typeorm';
import { User } from './user.entity';
import { OrdersService } from '../orders/orders.service';

@Injectable()
export class UsersService {
  constructor(
    @InjectRepository(User) private readonly repo: Repository<User>,
    private readonly dataSource: DataSource,
    @Inject(forwardRef(() => OrdersService)) private readonly orders: OrdersService,
  ) {}

  findById(id: number) {
    return this.repo.findOne({ where: { id } });
  }

  findByEmail(email: string) {
    return this.repo.findOne({ where: { email } });
  }

  search(q: string) {
    return this.dataSource.query(`SELECT * FROM "user" WHERE name ILIKE '%${q}%'`);
  }

  async getProfileWithOrders(id: number) {
    const user = await this.findById(id);
    const orders = await this.orders.listForUser(id);
    return { ...user, orders };
  }

  save(user: User) {
    return this.repo.save(user);
  }
}
