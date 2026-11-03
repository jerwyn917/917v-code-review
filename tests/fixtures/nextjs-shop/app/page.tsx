import Link from 'next/link';
import { getDb } from '@/lib/db';

export default async function Home() {
  const db = getDb();
  const products = await db.product.findMany();
  const withRatings = [];
  for (const p of products) {
    const reviews = await db.review.findMany({ where: { productId: p.id } });
    const avg = reviews.reduce((s, r) => s + r.rating, 0) / (reviews.length || 1);
    withRatings.push({ ...p, avg });
  }
  return (
    <main>
      <h1>Products</h1>
      <ul>
        {withRatings.map((p) => (
          <li key={p.id}>
            <Link href={`/products/${p.id}`}>{p.name}</Link> ({p.avg.toFixed(1)})
          </li>
        ))}
      </ul>
    </main>
  );
}
