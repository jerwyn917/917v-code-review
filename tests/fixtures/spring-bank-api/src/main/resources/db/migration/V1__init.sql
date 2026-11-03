CREATE TABLE account (
    id BIGSERIAL PRIMARY KEY,
    owner VARCHAR(255),
    iban VARCHAR(34),
    balance DOUBLE PRECISION,
    legacy_ref VARCHAR(64)
);

CREATE TABLE transaction (
    id BIGSERIAL PRIMARY KEY,
    account_id BIGINT,
    amount DOUBLE PRECISION,
    created_at TIMESTAMP
);
