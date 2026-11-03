import { PrismaClient } from '@prisma/client';

export function getDb() {
  return new PrismaClient();
}
