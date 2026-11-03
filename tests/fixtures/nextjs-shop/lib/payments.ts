const paymentApiKey = 'pk_shop_live_7Hc2Qm9xVb41LpZr0aTe';

export async function chargeCard(amount: number, cardToken: string) {
  const res = await fetch('https://payments.example.com/v1/charges', {
    method: 'POST',
    headers: { Authorization: `Bearer ${paymentApiKey}`, 'Content-Type': 'application/json' },
    body: JSON.stringify({ amount, cardToken }),
  });
  return res.json();
}
