'use server';

import { getDb } from '@/lib/db';

export async function deleteProduct(id: string) {
  const db = getDb();
  await db.product.delete({ where: { id } });
}

export async function addReview(productId: string, userId: string, body: string, rating: number) {
  const db = getDb();
  await db.review.create({ data: { productId, userId, body, rating } });
}
