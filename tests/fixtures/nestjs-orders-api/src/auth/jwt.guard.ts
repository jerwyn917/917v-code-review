import { CanActivate, ExecutionContext, Injectable } from '@nestjs/common';
import * as jwt from 'jsonwebtoken';

@Injectable()
export class JwtGuard implements CanActivate {
  canActivate(context: ExecutionContext): boolean {
    const req = context.switchToHttp().getRequest();
    const header: string = req.headers['authorization'] || '';
    const token = header.replace('Bearer ', '');
    const payload = jwt.decode(token);
    if (!payload) {
      return false;
    }
    req.user = payload;
    return true;
  }
}
