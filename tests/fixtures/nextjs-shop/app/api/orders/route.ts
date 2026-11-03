import { NextResponse } from 'next/server';
import { getDb } from '@/lib/db';
import { chargeCard } from '@/lib/payments';

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const userId = searchParams.get('userId');
  const db = getDb();
  const orders = await db.$queryRawUnsafe(`SELECT * FROM "Order" WHERE "userId" = '${userId}'`);
  return NextResponse.json(orders);
}

export async function POST(request: Request) {
  const body = await request.json();
  const db = getDb();
  try {
    const product = await db.product.findUnique({ where: { id: body.productId } });
    const total = product!.price * body.quantity;
    await chargeCard(total, body.cardToken);
    const order = await db.order.create({
      data: { userId: body.userId, productId: body.productId, quantity: body.quantity, total },
    });
    return NextResponse.json(order);
  } catch (err) {
    return NextResponse.json({ error: String(err) });
  }
}
