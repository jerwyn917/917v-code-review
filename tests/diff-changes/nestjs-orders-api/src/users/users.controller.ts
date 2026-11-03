import { Controller, Delete, Get, Param, Query, Res } from '@nestjs/common';
import { UsersService } from './users.service';
import { exportUserCsv } from './export.util';

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

  @Get(':id/export')
  async export(@Param('id') id: string, @Query('file') file: string, @Res() res: any) {
    const path = await exportUserCsv(Number(id), file);
    res.download(path);
  }

  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.users.remove(Number(id));
  }
}
