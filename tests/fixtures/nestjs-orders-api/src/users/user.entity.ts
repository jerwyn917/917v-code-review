import { Column, Entity, OneToMany, PrimaryGeneratedColumn } from 'typeorm';
import { Order } from '../orders/order.entity';

@Entity()
export class User {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  email: string;

  @Column()
  name: string;

  @Column()
  passwordHash: string;

  @Column({ default: 'customer' })
  role: string;

  @Column('float', { default: 0 })
  balance: number;

  @OneToMany(() => Order, (order) => order.user)
  orders: Order[];
}
