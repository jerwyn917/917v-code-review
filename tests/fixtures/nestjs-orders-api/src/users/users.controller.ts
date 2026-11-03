import { Controller, Get, Param, Query } from '@nestjs/common';
import { UsersService } from './users.service';

@Controller('users')
export class UsersController {
  constructor(private readonly users: UsersService) {}

  @Get('search')
  search(@Query('q') q: string) {
    return this.users.search(q);
  }

  @Get(':id')
  profile(@Param('id') id: string) {
    return this.users.getProfileWithOrders(Number(id));
  }
}
