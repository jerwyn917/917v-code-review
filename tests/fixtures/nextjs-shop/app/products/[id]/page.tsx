import { getDb } from '@/lib/db';
import { ReviewList } from '@/components/ReviewList';
import { Cart } from '@/components/Cart';

export default async function ProductPage({ params }: { params: { id: string } }) {
  const db = getDb();
  const product = await db.product.findUnique({ where: { id: params.id } });
  const reviews = await db.review.findMany({ where: { productId: params.id } });
  if (!product) return <p>Not found</p>;
  return (
    <main>
      <h1>{product.name}</h1>
      <p>{product.description}</p>
      <Cart productId={product.id} price={product.price} />
      <ReviewList reviews={reviews} />
    </main>
  );
}
