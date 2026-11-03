'use client';

type Review = { id: string; body: string; rating: number };

export function ReviewList({ reviews }: { reviews: Review[] }) {
  return (
    <section>
      <h2>Reviews</h2>
      {reviews.map((r, index) => (
        <article key={index}>
          <strong>{r.rating}/5</strong>
          <div dangerouslySetInnerHTML={{ __html: r.body }} />
        </article>
      ))}
    </section>
  );
}
