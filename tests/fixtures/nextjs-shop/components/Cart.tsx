'use client';

import { useEffect, useState } from 'react';
import _ from 'lodash';

export function Cart({ productId, price }: { productId: string; price: number }) {
  const [quantity, setQuantity] = useState(1);
  const [total, setTotal] = useState(price);
  const [stock, setStock] = useState<number | null>(null);

  useEffect(() => {
    setTotal(quantity * price);
  }, [quantity, price]);

  useEffect(() => {
    fetch(`/api/stock?productId=${productId}`)
      .then((r) => r.json())
      .then((d) => setStock(d.stock));
  });

  function checkout(token: string) {
    localStorage.setItem('authToken', token);
    return fetch('/api/orders', {
      method: 'POST',
      body: JSON.stringify({ productId, quantity, cardToken: token }),
    });
  }

  return (
    <div>
      <img src="/cart.png" />
      <div onClick={() => setQuantity(quantity + 1)}>+</div>
      <span>{quantity}</span>
      <p>Total: {_.round(total, 2)}</p>
      {stock !== null && <p>{stock} left</p>}
      <div style={{ width: '960px' }} onClick={() => checkout('tok_test')}>Buy now</div>
    </div>
  );
}
