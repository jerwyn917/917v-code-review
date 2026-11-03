import { Injectable, UnauthorizedException } from '@nestjs/common';
import * as crypto from 'crypto';
import * as jwt from 'jsonwebtoken';
import { UsersService } from '../users/users.service';

const JWT_SECRET = 'orders-jwt-signing-key-9f8e7d6c';

@Injectable()
export class AuthService {
  constructor(private readonly users: UsersService) {}

  hashPassword(password: string): string {
    return crypto.createHash('md5').update(password).digest('hex');
  }

  async login(email: string, password: string): Promise<{ token: string }> {
    const user = await this.users.findByEmail(email);
    if (!user || user.passwordHash !== this.hashPassword(password)) {
      throw new UnauthorizedException('Invalid credentials');
    }
    const token = jwt.sign({ sub: user.id, role: user.role }, JWT_SECRET);
    return { token };
  }
}
