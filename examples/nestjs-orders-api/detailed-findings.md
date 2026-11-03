# Code Review — Detailed Findings

**Repository:** nestjs-orders-api · **Review type:** Full codebase review · **Date:** 2026-11-03

**53 findings** — 4 Critical, 14 High, 26 Medium, 9 Low, 0 Informational. 50 Confirmed, 3 Potential.

Every finding below was validated against the source: the file exists, the line exists, and the evidence snippet appears in the file. **Confirmed** = a defect proven by the cited code. **Potential** = a risk that depends on context the reviewers could not verify (deployment, callers, configuration); treat it as something to check, not a proven vulnerability.

## Index

| ID | Severity | Category | Title | Location | Status |
|---|---|---|---|---|---|
| [SEC-001](#sec-001--hard-coded-production-database-password-in-source-and-committed-env) | Critical | Security | Hard-coded production database password in source and committed .env | `src/app.module.ts:13` | Confirmed |
| [SEC-002](#sec-002--jwtguard-decodes-the-jwt-without-verifying-its-signature) | Critical | Security | JwtGuard decodes the JWT without verifying its signature | `src/auth/jwt.guard.ts:8` | Confirmed |
| [SEC-003](#sec-003--order-prices-and-quantities-trusted-from-the-client-balance-manipulation) | Critical | Security | Order prices and quantities trusted from the client (balance manipulation) | `src/orders/orders.controller.ts:21` | Confirmed |
| [SEC-004](#sec-004--unauthenticated-sql-injection-in-get-userssearch) | Critical | Security | Unauthenticated SQL injection in GET /users/search | `src/users/users.service.ts:23` | Confirmed |
| [SEC-005](#sec-005--hard-coded-jwt-signing-secret-in-authservice) | High | Security | Hard-coded JWT signing secret in AuthService | `src/auth/auth.service.ts:6` | Confirmed |
| [SEC-006](#sec-006--passwords-hashed-with-unsalted-md5) | High | Security | Passwords hashed with unsalted MD5 | `src/auth/auth.service.ts:12` | Confirmed |
| [SEC-007](#sec-007--user-and-order-read-endpoints-have-no-authentication-or-ownership-check) | High | Security | User and order read endpoints have no authentication or ownership check | `src/users/users.controller.ts:13` | Confirmed |
| [SEC-008](#sec-008--password-hashes-and-full-user-rows-returned-in-api-responses) | High | Security | Password hashes and full user rows returned in API responses | `src/users/users.service.ts:27` | Confirmed |
| [PERF-001](#perf-001--n1-query-loading-order-items-in-ordersservicelistforuser) | High | Performance | N+1 query loading order items in OrdersService.listForUser | `src/orders/orders.service.ts:15` | Confirmed |
| [API-001](#api-001--post-orders-returns-201-for-validation-errors-and-all-failures) | High | API & Backend | POST /orders returns 201 for validation errors and all failures | `src/orders/orders.controller.ts:22` | Confirmed |
| [API-002](#api-002--placeorder-debits-balance-and-writes-order-without-a-transaction) | High | API & Backend | placeOrder debits balance and writes order without a transaction | `src/orders/orders.service.ts:28` | Confirmed |
| [DB-001](#db-001--typeorm-synchronize-true-enabled-unconditionally-against-the-production-db) | High | Database | TypeORM synchronize: true enabled unconditionally against the production DB | `src/app.module.ts:9` | Confirmed |
| [DB-002](#db-002--monetary-columns-stored-as-float-double-precision) | High | Database | Monetary columns stored as float (double precision) | `src/users/user.entity.ts:21` | Confirmed |
| [TEST-001](#test-001--authentication-authservicelogin-jwtguard-has-no-tests) | High | Testing | Authentication (AuthService.login, JwtGuard) has no tests | `src/auth/jwt.guard.ts:6` | Confirmed |
| [TEST-002](#test-002--ordersserviceplaceorder-balance-debit-has-no-tests) | High | Testing | OrdersService.placeOrder (balance debit) has no tests | `src/orders/orders.service.ts:27` | Confirmed |
| [OPS-001](#ops-001--committed-env-holds-production-db-host-and-password-and-there-is-no-gitignore) | High | DevOps & Infrastructure | Committed .env holds production DB host and password, and there is no .gitignore | `.env:1` | Confirmed |
| [OPS-002](#ops-002--jwt-signing-secret-baked-into-the-docker-image-via-env) | High | DevOps & Infrastructure | JWT signing secret baked into the Docker image via ENV | `Dockerfile:5` | Confirmed |
| [OPS-003](#ops-003--nestjscli-missing-from-devdependencies-so-nest-build-fails-in-ci-and-docker) | High | DevOps & Infrastructure | @nestjs/cli missing from devDependencies, so `nest build` fails in CI and Docker | `package.json:6` | Confirmed |
| [ARC-001](#arc-001--token-issuing-and-checking-split-across-classes-with-no-shared-auth-module-api) | Medium | Architecture | Token issuing and checking split across classes with no shared auth module API | `src/auth/jwt.guard.ts:7` | Confirmed |
| [ARC-002](#arc-002--order-validation-and-bulk-discount-pricing-rule-live-in-the-controller) | Medium | Architecture | Order validation and bulk-discount pricing rule live in the controller | `src/orders/orders.controller.ts:23` | Confirmed |
| [ARC-003](#arc-003--balance-debit-rule-lives-in-ordersservice-and-bypasses-the-users-domain) | Medium | Architecture | Balance debit rule lives in OrdersService and bypasses the Users domain | `src/orders/orders.service.ts:28` | Confirmed |
| [ARC-004](#arc-004--circular-dependency-between-users-and-orders-hidden-with-forwardref) | Medium | Architecture | Circular dependency between Users and Orders, hidden with forwardRef | `src/users/users.service.ts:5` | Confirmed |
| [SEC-009](#sec-009--no-brute-force-protection-on-post-authlogin) | Medium | Security | No brute-force protection on POST /auth/login | `src/auth/auth.controller.ts:8` | Confirmed |
| [SEC-010](#sec-010--login-tokens-issued-without-expiry) | Medium | Security | Login tokens issued without expiry | `src/auth/auth.service.ts:21` | Confirmed |
| [PERF-002](#perf-002--unbounded-full-table-fetch-of-all-orders-on-get-orders) | Medium | Performance | Unbounded full-table fetch of all orders on GET /orders | `src/orders/orders.service.ts:23` | Confirmed |
| [PERF-003](#perf-003--order-items-inserted-one-by-one-with-sequential-awaits-in-placeorder) | Medium | Performance | Order items inserted one-by-one with sequential awaits in placeOrder | `src/orders/orders.service.ts:33` | Confirmed |
| [API-003](#api-003--no-rate-limiting-on-login-or-the-search-endpoint) | Medium | API & Backend | No rate limiting on login or the search endpoint | `src/app.module.ts:8` | Potential |
| [API-004](#api-004--no-request-validation-no-global-validationpipe-untyped-bodies-and-params) | Medium | API & Backend | No request validation: no global ValidationPipe, untyped bodies and params | `src/main.ts:5` | Confirmed |
| [API-005](#api-005--post-orders-debits-balance-with-no-idempotency-protection) | Medium | API & Backend | POST /orders debits balance with no idempotency protection | `src/orders/orders.controller.ts:19` | Confirmed |
| [API-006](#api-006--get-usersid-returns-200-for-missing-users-and-the-raw-user-entity) | Medium | API & Backend | GET /users/:id returns 200 for missing users and the raw User entity | `src/users/users.service.ts:27` | Confirmed |
| [DB-003](#db-003--orderitemorderid-has-no-foreign-key-to-order) | Medium | Database | OrderItem.orderId has no foreign key to Order | `src/orders/order.entity.ts:22` | Confirmed |
| [DB-004](#db-004--missing-indexes-on-orderuserid-and-order_itemorderid) | Medium | Database | Missing indexes on order.userId and order_item.orderId | `src/orders/orders.service.ts:16` | Confirmed |
| [DB-005](#db-005--useremail-has-no-unique-constraint-though-login-treats-it-as-unique) | Medium | Database | User.email has no unique constraint though login treats it as unique | `src/users/user.entity.ts:9` | Confirmed |
| [DB-006](#db-006--no-check-constraint-keeps-userbalance-non-negative) | Medium | Database | No CHECK constraint keeps user.balance non-negative | `src/users/user.entity.ts:21` | Confirmed |
| [TEST-003](#test-003--jest-config-missing-no-ts-jest-transform-e2e-config-file-absent) | Medium | Testing | Jest config missing: no ts-jest transform, e2e config file absent | `package.json:8` | Confirmed |
| [TEST-004](#test-004--usersservice-spec-asserts-only-instantiation-no-behaviour-tested) | Medium | Testing | UsersService spec asserts only instantiation; no behaviour tested | `src/users/users.service.spec.ts:4` | Confirmed |
| [TEST-005](#test-005--no-e2eintegration-tests-only-a-skipped-placeholder-exists) | Medium | Testing | No e2e/integration tests: only a skipped placeholder exists | `test/app.e2e-spec.ts:1` | Confirmed |
| [OPS-004](#ops-004--ci-runs-no-tests-lint-or-dependency-audit-and-only-on-push) | Medium | DevOps & Infrastructure | CI runs no tests, lint or dependency audit, and only on push | `.github/workflows/ci.yml:2` | Confirmed |
| [OPS-005](#ops-005--actionscheckout-pinned-to-a-mutable-branch-master) | Medium | DevOps & Infrastructure | actions/checkout pinned to a mutable branch (@master) | `.github/workflows/ci.yml:7` | Confirmed |
| [OPS-006](#ops-006--no-lockfile-so-ci-and-docker-use-non-reproducible-npm-install) | Medium | DevOps & Infrastructure | No lockfile, so CI and Docker use non-reproducible `npm install` | `.github/workflows/ci.yml:11` | Confirmed |
| [OPS-007](#ops-007--unpinned-nodelatest-base-image) | Medium | DevOps & Infrastructure | Unpinned node:latest base image | `Dockerfile:1` | Confirmed |
| [OPS-008](#ops-008--copy---without-a-dockerignore-copies-env-and-host-artifacts-into-the-image) | Medium | DevOps & Infrastructure | COPY . . without a .dockerignore copies .env and host artifacts into the image | `Dockerfile:3` | Confirmed |
| [OPS-009](#ops-009--container-runs-as-root-no-user-instruction) | Medium | DevOps & Infrastructure | Container runs as root (no USER instruction) | `Dockerfile:8` | Confirmed |
| [OPS-010](#ops-010--deployment-env-vars-do-not-match-what-the-code-reads) | Medium | DevOps & Infrastructure | Deployment env vars do not match what the code reads | `src/app.module.ts:11` | Confirmed |
| [CQ-001](#cq-001--consolelog-in-bootstrap-violates-the-nest-logger-convention) | Low | Code Quality | console.log in bootstrap violates the Nest Logger convention | `src/main.ts:8` | Confirmed |
| [SEC-011](#sec-011--cors-enabled-for-all-origins-and-no-security-headers) | Low | Security | CORS enabled for all origins and no security headers | `src/main.ts:5` | Confirmed |
| [API-007](#api-007--non-restful-route-for-a-users-orders-and-no-api-versioning) | Low | API & Backend | Non-RESTful route for a user's orders, and no API versioning | `src/orders/orders.controller.ts:14` | Confirmed |
| [DB-007](#db-007--db-connection-has-no-ssl-or-pool-configuration) | Low | Database | DB connection has no SSL or pool configuration | `src/app.module.ts:9` | Potential |
| [DB-008](#db-008--role-and-status-are-unconstrained-free-text-columns) | Low | Database | role and status are unconstrained free-text columns | `src/users/user.entity.ts:18` | Confirmed |
| [DB-009](#db-009--leading-wildcard-ilike-user-search-cannot-use-an-index) | Low | Database | Leading-wildcard ILIKE user search cannot use an index | `src/users/users.service.ts:24` | Potential |
| [OPS-011](#ops-011--ci-targets-end-of-life-node-20) | Low | DevOps & Infrastructure | CI targets end-of-life Node 20 | `.github/workflows/ci.yml:10` | Confirmed |
| [OPS-012](#ops-012--single-stage-image-ships-devdependencies-sources-and-build-toolchain) | Low | DevOps & Infrastructure | Single-stage image ships devDependencies, sources and build toolchain | `Dockerfile:1` | Confirmed |
| [OPS-013](#ops-013--no-health-endpoint-healthcheck-or-graceful-shutdown-hooks) | Low | DevOps & Infrastructure | No health endpoint, HEALTHCHECK or graceful shutdown hooks | `src/main.ts:4` | Confirmed |

### SEC-001 · Hard-coded production database password in source and committed .env

| Field | Value |
|---|---|
| Severity | Critical |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/app.module.ts:13`](../../src/app.module.ts#L13)–14 |
| Reported by | security-reviewer |
| References | CWE-798, A07:2021 |

**Description**

The PostgreSQL password is a string literal in AppModule's TypeORM config. The same credential, with a production DB hostname, is also in the committed .env file. No .gitignore exists in the repo, so .env is tracked. The value looks like a real production credential, not a fixture.

**Evidence**

```ts
username: 'orders',
password: '[REDACTED]',
```

**Potential impact**

Anyone with read access to the repository, its forks, CI logs or built images has the production database credential, giving full read/write access to user and order data.

**Recommended solution**

Rotate the database password now. Read it from the environment (for example `password: process.env.DB_PASSWORD` via @nestjs/config with a validated schema that fails at startup when it is missing), remove .env from version control, add a .gitignore, commit only a .env.example with placeholder values, and purge the secret from git history.

**Also found at:** [`.env:2`](../../.env#L2)


### SEC-002 · JwtGuard decodes the JWT without verifying its signature

| Field | Value |
|---|---|
| Severity | Critical |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/auth/jwt.guard.ts:8`](../../src/auth/jwt.guard.ts#L8)–15 |
| Reported by | security-reviewer |
| References | CWE-347, A07:2021 |

**Description**

JwtGuard calls jwt.decode(), which only base64-decodes the token and never checks the signature, algorithm or expiry. Any well-formed JWT, including one the attacker writes with an arbitrary `sub` and `role` and any (or no) signature, passes the guard and becomes req.user. Reachability: the guard protects POST /orders, the only authenticated route. Control: anonymous internet caller. Mitigations: there is no APP_GUARD, Passport strategy or other jwt.verify call anywhere in src. Blast radius: money. OrdersController.create passes req.user.sub straight to placeOrder, which debits that user's balance.

**Evidence**

```ts
const header: string = req.headers['authorization'] || '';
const token = header.replace('Bearer ', '');
const payload = jwt.decode(token);
if (!payload) {
  return false;
}
req.user = payload;
```

**Potential impact**

An unauthenticated attacker can forge a token for any user id and place orders that debit any customer's balance. Any future role-based check would be bypassed the same way, by forging `role`.

**Recommended solution**

Verify the token: `[REDACTED] payload = jwt.verify(token, secret, { algorithms: ['HS256'] })` in a try/catch that throws UnauthorizedException, with the secret coming from config. Better, adopt @nestjs/jwt + JwtService.verifyAsync (or @nestjs/passport's JwtStrategy) and require the 'Bearer ' prefix explicitly.

**Also found at:** [`src/orders/orders.controller.ts:28`](../../src/orders/orders.controller.ts#L28)


### SEC-003 · Order prices and quantities trusted from the client (balance manipulation)

| Field | Value |
|---|---|
| Severity | Critical |
| Category | Security (also: API & Backend) |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.controller.ts:21`](../../src/orders/orders.controller.ts#L21)–28 |
| Reported by | backend-reviewer, security-reviewer |
| References | CWE-602, A04:2021 |

**Description**

POST /orders takes `body: any` and copies each item, including `price`, from the request into placeOrder. The total is computed from client prices and quantities, then subtracted from the user's balance. Nothing validates the input: there is no DTO, no ValidationPipe, no catalogue price lookup, no positivity check and no sufficient-balance check. A negative price or quantity makes `total` negative, so the debit increases the balance. Control: any caller who can pass the guard, which currently means anyone (see the JwtGuard finding).

**Evidence**

```ts
async create(@Req() req: any, @Body() body: any) {
  try {
    if (!body.items || body.items.length === 0) {
      return { error: 'Order must contain items' };
    }
    const discount = body.items.length > 10 ? 0.1 : 0;
    const items = body.items.map((i: any) => ({ ...i, price: i.price * (1 - discount) }));
    return await this.orders.placeOrder(req.user.sub, items);
```

**Potential impact**

Users can buy items at any price they choose (for example 0.01) or credit their own balance arbitrarily with negative prices or quantities. This is direct financial loss.

**Recommended solution**

Accept only `{ sku, quantity }` through a class-validator DTO (`@IsString() sku`, `@IsInt() @Min(1) quantity`, `@ArrayNotEmpty`, `@ValidateNested`), with a global `ValidationPipe({ whitelist: true, forbidNonWhitelisted: true })`. Look up prices server-side in OrdersService, and reject the order when `total > user.balance`.

**Also found at:** [`src/orders/orders.service.ts:29`](../../src/orders/orders.service.ts#L29), [`src/orders/orders.controller.ts:26`](../../src/orders/orders.controller.ts#L26)

<sub>Validation: severity raised from High to Critical on merge with a duplicate; merged by orchestrator decision: same root cause: client-controlled price feeds the debit; exploit-enabling validation is owned by security</sub>


### SEC-004 · Unauthenticated SQL injection in GET /users/search

| Field | Value |
|---|---|
| Severity | Critical |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/users.service.ts:23`](../../src/users/users.service.ts#L23)–25 |
| Reported by | security-reviewer |
| References | CWE-89, A03:2021 |

**Description**

UsersService.search() puts the `q` query parameter straight into a raw SQL string passed to DataSource.query(). Reachability: routed by UsersController.search (GET /users/search). Control: anonymous caller, because the controller has no guard and there is no global guard. Mitigations: none. There is no ValidationPipe and no DTO, and the query is not parameterized.

**Evidence**

```ts
search(q: string) {
  return this.dataSource.query(`SELECT * FROM "user" WHERE name ILIKE '%${q}%'`);
}
```

**Potential impact**

Anyone on the network can read the whole database (users, password hashes, balances, orders). Because the DB account is the schema owner (synchronize: true), they can also modify balances or drop tables with stacked or UNION-based payloads.

**Recommended solution**

Use a parameterized query: `this.dataSource.query('SELECT id, name FROM "user" WHERE name ILIKE $1', [`%${q}%`])`, or the repository: `this.repo.find({ where: { name: ILike(`%${q}%`) }, select: ['id', 'name'] })`. Also put the route behind authentication.

**Also found at:** [`src/users/users.controller.ts:9`](../../src/users/users.controller.ts#L9)


### SEC-005 · Hard-coded JWT signing secret in AuthService

| Field | Value |
|---|---|
| Severity | High |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/auth/auth.service.ts:6`](../../src/auth/auth.service.ts#L6) |
| Reported by | security-reviewer |
| References | CWE-798, A02:2021 |

**Description**

The HMAC key used to sign login tokens is a module-level string literal. Anyone with source access can mint valid tokens for any user. This matters even after the guard is fixed to verify signatures.

**Evidence**

```ts
const JWT_SECRET = '[REDACTED]';
```

**Potential impact**

Once JwtGuard verifies signatures, anyone who has seen the repo (or the Docker image) can still forge tokens and impersonate any user, including privileged roles.

**Recommended solution**

Rotate the key and load it from configuration (for example ConfigService/JwtModule.registerAsync with `secret: config.getOrThrow('JWT_SECRET')`), with no literal fallback. Use a long random value from a secret manager.

**Also found at:** [`src/auth/auth.service.ts:21`](../../src/auth/auth.service.ts#L21)


### SEC-006 · Passwords hashed with unsalted MD5

| Field | Value |
|---|---|
| Severity | High |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/auth/auth.service.ts:12`](../../src/auth/auth.service.ts#L12)–14 |
| Reported by | security-reviewer |
| References | CWE-916, A02:2021 |

**Description**

hashPassword() uses a single unsalted MD5 digest, and login compares against it. MD5 is fast and unsalted, so identical passwords share hashes and leaked hashes crack quickly with rainbow tables or GPUs. The hashes are also reachable through the SQL injection and the profile endpoint, which returns passwordHash.

**Evidence**

```ts
hashPassword(password: string): string {
  return crypto.createHash('md5').update(password).digest('hex');
}
```

**Potential impact**

Any hash disclosure turns quickly into plaintext passwords, enabling account takeover here and credential stuffing elsewhere.

**Recommended solution**

Use a slow, salted password hash: bcrypt (cost >= 12) or argon2id via `argon2.hash` / `argon2.verify`. Rehash on next successful login to migrate existing users. This needs a new dependency (bcrypt or argon2), because Node's built-in alternative is crypto.scrypt with a per-user salt.

**Also found at:** [`src/auth/auth.service.ts:18`](../../src/auth/auth.service.ts#L18)


### SEC-007 · User and order read endpoints have no authentication or ownership check

| Field | Value |
|---|---|
| Severity | High |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/users.controller.ts:13`](../../src/users/users.controller.ts#L13)–16 |
| Reported by | security-reviewer |
| References | CWE-639, A01:2021 |

**Description**

GET /users/:id, GET /users/search, GET /orders and GET /orders/user/:userId have no @UseGuards, and there is no global APP_GUARD. Only POST /orders is guarded. Nothing compares the requested id with the caller's identity (IDOR). GET /orders returns every order in the system. Control: anonymous caller with sequential integer ids.

**Evidence**

```ts
@Get(':id')
profile(@Param('id') id: string) {
  return this.users.getProfileWithOrders(Number(id));
}
```

**Potential impact**

Anyone can enumerate every user's profile, balance and order history, and list all orders, by iterating ids. This exposes customer PII and financial data.

**Recommended solution**

Apply a verified JWT guard globally (APP_GUARD) and mark only /auth/login as @Public(). In the services, enforce ownership, for example `if (id !== req.user.sub && req.user.role !== 'admin') throw new ForbiddenException()`. Restrict GET /orders (list all) to an admin role.

**Also found at:** [`src/users/users.controller.ts:8`](../../src/users/users.controller.ts#L8), [`src/orders/orders.controller.ts:9`](../../src/orders/orders.controller.ts#L9), [`src/orders/orders.controller.ts:14`](../../src/orders/orders.controller.ts#L14)


### SEC-008 · Password hashes and full user rows returned in API responses

| Field | Value |
|---|---|
| Severity | High |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/users.service.ts:27`](../../src/users/users.service.ts#L27)–30 |
| Reported by | security-reviewer |
| References | CWE-200, A01:2021 |

**Description**

getProfileWithOrders spreads the whole User entity, including passwordHash, role and balance, into the response. search() returns `SELECT *` rows from the user table. The User entity has no @Exclude/select:false on passwordHash, and there is no ClassSerializerInterceptor. Combined with the unauthenticated routes and unsalted MD5, this exposes crackable credentials.

**Evidence**

```ts
async getProfileWithOrders(id: number) {
  const user = await this.findById(id);
  const orders = await this.orders.listForUser(id);
  return { ...user, orders };
```

**Potential impact**

Every user's email and password hash is retrievable by anyone, so passwords can be recovered offline.

**Recommended solution**

Return an explicit response DTO (id, name, email only where authorized). Mark passwordHash `@Column({ select: false })` and/or use class-transformer `@Exclude()` with a ClassSerializerInterceptor. Select explicit columns in search().

**Also found at:** [`src/users/users.service.ts:24`](../../src/users/users.service.ts#L24), [`src/users/user.entity.ts:15`](../../src/users/user.entity.ts#L15)


### PERF-001 · N+1 query loading order items in OrdersService.listForUser

| Field | Value |
|---|---|
| Severity | High |
| Category | Performance |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.service.ts:15`](../../src/orders/orders.service.ts#L15)–21 |
| Reported by | performance-reviewer |

**Description**

listForUser() fetches a user's orders, then awaits a separate OrderItem query for each order inside a for loop. This is reachable on two hot request paths: GET /orders/user/:userId (OrdersController.forUser) and GET /users/:id (UsersService.getProfileWithOrders calls listForUser). Neither route has a guard, so any caller can trigger it. A user with N orders costs 1 + N queries, all run one after another (a customer with 200 orders = 201 queries on one profile view). The query count grows with each user's order history, and listForUser has no pagination.

**Evidence**

```ts
  async listForUser(userId: number) {
    const orders = await this.orders.find({ where: { userId } });
    for (const order of orders) {
      (order as any).items = await this.items.find({ where: { orderId: order.id } });
    }
    return orders;
  }
```

**Potential impact**

Latency and DB load grow linearly with each user's order count on the profile and per-user order endpoints. Each request holds a pool connection for N sequential round trips, so heavy users or repeated calls can exhaust the connection pool.

**Recommended solution**

Fetch all items in one query and group them in memory: `const orders = await this.orders.find({ where: { userId }, order: { id: 'DESC' }, take, skip }); const items = orders.length ? await this.items.find({ where: { orderId: In(orders.map(o => o.id)) } }) : []; const byOrder = new Map<number, OrderItem[]>(); items.forEach(i => (byOrder.get(i.orderId) ?? byOrder.set(i.orderId, []).get(i.orderId)!).push(i)); orders.forEach(o => (o as any).items = byOrder.get(o.id) ?? []);`. A better option is to declare an `@OneToMany(() => OrderItem, i => i.order)` relation on Order and use `find({ where: { userId }, relations: { items: true } })`. Either way, total queries drop to 2 (or 1). Also paginate this list.

**Also found at:** [`src/users/users.service.ts:29`](../../src/users/users.service.ts#L29), [`src/orders/orders.controller.ts:16`](../../src/orders/orders.controller.ts#L16)


### API-001 · POST /orders returns 201 for validation errors and all failures

| Field | Value |
|---|---|
| Severity | High |
| Category | API & Backend (also: Code Quality) |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.controller.ts:22`](../../src/orders/orders.controller.ts#L22)–29 |
| Reported by | architecture-reviewer, backend-reviewer |

**Description**

The create handler returns `{ error: 'Order must contain items' }` as a normal value, so Nest sends it with 201 Created. The surrounding `try { ... } catch (e) {}` turns every exception from placeOrder (missing user, DB failure, TypeError on malformed items) into a 201 with an empty body. The error shape also differs from Nest's standard `{ statusCode, message, error }` body that the other endpoints use (for example, UnauthorizedException in AuthService). The repo has no global exception filter.

**Evidence**

```ts
try {
  if (!body.items || body.items.length === 0) {
    return { error: 'Order must contain items' };
  }
  ...
  return await this.orders.placeOrder(req.user.sub, items);
} catch (e) {}
```

**Potential impact**

Clients cannot tell a failed order from a successful one. A payment-like operation that partly failed (balance already debited, see the transaction finding) is reported as created, and nothing logs the failure.

**Recommended solution**

Remove the try/catch and throw Nest HTTP exceptions instead: `BadRequestException` for an empty items list (or let a DTO with `@ArrayNotEmpty()` and a global ValidationPipe handle it), and `NotFoundException` or `ConflictException` from the service for domain errors. If a uniform error envelope is wanted, register one global ExceptionFilter in main.ts.

**Also found at:** [`src/orders/orders.service.ts:30`](../../src/orders/orders.service.ts#L30), [`src/auth/auth.service.ts:19`](../../src/auth/auth.service.ts#L19)

<sub>Validation: merged by orchestrator decision: same try/catch block; one fix (throw Nest exceptions, remove empty catch)</sub>


### API-002 · placeOrder debits balance and writes order without a transaction

| Field | Value |
|---|---|
| Severity | High |
| Category | API & Backend (also: Database) |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.service.ts:28`](../../src/orders/orders.service.ts#L28)–35 |
| Reported by | backend-reviewer, database-reviewer |

**Description**

placeOrder makes several separate writes with no transaction or QueryRunner: it saves the user's new balance, then the order, then each OrderItem in a loop. If any later write fails, the balance has already been debited and is never restored. The balance update is also an unlocked read-modify-write, so two concurrent orders can both read the same balance and one debit is lost. Nothing checks for sufficient funds, so the balance can go negative. The order is marked 'paid' before its items exist. Reachability: called from the live POST /orders route.

**Evidence**

```ts
const user = await this.users.findById(userId);
const total = items.reduce((sum, i) => sum + i.price * i.quantity, 0);
user.balance = user.balance - total;
await this.users.save(user);
const order = await this.orders.save({ userId, total, status: 'paid' });
for (const item of items) {
  await this.items.save({ orderId: order.id, ...item });
}
```

**Potential impact**

A database error or crash partway through leaves users charged with no order, or with an order missing some items. Concurrent requests can under-debit, and a user with insufficient funds can still place orders.

**Recommended solution**

Wrap the whole operation in `this.dataSource.transaction(async (m) => { ... })`. Inside it, load the user with `m.findOne(User, { where: { id }, lock: { mode: 'pessimistic_write' } })`, or do an atomic `UPDATE user SET balance = balance - :total WHERE id = :id AND balance >= :total`. Throw NotFoundException when the user does not exist and a ConflictException or UnprocessableEntityException when funds are insufficient. Save the order and its items through the same manager `m`.

**Also found at:** [`src/users/users.service.ts:33`](../../src/users/users.service.ts#L33)

<sub>Validation: merged by orchestrator decision: same fix: one transaction with a row lock or conditional atomic debit</sub>


### DB-001 · TypeORM synchronize: true enabled unconditionally against the production DB

| Field | Value |
|---|---|
| Severity | High |
| Category | Database |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/app.module.ts:9`](../../src/app.module.ts#L9)–18 |
| Reported by | database-reviewer |

**Description**

AppModule configures TypeORM with `synchronize: true` and no environment gating (no NODE_ENV check, no separate config for production). The committed .env points DB_HOST at `prod-db.internal.acme.io`, and the review brief says the repo has no migrations folder, so schema auto-sync is the only schema-management mechanism in every environment. On each boot TypeORM diffs the entities against the live schema and issues DDL. Renaming an entity property or changing a column type (for example fixing the float money columns) makes it DROP the old column and ADD a new one, which deletes the data in it. Reachability: this runs on every app start. Control: any developer change to an entity. Mitigations: none found in the files read.

**Evidence**

```ts
    TypeOrmModule.forRoot({
      type: 'postgres',
      host: process.env.DB_HOST || 'localhost',
...
      autoLoadEntities: true,
      synchronize: true,
    }),
```

**Potential impact**

A routine entity refactor deployed to production can silently drop live columns such as user.balance or order.total, permanently losing financial data. Schema changes are also not reviewable, versioned or reversible.

**Recommended solution**

Set `synchronize: false` (or `synchronize: process.env.NODE_ENV === 'development'` at most), add a TypeORM DataSource config with `migrations: ['dist/migrations/*.js']` and `migrationsRun: false`, generate an initial migration from the current schema with `typeorm migration:generate`, and run migrations as an explicit deploy step.

**Also found at:** [`.env:1`](../../.env#L1)


### DB-002 · Monetary columns stored as float (double precision)

| Field | Value |
|---|---|
| Severity | High |
| Category | Database |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/user.entity.ts:21`](../../src/users/user.entity.ts#L21)–22 |
| Reported by | database-reviewer |

**Description**

User.balance, Order.total and OrderItem.price are declared `@Column('float')`, which maps to Postgres `double precision`. Binary floating point cannot represent most decimal amounts exactly. OrdersService.placeOrder computes `user.balance - total` from `price * quantity` sums, and OrdersController applies a 0.9 discount multiplier, so rounding error is introduced and then stored back in the balance on every order.

**Evidence**

```ts
  @Column('float', { default: 0 })
  balance: number;
```

**Potential impact**

Balances and order totals drift by fractions of a cent (for example 0.1 + 0.2 = 0.30000000000000004). Over many orders the stored balances stop reconciling with the sum of order totals, which corrupts the ledger and breaks equality comparisons and reports.

**Recommended solution**

Use `@Column('numeric', { precision: 12, scale: 2, transformer: ... })` (or store integer minor units as `bigint`, e.g. `balanceCents`). Do arithmetic with integers or a decimal library, and add a migration that converts existing values with explicit rounding.

**Also found at:** [`src/orders/order.entity.ts:15`](../../src/orders/order.entity.ts#L15), [`src/orders/order.entity.ts:36`](../../src/orders/order.entity.ts#L36)


### TEST-001 · Authentication (AuthService.login, JwtGuard) has no tests

| Field | Value |
|---|---|
| Severity | High |
| Category | Testing |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/auth/jwt.guard.ts:6`](../../src/auth/jwt.guard.ts#L6)–16 |
| Reported by | testing-reviewer |

**Description**

JwtGuard.canActivate is the only authorization control on POST /orders, and AuthService.login issues the tokens. Neither has a unit or e2e test. A single negative test, such as 'a token signed with a different key is rejected' or 'an unsigned/forged token returns 401', would fail against the current guard, which calls jwt.decode (no signature or expiry check) instead of jwt.verify. Login also has no test for an unknown email, a wrong password, or the token's claims. The underlying guard and hashing defects belong to security-reviewer. This finding covers only the missing tests that would have caught them.

**Evidence**

```ts
Searched src/users/users.service.spec.ts and test/app.e2e-spec.ts for JwtGuard, AuthService, login, '/auth' and Authorization headers. There are no references, and no auth.service.spec.ts or jwt.guard.spec.ts exists alongside src/auth/auth.service.ts or src/auth/jwt.guard.ts.
```

**Potential impact**

Authentication regressions and forged-token acceptance ship without any automated signal. Anyone who can craft a JWT-shaped string can reach the money-moving endpoint, and no test will flag it.

**Recommended solution**

Add src/auth/jwt.guard.spec.ts that builds an ExecutionContext stub and asserts: no header gives false/401, a malformed token is rejected, a token signed with the wrong secret is rejected, an expired token is rejected, and a valid token sets req.user. Add src/auth/auth.service.spec.ts covering an unknown email, a wrong password and a successful login (decode the token and assert the sub/role claims). Add an e2e case: POST /orders with a forged token returns 401.

**Also found at:** [`src/auth/auth.service.ts:16`](../../src/auth/auth.service.ts#L16), [`src/auth/auth.controller.ts:8`](../../src/auth/auth.controller.ts#L8)


### TEST-002 · OrdersService.placeOrder (balance debit) has no tests

| Field | Value |
|---|---|
| Severity | High |
| Category | Testing |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.service.ts:27`](../../src/orders/orders.service.ts#L27)–36 |
| Reported by | testing-reviewer |

**Description**

placeOrder is the money path: it loads the user, computes the total from caller-supplied price*quantity, debits user.balance, saves the user, then saves the order and each item in separate writes. No test file covers OrdersService or OrdersController. The repo's only test files are src/users/users.service.spec.ts (instantiation only) and test/app.e2e-spec.ts (a skipped placeholder), and neither references OrdersService, placeOrder or /orders. The paths a test would exercise are all unchecked: a missing user (findById returns null, so user.balance throws), insufficient balance (the balance can go negative), zero, negative or non-integer quantity and price, floating-point rounding of the total, a failure partway through after the balance was already debited, concurrent orders for the same user, and the controller's 10% discount boundary at more than 10 items. Reachability: POST /orders is routed and guarded only by JwtGuard. Blast radius: money.

**Evidence**

```ts
Searched the repo's two test files (src/users/users.service.spec.ts, test/app.e2e-spec.ts) for OrdersService, placeOrder, OrdersController and '/orders'. Neither file references them, and there is no orders.service.spec.ts or orders.controller.spec.ts next to the sources.
```

**Potential impact**

Any regression or existing defect in the debit logic (negative balances, a debit without an order on partial failure, wrong totals from discount or rounding) reaches production undetected and directly loses or misstates customer money.

**Recommended solution**

Add src/orders/orders.service.spec.ts using Test.createTestingModule with mocked Repository<Order>, Repository<OrderItem> and UsersService, and assert outcomes rather than calls: the balance is debited by the exact total, an unknown user is rejected, insufficient balance is rejected with no writes, invalid quantity or price is rejected, and when items.save fails the debit is not persisted. Add an e2e test for POST /orders against a real Postgres (testcontainers or a test DB) that covers the discount boundary (10 vs 11 items) and two concurrent orders that together exceed the balance.

**Also found at:** [`src/orders/orders.controller.ts:26`](../../src/orders/orders.controller.ts#L26), [`src/orders/orders.service.ts:15`](../../src/orders/orders.service.ts#L15)


### OPS-001 · Committed .env holds production DB host and password, and there is no .gitignore

| Field | Value |
|---|---|
| Severity | High |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`.env:1`](../../.env#L1)–2 |
| Reported by | devops-reviewer |
| References | CWE-312, A05:2021 |

**Description**

A .env file containing DB_HOST and DB_PASSWORD is part of the repository. The host value names an internal production database, and the password is the same literal hard-coded at src/app.module.ts:14. The repository has no .gitignore, so .env (and node_modules/dist after a local build) will keep being committed. There is also no .env.example that documents the required variables without real values.

**Evidence**

```
DB_HOST=[REDACTED]
DB_PASSWORD=[REDACTED]
```

**Potential impact**

Anyone with read access to the repository, or to any clone or fork of it, gets the production database location and credentials.

**Recommended solution**

Delete .env from the repo and purge it from history (git filter-repo/BFG). Rotate the database password. Add a .gitignore listing .env, node_modules and dist. Commit a .env.example with placeholder values for DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_NAME, JWT_SECRET and PORT.


### OPS-002 · JWT signing secret baked into the Docker image via ENV

| Field | Value |
|---|---|
| Severity | High |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`Dockerfile:5`](../../Dockerfile#L5) |
| Reported by | devops-reviewer |
| References | CWE-798, A05:2021 |

**Description**

The Dockerfile sets JWT_SECRET as a literal in an ENV instruction. ENV values are stored in the image config and layer history, so anyone who can pull the image can read them with `docker inspect` or `docker history`. The value is the same literal hard-coded at src/auth/auth.service.ts:6, so the leaked value is the live token-signing key. The application never reads process.env.JWT_SECRET, so this ENV also has no effect: it exposes the secret without making it configurable. Reachability: every image built from this Dockerfile. Control: anyone with registry pull access. Mitigations: none in the repo (no .dockerignore, no build secrets, no runtime injection).

**Evidence**

```dockerfile
ENV JWT_SECRET=[REDACTED]
```

**Potential impact**

Anyone with access to the image or registry can recover the signing key and mint valid JWTs for any user id and role, including admin roles.

**Recommended solution**

Remove the ENV line. Inject JWT_SECRET at runtime from the orchestrator's secret store (Kubernetes Secret, ECS/SSM, Docker secrets), read it via process.env / @nestjs/config in AuthService, and fail startup if it is missing. Rotate the key, because it is now in image history and git history.

**Also found at:** [`src/auth/auth.service.ts:6`](../../src/auth/auth.service.ts#L6)


### OPS-003 · @nestjs/cli missing from devDependencies, so `nest build` fails in CI and Docker

| Field | Value |
|---|---|
| Severity | High |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`package.json:6`](../../package.json#L6) |
| Reported by | devops-reviewer |

**Description**

The build script runs `nest build`, but the `nest` binary is provided only by @nestjs/cli, which is not in dependencies or devDependencies. Both the CI job (`npm install` then `npm run build`) and the Dockerfile (`RUN npm install` then `RUN npm run build`) install only the declared packages, so the build step should fail with `nest: not found`. Neither the GitHub-hosted runner nor the node base image ships @nestjs/cli globally.

**Evidence**

```json
    "build": "nest build",
```

**Potential impact**

The CI pipeline cannot go green and the Docker image cannot be built, so nothing can be deployed from this repository as it stands.

**Recommended solution**

Add "@nestjs/cli": "^10.3.0" (and "@types/node") to devDependencies and commit the resulting package-lock.json. Alternatively, change the script to `tsc -p tsconfig.json`.

**Also found at:** [`Dockerfile:6`](../../Dockerfile#L6), [`.github/workflows/ci.yml:12`](../../.github/workflows/ci.yml#L12)


### ARC-001 · Token issuing and checking split across classes with no shared auth module API

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Architecture |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/auth/jwt.guard.ts:7`](../../src/auth/jwt.guard.ts#L7)–10 |
| Reported by | architecture-reviewer |

**Description**

AuthService signs tokens with a module-private constant (auth.service.ts:21). JwtGuard reimplements token handling on its own with a direct `jsonwebtoken` import and a manual header parse, and it has no access to the signing configuration. The guard is not declared or exported by AuthModule (auth.module.ts:[REDACTED]). OrdersController imports it straight from '../auth/jwt.guard' (orders.controller.ts:3), and OrdersModule does not import AuthModule. Auth is therefore not encapsulated: the issue and verify halves of one concern have no shared configuration or provider, and consumers reach into the auth folder's internals. This design split is what lets the guard drift from the signer (the verification flaw itself is left to the security reviewer).

**Evidence**

```ts
    const req = context.switchToHttp().getRequest();
    const header: string = req.headers['authorization'] || '';
    const token = header.replace('Bearer ', '');
    const payload = jwt.decode(token);
```

**Potential impact**

Token rules (secret, algorithm, expiry, claims) must be changed in two places that cannot see each other. Every new protected module copies the cross-module file import.

**Recommended solution**

Centralise token handling in AuthModule: register `JwtModule.registerAsync` from @nestjs/jwt (or a small TokenService) that is configured once from ConfigService. Inject JwtService into both AuthService and JwtGuard, provide and export JwtGuard from AuthModule, and have OrdersModule import AuthModule (or register the guard as APP_GUARD with a @Public() decorator).

**Also found at:** [`src/auth/auth.service.ts:21`](../../src/auth/auth.service.ts#L21), [`src/auth/auth.module.ts:6`](../../src/auth/auth.module.ts#L6), [`src/orders/orders.controller.ts:3`](../../src/orders/orders.controller.ts#L3)


### ARC-002 · Order validation and bulk-discount pricing rule live in the controller

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Architecture |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.controller.ts:23`](../../src/orders/orders.controller.ts#L23)–27 |
| Reported by | architecture-reviewer |

**Description**

The README convention says business logic lives in services and controllers only map HTTP to service calls. OrdersController.create instead holds the input validation (non-empty items) and a pricing rule: a 10% discount when an order has more than 10 lines. Both thresholds are magic numbers. OrdersService.placeOrder then trusts whatever prices it receives. The pricing rule is therefore tied to this one HTTP route, and any other caller of placeOrder (a job, another endpoint or a test) bypasses it. `class-validator` is a dependency but no DTO is used, so validation is hand-coded in the controller.

**Evidence**

```ts
      if (!body.items || body.items.length === 0) {
        return { error: 'Order must contain items' };
      }
      const discount = body.items.length > 10 ? 0.1 : 0;
      const items = body.items.map((i: any) => ({ ...i, price: i.price * (1 - discount) }));
```

**Potential impact**

The pricing rule cannot be unit-tested without HTTP, will be duplicated or skipped by future callers, and breaks the project's stated layering convention.

**Recommended solution**

Move the discount computation into OrdersService (or a small pricing method it owns), with named constants such as BULK_DISCOUNT_MIN_LINES = 10 and BULK_DISCOUNT_RATE = 0.1. Move the shape and emptiness checks to a CreateOrderDto with class-validator decorators (`@ArrayNotEmpty`, `@ValidateNested`). The controller then becomes `return this.orders.placeOrder(req.user.sub, dto.items)`.

**Also found at:** [`src/orders/orders.service.ts:27`](../../src/orders/orders.service.ts#L27)


### ARC-003 · Balance debit rule lives in OrdersService and bypasses the Users domain

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Architecture |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.service.ts:28`](../../src/orders/orders.service.ts#L28)–31 |
| Reported by | architecture-reviewer |

**Description**

OrdersService.placeOrder loads a User entity, mutates `user.balance` directly and persists it through the generic `UsersService.save(user)` pass-through (users.service.ts:33). The Users module therefore does not own its own balance invariant: no sufficient-funds check, no single place for the debit rule. Orders reaches into another aggregate's state. The same method also does not handle a null user from findById. It is also the reason OrdersService depends on UsersService at all, which feeds the module cycle.

**Evidence**

```ts
    const user = await this.users.findById(userId);
    const total = items.reduce((sum, i) => sum + i.price * i.quantity, 0);
    user.balance = user.balance - total;
    await this.users.save(user);
```

**Potential impact**

Any future feature that touches the balance (refunds, top-ups) will reimplement the rule, and invariants such as 'balance must not go negative' have no home. The generic save() lets any module write arbitrary User fields.

**Recommended solution**

Add an intention-revealing method on UsersService, for example `debitBalance(userId: number, amount: number, manager?: EntityManager)`, that loads the user, throws NotFoundException or a domain error for a missing user or insufficient funds, and persists the change. Call it from placeOrder (inside the transaction the backend reviewer will recommend) and remove the public generic `save(user)`.

**Also found at:** [`src/users/users.service.ts:33`](../../src/users/users.service.ts#L33)


### ARC-004 · Circular dependency between Users and Orders, hidden with forwardRef

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Architecture |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/users.service.ts:5`](../../src/users/users.service.ts#L5)–12 |
| Reported by | architecture-reviewer |

**Description**

Confirmed the three cycles reported by the import graph. At the service level, UsersService imports and injects OrdersService (users.service.ts:5, :12) only so getProfileWithOrders can call orders.listForUser (line 29), while OrdersService imports and injects UsersService (orders.service.ts:5, :12) for placeOrder. At the module level, UsersModule and OrdersModule import each other through `forwardRef` (users.module.ts:9, orders.module.ts:9). Both directions use `forwardRef` to hide the cycle, not to resolve it. The entity cycle (order.entity.ts:2 <-> user.entity.ts:2) is the normal TypeORM bidirectional relation with lazy arrow-function types and is benign on its own. The service and module cycles, however, come from a misplaced responsibility: a Users service that composes Orders data.

**Evidence**

```ts
import { OrdersService } from '../orders/orders.service';
...
    @Inject(forwardRef(() => OrdersService)) private readonly orders: OrdersService,
```

**Potential impact**

The two feature modules cannot be understood, tested or extracted on their own (users.service.spec.ts has to stub an OrdersService just to construct UsersService). The cycle relies on forwardRef ordering, so an injection that is undefined at construction time is a latent risk as the modules grow.

**Recommended solution**

Make the dependency one-way: Orders -> Users. Move getProfileWithOrders out of UsersService, either into OrdersService (for example `getUserProfileWithOrders`) or into a small composing ProfileService/controller that lives in OrdersModule. Alternatively, load it through the existing `User.orders` relation (`repo.findOne({ where: { id }, relations: { orders: true } })`). Then drop OrdersService from UsersService, and forwardRef(() => OrdersModule) from UsersModule, along with the remaining forwardRefs.

**Also found at:** [`src/orders/orders.service.ts:5`](../../src/orders/orders.service.ts#L5), [`src/orders/orders.service.ts:12`](../../src/orders/orders.service.ts#L12), [`src/users/users.module.ts:9`](../../src/users/users.module.ts#L9), [`src/orders/orders.module.ts:9`](../../src/orders/orders.module.ts#L9), [`src/users/users.service.ts:29`](../../src/users/users.service.ts#L29), [`src/orders/order.entity.ts:2`](../../src/orders/order.entity.ts#L2), [`src/users/user.entity.ts:2`](../../src/users/user.entity.ts#L2)


### SEC-009 · No brute-force protection on POST /auth/login

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/auth/auth.controller.ts:8`](../../src/auth/auth.controller.ts#L8)–11 |
| Reported by | security-reviewer |
| References | CWE-307, A07:2021 |

**Description**

The login endpoint has no rate limiting, throttling or lockout. package.json has no @nestjs/throttler or equivalent, and main.ts registers no middleware. Combined with fast MD5 hashing, online password guessing is cheap.

**Evidence**

```ts
@Post('login')
login(@Body() body: { email: string; password: string }) {
  return this.auth.login(body.email, body.password);
}
```

**Potential impact**

Attackers can run unlimited credential-stuffing or password-guessing attempts against any account.

**Recommended solution**

Add @nestjs/throttler (ThrottlerModule + ThrottlerGuard) with a strict per-IP and per-account limit on /auth/login, for example 5 attempts per minute, and consider progressive lockout.


### SEC-010 · Login tokens issued without expiry

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/auth/auth.service.ts:21`](../../src/auth/auth.service.ts#L21) |
| Reported by | security-reviewer |
| References | CWE-613, A07:2021 |

**Description**

jwt.sign is called with no `expiresIn`, so issued tokens never expire. With no revocation mechanism, a leaked token stays valid forever, as long as the signing key is unchanged.

**Evidence**

```ts
const token = jwt.sign({ sub: user.id, role: user.role }, JWT_SECRET);
```

**Potential impact**

Stolen or logged tokens give permanent account access, and role changes or deactivation are not reflected in existing tokens.

**Recommended solution**

Sign with a short lifetime and pinned algorithm: `jwt.sign(payload, secret, { expiresIn: '15m', algorithm: 'HS256' })`, and enforce `exp` in verification. Add refresh tokens if longer sessions are needed.


### PERF-002 · Unbounded full-table fetch of all orders on GET /orders

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Performance (also: API & Backend) |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.service.ts:23`](../../src/orders/orders.service.ts#L23)–25 |
| Reported by | backend-reviewer, performance-reviewer |

**Description**

listAll() calls this.orders.find() with no where clause, take/skip, or select. OrdersController.all() exposes it on GET /orders with no guard. Each request loads every row in the orders table, which grows with every order placed, and serializes it to JSON. The users search endpoint has the same problem: GET /users/search runs `SELECT * FROM "user" WHERE name ILIKE '%q%'` with no LIMIT, so an empty or one-letter q returns most of the user table.

**Evidence**

```ts
  async listAll() {
    return this.orders.find();
  }
```

**Potential impact**

Response time, memory use, and payload size grow linearly with the table. One unauthenticated request can pull the whole orders table into Node's heap. Repeated calls can cause memory pressure, event-loop stalls during JSON serialization, and DB I/O spikes.

**Recommended solution**

Paginate with a capped page size: `listAll(page = 1, limit = 50) { const take = Math.min(limit, 100); return this.orders.find({ order: { id: 'DESC' }, take, skip: (page - 1) * take }); }`. For large tables, switch to keyset pagination (`where: { id: LessThan(cursor) }`). Apply a LIMIT (and select only the needed columns) to UsersService.search too.

**Also found at:** [`src/orders/orders.controller.ts:11`](../../src/orders/orders.controller.ts#L11), [`src/users/users.service.ts:24`](../../src/users/users.service.ts#L24), [`src/orders/orders.controller.ts:9`](../../src/orders/orders.controller.ts#L9)

<sub>Validation: merged by orchestrator decision: same unbounded listAll(); pagination fixes both</sub>


### PERF-003 · Order items inserted one-by-one with sequential awaits in placeOrder

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Performance |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.service.ts:33`](../../src/orders/orders.service.ts#L33)–35 |
| Reported by | performance-reviewer |

**Description**

placeOrder() awaits this.items.save() once per item inside a for loop. TypeORM's save() also does a SELECT-before-INSERT pass per entity, so an order with K items costs about K to 2K sequential round trips, on top of the user read, the user save and the order save. This is the POST /orders write path, and the controller allows any number of items (the discount logic expects orders with more than 10 items).

**Evidence**

```ts
    for (const item of items) {
      await this.items.save({ orderId: order.id, ...item });
    }
```

**Potential impact**

Checkout latency grows linearly with basket size (for example, 50 items means 50+ serial DB round trips). Each request holds a pool connection longer, which cuts throughput under load.

**Recommended solution**

Insert all items in one statement: `await this.items.insert(items.map(i => ({ orderId: order.id, ...i })));`, or `this.items.save(array)`, which batches. When transactional correctness is fixed (backend/database own that), run this inside the same transaction/EntityManager as the balance and order writes.


### API-003 · No rate limiting on login or the search endpoint

| Field | Value |
|---|---|
| Severity | Medium |
| Category | API & Backend |
| Status | Potential |
| Confidence | High |
| Location | [`src/app.module.ts:8`](../../src/app.module.ts#L8)–22 |
| Reported by | backend-reviewer |

**Description**

No throttler is configured: @nestjs/throttler is not a dependency, AppModule has no ThrottlerModule or APP_GUARD, and main.ts adds no rate-limit middleware. POST /auth/login and GET /users/search, which runs an unanchored ILIKE '%q%' scan, accept unlimited requests. Brute-forcing credentials is a security concern and is left to the security reviewer; this finding covers the missing API-level throttling mechanism.

**Evidence**

```ts
imports: [
  TypeOrmModule.forRoot({
  ...
  }),
  AuthModule,
  UsersModule,
  OrdersModule,
],
```

**Potential impact**

Clients can flood the login and search endpoints, consuming database capacity and degrading the API for everyone.

**Recommended solution**

Add @nestjs/throttler: register `ThrottlerModule.forRoot([{ ttl: 60000, limit: 100 }])` and `{ provide: APP_GUARD, useClass: ThrottlerGuard }`, with stricter `@Throttle()` limits on `auth/login` and `users/search`.


### API-004 · No request validation: no global ValidationPipe, untyped bodies and params

| Field | Value |
|---|---|
| Severity | Medium |
| Category | API & Backend |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/main.ts:5`](../../src/main.ts#L5)–7 |
| Reported by | backend-reviewer |

**Description**

main.ts does not register a ValidationPipe, and no DTO classes exist. class-validator is a dependency but unused, and class-transformer is not installed. Bodies are typed `any` or as inline object types, which are not validated at runtime. Route params are converted with `Number(...)` instead of ParseIntPipe, so `/users/abc` or `/orders/user/abc` passes NaN to TypeORM. A login request without `email` or `password` reaches `crypto.createHash(...).update(undefined)`, which throws, so the client gets 500 instead of 400.

**Evidence**

```ts
const app = await NestFactory.create(AppModule);
app.enableCors();
await app.listen(process.env.PORT || 3000);
```

**Potential impact**

Malformed input produces 500s or undefined behavior instead of 400 responses, unknown fields pass straight through to entity saves, and the API has no enforced contract for clients.

**Recommended solution**

Add `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))` and install class-transformer. Create LoginDto (`@IsEmail()`, `@IsString() @MinLength(...)`) and CreateOrderDto, and use `@Param('id', ParseIntPipe) id: number` on the users and orders routes.

**Also found at:** [`src/orders/orders.controller.ts:21`](../../src/orders/orders.controller.ts#L21), [`src/auth/auth.controller.ts:9`](../../src/auth/auth.controller.ts#L9), [`src/users/users.controller.ts:15`](../../src/users/users.controller.ts#L15), [`src/orders/orders.controller.ts:16`](../../src/orders/orders.controller.ts#L16)


### API-005 · POST /orders debits balance with no idempotency protection

| Field | Value |
|---|---|
| Severity | Medium |
| Category | API & Backend |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.controller.ts:19`](../../src/orders/orders.controller.ts#L19)–21 |
| Reported by | backend-reviewer |

**Description**

Placing an order is a payment-like operation: it debits the user's balance immediately and marks the order 'paid'. The endpoint accepts no idempotency key and has no deduplication, so a client retry after a timeout, or a double submit, creates a second order and a second debit.

**Evidence**

```ts
@UseGuards(JwtGuard)
@Post()
async create(@Req() req: any, @Body() body: any) {
```

**Potential impact**

Network retries or repeated clicks double-charge users, and support has to reconcile the extra orders by hand.

**Recommended solution**

Accept an `Idempotency-Key` header and store it in the same transaction as the order, for example in a unique `(userId, idempotencyKey)` column on Order. On a repeat key, return the existing order instead of creating a new one.


### API-006 · GET /users/:id returns 200 for missing users and the raw User entity

| Field | Value |
|---|---|
| Severity | Medium |
| Category | API & Backend |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/users.service.ts:27`](../../src/users/users.service.ts#L27)–31 |
| Reported by | backend-reviewer |

**Description**

getProfileWithOrders spreads the result of findById into the response without a null check. For a nonexistent id, the client gets 200 with `{ orders: [] }` instead of 404. For an existing user, the whole TypeORM entity is serialized, including `passwordHash`, `role` and `balance`, because there is no response DTO and no ClassSerializerInterceptor/@Exclude. GET /users/search also returns raw `SELECT *` rows.

**Evidence**

```ts
async getProfileWithOrders(id: number) {
  const user = await this.findById(id);
  const orders = await this.orders.listForUser(id);
  return { ...user, orders };
}
```

**Potential impact**

Clients cannot detect a missing resource, and the response contract is coupled to the database schema, so internal columns such as passwordHash are exposed to callers.

**Recommended solution**

Throw `NotFoundException` when `user` is null. Map the result to a UserProfileDto (id, name, email, orders), or mark sensitive columns with `@Exclude()` and register ClassSerializerInterceptor globally. Apply the same mapping to search results.

**Also found at:** [`src/users/users.service.ts:24`](../../src/users/users.service.ts#L24)


### DB-003 · OrderItem.orderId has no foreign key to Order

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Database |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/order.entity.ts:22`](../../src/orders/order.entity.ts#L22)–28 |
| Reported by | database-reviewer |

**Description**

OrderItem stores `orderId` as a plain `@Column()` with no `@ManyToOne(() => Order)` / `@JoinColumn`, so TypeORM creates no foreign-key constraint. Items can reference orders that do not exist, and deleting an order leaves its items behind. There is also no ON DELETE behavior. By contrast, Order.userId is backed by a @ManyToOne relation.

**Evidence**

```ts
@Entity()
export class OrderItem {
  @PrimaryGeneratedColumn()
  id: number;

  @Column()
  orderId: number;
```

**Potential impact**

Order line items, which are priced financial records, can become orphaned or point to the wrong order, and referential integrity is not guaranteed at the database level. No order-deletion path exists in the files read today, so the immediate risk is limited to future code and manual operations.

**Recommended solution**

Add `@ManyToOne(() => Order, (o) => o.items, { onDelete: 'CASCADE', nullable: false }) @JoinColumn({ name: 'orderId' }) order: Order;` and keep `@Column() orderId`. Add the matching `@OneToMany` on Order and create the constraint through a migration after cleaning up any orphans.


### DB-004 · Missing indexes on order.userId and order_item.orderId

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Database |
| Status | Confirmed |
| Confidence | Medium |
| Location | [`src/orders/orders.service.ts:16`](../../src/orders/orders.service.ts#L16)–18 |
| Reported by | database-reviewer |

**Description**

Postgres does not index foreign-key or referencing columns automatically. listForUser filters `order` by `userId` and `order_item` by `orderId`, and neither entity declares an `@Index`. Both lookups need a sequential scan of their table. The query is on the hot path of GET /orders/user/:userId and GET /users/:id. This assumes the order tables grow with usage and are not tiny. The per-order loop itself (N+1) belongs to performance.

**Evidence**

```ts
    const orders = await this.orders.find({ where: { userId } });
    for (const order of orders) {
      (order as any).items = await this.items.find({ where: { orderId: order.id } });
```

**Potential impact**

Profile and order-history latency grows linearly with total order and item volume across all users, and database CPU load rises as the tables grow.

**Recommended solution**

Add `@Index()` on `Order.userId` and `OrderItem.orderId` (or `@Index(['userId', 'id'])` if results get ordered or paginated), created through a migration with `CREATE INDEX CONCURRENTLY`.

**Also found at:** [`src/orders/order.entity.ts:12`](../../src/orders/order.entity.ts#L12), [`src/orders/order.entity.ts:27`](../../src/orders/order.entity.ts#L27)


### DB-005 · User.email has no unique constraint though login treats it as unique

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Database |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/user.entity.ts:9`](../../src/users/user.entity.ts#L9)–10 |
| Reported by | database-reviewer |

**Description**

AuthService.login resolves the account with `findByEmail` (`findOne({ where: { email } })`), which assumes one row per email. The column is a plain `@Column()` with no `unique: true` and no index, so duplicates are allowed. Postgres comparison is also case-sensitive, so 'A@x.com' and 'a@x.com' count as different users.

**Evidence**

```ts
  @Column()
  email: string;
```

**Potential impact**

Duplicate accounts per email can be created. Login then picks an arbitrary matching row, which leads to failed logins or authentication against the wrong account. Each login also sequentially scans the user table.

**Recommended solution**

Add `@Index({ unique: true })` on email (ideally a unique index on `lower(email)`, or the `citext` type). Deduplicate existing rows in the migration before creating the index.

**Also found at:** [`src/users/users.service.ts:19`](../../src/users/users.service.ts#L19)


### DB-006 · No CHECK constraint keeps user.balance non-negative

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Database |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/user.entity.ts:21`](../../src/users/user.entity.ts#L21)–22 |
| Reported by | database-reviewer |

**Description**

The README says orders debit the user's balance, but nothing in the schema enforces the invariant that the balance stays at or above zero. The column has no CHECK constraint, and placeOrder subtracts the total without checking that the balance covers it, so the database accepts negative balances.

**Evidence**

```ts
  @Column('float', { default: 0 })
  balance: number;
```

**Potential impact**

Users can place orders with insufficient funds and drive their balance negative. Neither the application nor the database stops it, and corrupted balances persist.

**Recommended solution**

Add `@Check('"balance" >= 0')` on the User entity (created through a migration) as a backstop, alongside the conditional atomic debit described in the lost-update finding.


### TEST-003 · Jest config missing: no ts-jest transform, e2e config file absent

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Testing |
| Status | Confirmed |
| Confidence | Medium |
| Location | [`package.json:8`](../../package.json#L8)–9 |
| Reported by | testing-reviewer |

**Description**

package.json declares `"test": "jest"` and `"test:e2e": "jest --config ./test/jest-e2e.json"`, but test/jest-e2e.json does not exist. I attempted to read it and it is missing. ts-jest is a devDependency, but package.json has no `jest` key and there is no jest.config.js or jest.config.ts at the root, so nothing configures ts-jest as the transform. With Jest's default babel-jest and no TypeScript Babel preset, the TypeScript in users.service.spec.ts (`{} as any`) is expected to fail to parse. Assumption: no other Jest config variant (for example jest.config.mjs or .cjs) exists. I could not glob for every variant.

**Evidence**

```json
"test": "jest",
"test:e2e": "jest --config ./test/jest-e2e.json"
```

**Potential impact**

`npm run test:e2e` fails immediately on the missing config, and `npm test` probably fails to compile the TypeScript specs. Any CI gate that runs these scripts is broken or gets disabled, so even the tests that do get written won't run.

**Recommended solution**

Add Jest config to package.json (or jest.config.ts): `{"moduleFileExtensions":["js","json","ts"],"rootDir":"src","testRegex":".*\\.spec\\.ts$","transform":{"^.+\\.(t|j)s$":"ts-jest"},"testEnvironment":"node"}`, and create test/jest-e2e.json with the same transform plus `"rootDir":".","testRegex":".e2e-spec.ts$"`. This matches the standard Nest CLI scaffold.


### TEST-004 · UsersService spec asserts only instantiation; no behaviour tested

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Testing |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/users.service.spec.ts:4`](../../src/users/users.service.spec.ts#L4)–7 |
| Reported by | testing-reviewer |

**Description**

The only unit test constructs UsersService with three `{} as any` stubs and asserts toBeDefined. None of its methods is called. search (raw SQL built from user input), getProfileWithOrders (merges the user with orders and does not handle a missing user) and findByEmail (used by login) have no tests. The empty-object stubs would throw on any method call, so the test can only ever check the constructor.

**Evidence**

```ts
it('should be defined', () => {
    const service = new UsersService({} as any, {} as any, {} as any);
    expect(service).toBeDefined();
  });
```

**Potential impact**

The core user service looks tested but has effectively no coverage. Regressions in profile assembly, the null-user path and search escaping go undetected.

**Recommended solution**

Use Test.createTestingModule with getRepositoryToken(User), a DataSource mock and an OrdersService mock. Assert outcomes: getProfileWithOrders returns the user's fields plus orders, and handles an unknown id (expect a NotFoundException once that is implemented). search passes the term as a bound parameter, not interpolated (assert the query text and params); input containing a quote should not alter the SQL. Cover search further in the e2e suite against a real DB.

**Also found at:** [`src/users/users.service.ts:23`](../../src/users/users.service.ts#L23), [`src/users/users.service.ts:27`](../../src/users/users.service.ts#L27)


### TEST-005 · No e2e/integration tests: only a skipped placeholder exists

| Field | Value |
|---|---|
| Severity | Medium |
| Category | Testing |
| Status | Confirmed |
| Confidence | High |
| Location | [`test/app.e2e-spec.ts:1`](../../test/app.e2e-spec.ts#L1)–5 |
| Reported by | testing-reviewer |

**Description**

The only e2e file contains one it.skip test with a TODO and no body. None of the routed endpoints (POST /auth/login, GET /users/search, GET /users/:id, GET /orders, GET /orders/user/:userId, POST /orders) has an HTTP-level test, even though supertest and @nestjs/testing are installed. Nothing exercises the real TypeORM/Postgres integration either, including the raw SQL in UsersService.search and the multi-write order flow. The skip also means the e2e suite reports green while testing nothing.

**Evidence**

```ts
describe('AppController (e2e)', () => {
  it.skip('/ (GET)', () => {
    // TODO: write e2e tests
  });
});
```

**Potential impact**

Wiring bugs (guards, module imports, the forwardRef cycle between Users and Orders, request-body handling, error responses) and DB-level behaviour are never verified. A passing CI run gives false confidence.

**Recommended solution**

Replace the placeholder with a real suite. Bootstrap AppModule via Test.createTestingModule against a disposable Postgres (testcontainers or a CI service DB), then use supertest for the main flows: login success and failure, unauthenticated vs authenticated POST /orders, profile retrieval, and search with special characters such as a quote or percent sign. Remove it.skip, and consider a lint rule (jest/no-disabled-tests) so skipped tests cannot be committed silently.


### OPS-004 · CI runs no tests, lint or dependency audit, and only on push

| Field | Value |
|---|---|
| Severity | Medium |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`.github/workflows/ci.yml:2`](../../.github/workflows/ci.yml#L2)–12 |
| Reported by | devops-reviewer |

**Description**

The only job installs and builds. `npm test` (jest) is defined in package.json but never run, and there is no lint, type-check or `npm audit` step. The workflow triggers on `push` only, so pull requests from forks get no checks, and nothing in the repository blocks a merge on a failing pipeline.

**Evidence**

```yaml
on: [push]
...
      - run: npm install
      - run: npm run build
```

**Potential impact**

Regressions in order and balance logic, and vulnerable dependencies, reach main undetected. The pipeline gives no signal beyond 'it compiles'.

**Recommended solution**

Trigger on `push` and `pull_request`. After `npm ci`, add `npm run lint` (once ESLint is configured), `npm test -- --ci`, and `npm audit --audit-level=high`. Make the job a required status check on main.

**Also found at:** [`package.json:8`](../../package.json#L8)


### OPS-005 · actions/checkout pinned to a mutable branch (@master)

| Field | Value |
|---|---|
| Severity | Medium |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`.github/workflows/ci.yml:7`](../../.github/workflows/ci.yml#L7) |
| Reported by | devops-reviewer |

**Description**

The checkout step references the `master` branch instead of a release tag or commit SHA. Branch refs are mutable, so the code that runs in CI can change without any change to this repository. The workflow also declares no `permissions:` block, so the job receives the repository's default GITHUB_TOKEN scope.

**Evidence**

```yaml
      - uses: actions/checkout@master
```

**Potential impact**

A change pushed to that branch, whether a breaking change or a compromise, runs immediately in this pipeline with the job's token and any secrets added later.

**Recommended solution**

Pin to a full commit SHA with a version comment, e.g. `actions/checkout@<sha> # v4.x`, and do the same for actions/setup-node. Add `permissions: contents: read` at workflow level. Use Dependabot for github-actions to keep the pins current.

**Also found at:** [`.github/workflows/ci.yml:8`](../../.github/workflows/ci.yml#L8)


### OPS-006 · No lockfile, so CI and Docker use non-reproducible `npm install`

| Field | Value |
|---|---|
| Severity | Medium |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`.github/workflows/ci.yml:11`](../../.github/workflows/ci.yml#L11) |
| Reported by | devops-reviewer |

**Description**

No package-lock.json is committed (none exists at the repository root), every dependency uses a caret range, and both CI and the Dockerfile run `npm install` rather than `npm ci`. Every build resolves the newest matching versions at that moment.

**Evidence**

```yaml
      - run: npm install
```

**Potential impact**

Builds of the same commit can produce different dependency trees. A compromised or buggy minor/patch release reaches production without any diff to review.

**Recommended solution**

Run `npm install` once locally and commit package-lock.json. Switch CI and the Dockerfile to `npm ci` (use `npm ci --omit=dev` in the runtime stage), and enable `cache: npm` in actions/setup-node.

**Also found at:** [`Dockerfile:4`](../../Dockerfile#L4), [`package.json:12`](../../package.json#L12)


### OPS-007 · Unpinned node:latest base image

| Field | Value |
|---|---|
| Severity | Medium |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`Dockerfile:1`](../../Dockerfile#L1) |
| Reported by | devops-reviewer |

**Description**

The image is built FROM node:latest, which moves to each new Node major release. Builds are not reproducible, and production silently changes runtime (currently a non-LTS 'Current' line) with no review. The CI workflow tests on Node 20, so what CI verifies is not what ships.

**Evidence**

```dockerfile
FROM node:latest
```

**Potential impact**

A routine rebuild can pull a new Node major with breaking changes or native-module ABI changes and break the service in production. The full Debian-based `latest` image also carries a large CVE surface.

**Recommended solution**

Pin to an active LTS slim or alpine tag, ideally by digest, e.g. `FROM node:22-alpine@sha256:<digest>`, and use the same major in CI (`node-version: 22`).

**Also found at:** [`.github/workflows/ci.yml:10`](../../.github/workflows/ci.yml#L10)


### OPS-008 · COPY . . without a .dockerignore copies .env and host artifacts into the image

| Field | Value |
|---|---|
| Severity | Medium |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`Dockerfile:3`](../../Dockerfile#L3)–4 |
| Reported by | devops-reviewer |

**Description**

The Dockerfile copies the whole build context with `COPY . .`, and the repository has no .dockerignore. The committed .env (production DB host and password), any local node_modules or dist, and .git are therefore copied into an image layer. Running `npm install` after `COPY . .` also busts the dependency layer cache on every source change.

**Evidence**

```dockerfile
COPY . .
RUN npm install
```

**Potential impact**

Database credentials and repository history ship inside every image, and builds are slow and non-reproducible because host node_modules can overwrite or mix with container-installed modules.

**Recommended solution**

Add a .dockerignore with .env*, .git, node_modules, dist, docs, test and coverage. Copy package.json and package-lock.json first, run `npm ci`, then `COPY src ./src` and the tsconfig.

**Also found at:** [`.env:1`](../../.env#L1)


### OPS-009 · Container runs as root (no USER instruction)

| Field | Value |
|---|---|
| Severity | Medium |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`Dockerfile:8`](../../Dockerfile#L8) |
| Reported by | devops-reviewer |

**Description**

The Dockerfile has no USER instruction, so `node dist/main` runs as root (uid 0) in the official node image. Combined with the baked-in secrets and the full build toolchain in the image, any RCE in the app or its dependencies runs with root privileges inside the container.

**Evidence**

```dockerfile
CMD ["node", "dist/main"]
```

**Potential impact**

A compromise of the Node process gets root in the container, which makes container escape and tampering with the filesystem much easier.

**Recommended solution**

In the runtime stage, `COPY --chown=node:node` the app files and add `USER node` (the official node images ship a `node` user) before CMD. Also set `runAsNonRoot: true` in the deployment manifest.


### OPS-010 · Deployment env vars do not match what the code reads

| Field | Value |
|---|---|
| Severity | Medium |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/app.module.ts:11`](../../src/app.module.ts#L11)–15 |
| Reported by | devops-reviewer |

**Description**

Configuration is split three ways and does not line up. .env defines DB_PASSWORD, but AppModule never reads it and hard-codes the username, password, port and database name. Only DB_HOST and PORT come from the environment. The Dockerfile sets JWT_SECRET, but AuthService uses a module-level literal and never reads process.env. No config module or schema validates required variables at startup, so a missing DB_HOST silently falls back to localhost.

**Evidence**

```ts
      host: process.env.DB_HOST || 'localhost',
      port: 5432,
      username: 'orders',
      password: '[REDACTED]',
      database: 'orders',
```

**Potential impact**

Operators who rotate DB_PASSWORD or JWT_SECRET in the environment get no effect, and the old credentials keep working. Each environment needs a code change to point at a different database. A misconfigured deployment starts and then fails at runtime rather than failing fast.

**Recommended solution**

Add @nestjs/config with a validation schema (Joi or class-validator) that requires DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_NAME and JWT_SECRET. Use TypeOrmModule.forRootAsync with ConfigService and inject the JWT secret the same way. Document every key in .env.example.

**Also found at:** [`.env:2`](../../.env#L2), [`Dockerfile:5`](../../Dockerfile#L5), [`src/auth/auth.service.ts:6`](../../src/auth/auth.service.ts#L6)


### CQ-001 · console.log in bootstrap violates the Nest Logger convention

| Field | Value |
|---|---|
| Severity | Low |
| Category | Code Quality |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/main.ts:8`](../../src/main.ts#L8) |
| Reported by | architecture-reviewer |

**Description**

main.ts logs startup with `console.log`, although the README says to use the Nest `Logger` and never `console.log`. The message also omits useful context such as the port.

**Evidence**

```ts
  console.log('Orders API listening');
```

**Potential impact**

Startup output bypasses Nest's log formatting, levels and any custom logger, and the line does not say which port the API is bound to.

**Recommended solution**

Use `const logger = new Logger('Bootstrap');` and `logger.log(`Orders API listening on port ${port}`)`, where `port` is the resolved `process.env.PORT || 3000`.


### SEC-011 · CORS enabled for all origins and no security headers

| Field | Value |
|---|---|
| Severity | Low |
| Category | Security |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/main.ts:5`](../../src/main.ts#L5)–6 |
| Reported by | security-reviewer |
| References | CWE-942, A05:2021 |

**Description**

app.enableCors() with no options reflects `Access-Control-Allow-Origin: *` for every origin. helmet (or equivalent) is not installed or registered. Auth uses a Bearer header rather than cookies, so cross-site credentialed abuse is limited today, which is why the severity is Low.

**Evidence**

```ts
const app = await NestFactory.create(AppModule);
app.enableCors();
```

**Potential impact**

Any website can call the API from a victim's browser and read responses. If cookie auth is added later, this becomes a CSRF/data-theft vector. Missing headers weaken defence in depth.

**Recommended solution**

Configure an explicit allow-list: `app.enableCors({ origin: config.get('CORS_ORIGINS').split(','), credentials: false })`, and register `app.use(helmet())`.


### API-007 · Non-RESTful route for a user's orders, and no API versioning

| Field | Value |
|---|---|
| Severity | Low |
| Category | API & Backend |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/orders/orders.controller.ts:14`](../../src/orders/orders.controller.ts#L14)–17 |
| Reported by | backend-reviewer |

**Description**

A user's orders are served at `GET /orders/user/:userId` instead of a nested resource such as `GET /users/:id/orders`, or `GET /orders?userId=` for a filter. POST /orders returns 201 with no Location header. No versioning is configured: there is no `app.enableVersioning` or global prefix, and no `/v1` routes.

**Evidence**

```ts
@Get('user/:userId')
forUser(@Param('userId') userId: string) {
  return this.orders.listForUser(Number(userId));
}
```

**Potential impact**

The URL scheme is inconsistent, and without versioning the planned contract fixes (DTOs, pagination, error codes) will be breaking changes for existing clients.

**Recommended solution**

Call `app.setGlobalPrefix('api')` and `app.enableVersioning({ type: VersioningType.URI, defaultVersion: '1' })` in main.ts. Move the listing to `GET /users/:id/orders` or `GET /orders?userId=`, and ship the contract fixes under v1.

**Also found at:** [`src/main.ts:5`](../../src/main.ts#L5)


### DB-007 · DB connection has no SSL or pool configuration

| Field | Value |
|---|---|
| Severity | Low |
| Category | Database |
| Status | Potential |
| Confidence | Medium |
| Location | [`src/app.module.ts:9`](../../src/app.module.ts#L9)–15 |
| Reported by | database-reviewer |

**Description**

The TypeORM Postgres config sets no `ssl` option and no `extra.max` / pool settings, while .env targets a remote production host (`prod-db.internal.acme.io`). Connections are unencrypted unless the network or a proxy enforces TLS, and the pool uses the node-postgres default of 10. Hard-coded DB credentials in this block are left to the security reviewer.

**Evidence**

```ts
    TypeOrmModule.forRoot({
      type: 'postgres',
      host: process.env.DB_HOST || 'localhost',
      port: 5432,
      username: 'orders',
      password: '[REDACTED]',
      database: 'orders',
```

**Potential impact**

Database traffic, including credentials and balances, may cross the network in cleartext. The pool size is not tuned to the deployment.

**Recommended solution**

Use `TypeOrmModule.forRootAsync` with ConfigService. Set `ssl: { rejectUnauthorized: true, ca: ... }` for non-local hosts and `extra: { max: Number(process.env.DB_POOL_MAX ?? 10) }`.


### DB-008 · role and status are unconstrained free-text columns

| Field | Value |
|---|---|
| Severity | Low |
| Category | Database |
| Status | Confirmed |
| Confidence | High |
| Location | [`src/users/user.entity.ts:18`](../../src/users/user.entity.ts#L18)–19 |
| Reported by | database-reviewer |

**Description**

User.role (default 'customer') and Order.status (default 'pending', set to 'paid') are plain varchar columns with no enum type or CHECK constraint. Any string can be stored, and the role value is embedded in JWTs for authorization.

**Evidence**

```ts
  @Column({ default: 'customer' })
  role: string;
```

**Potential impact**

Typos or invalid states ('Paid', 'admin ') persist silently, which breaks status filters and role checks.

**Recommended solution**

Use `@Column({ type: 'enum', enum: UserRole, default: UserRole.Customer })` and an `OrderStatus` enum, or add CHECK constraints, through a migration.

**Also found at:** [`src/orders/order.entity.ts:18`](../../src/orders/order.entity.ts#L18)


### DB-009 · Leading-wildcard ILIKE user search cannot use an index

| Field | Value |
|---|---|
| Severity | Low |
| Category | Database |
| Status | Potential |
| Confidence | Medium |
| Location | [`src/users/users.service.ts:24`](../../src/users/users.service.ts#L24) |
| Reported by | database-reviewer |

**Description**

The user search uses `name ILIKE '%...%'`. A leading wildcard prevents use of a B-tree index, so every search is a full table scan. The SQL injection in this query and the SELECT * exposure of passwordHash belong to security and are not covered here. This assumes the user table becomes large; for small tables the cost is negligible.

**Evidence**

```ts
    return this.dataSource.query(`SELECT * FROM "user" WHERE name ILIKE '%${q}%'`);
```

**Potential impact**

Search latency and database load grow linearly with the number of users.

**Recommended solution**

Use QueryBuilder with a parameter, select only the needed columns, add a limit, and if search volume warrants it create a `pg_trgm` GIN index: `CREATE INDEX CONCURRENTLY user_name_trgm ON "user" USING gin (name gin_trgm_ops)`.


### OPS-011 · CI targets end-of-life Node 20

| Field | Value |
|---|---|
| Severity | Low |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`.github/workflows/ci.yml:10`](../../.github/workflows/ci.yml#L10) |
| Reported by | devops-reviewer |

**Description**

CI pins node-version 20. Node.js 20 reached end of life in April 2026, so it no longer gets security fixes as of this review. It also differs from the node:latest runtime used by the Dockerfile.

**Evidence**

```yaml
          node-version: 20
```

**Potential impact**

CI validates against an unsupported runtime that is not the one shipped, so version-specific failures surface only in production.

**Recommended solution**

Move CI and the Docker base image to the same active LTS major (e.g. 22 or 24), and declare it in package.json `engines` and an `.nvmrc`.

**Also found at:** [`Dockerfile:1`](../../Dockerfile#L1)


### OPS-012 · Single-stage image ships devDependencies, sources and build toolchain

| Field | Value |
|---|---|
| Severity | Low |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | High |
| Location | [`Dockerfile:1`](../../Dockerfile#L1)–8 |
| Reported by | devops-reviewer |

**Description**

The Dockerfile builds and runs in one stage. The runtime image keeps every devDependency (jest, ts-jest, typescript, supertest), the TypeScript sources, the test folder and the full Debian toolchain from the non-slim node image.

**Evidence**

```dockerfile
FROM node:latest
WORKDIR /app
COPY . .
RUN npm install
...
RUN npm run build
```

**Potential impact**

Image size and CVE surface are several times larger than needed, which slows pulls and scale-out and widens what an attacker can use after a compromise.

**Recommended solution**

Use a multi-stage build. The builder stage runs `npm ci && npm run build`. The runtime stage (node:<lts>-alpine) copies package*.json, runs `npm ci --omit=dev`, copies `dist/` from the builder, sets `ENV NODE_ENV=production`, and runs `USER node`.


### OPS-013 · No health endpoint, HEALTHCHECK or graceful shutdown hooks

| Field | Value |
|---|---|
| Severity | Low |
| Category | DevOps & Infrastructure |
| Status | Confirmed |
| Confidence | Medium |
| Location | [`src/main.ts:4`](../../src/main.ts#L4)–9 |
| Reported by | devops-reviewer |

**Description**

The Dockerfile has no HEALTHCHECK. AppModule registers only the Auth, Users and Orders modules, with no @nestjs/terminus or health controller, so orchestrators have nothing to probe for liveness or readiness, including database connectivity. main.ts does not call app.enableShutdownHooks(). With `node` running as PID 1 in exec-form CMD and no signal handlers, SIGTERM is ignored until the runtime sends SIGKILL, so in-flight requests and DB connections are cut instead of drained. Startup is reported only with a console.log line (logging style itself is architecture's concern).

**Evidence**

```ts
async function bootstrap() {
  const app = await NestFactory.create(AppModule);
  app.enableCors();
  await app.listen(process.env.PORT || 3000);
  console.log('Orders API listening');
}
```

**Potential impact**

Unhealthy instances, for example ones that lost the database, keep receiving traffic. Every deploy or scale-down waits the full kill timeout and drops requests mid-flight, which could leave order and balance writes half-done.

**Recommended solution**

Add @nestjs/terminus with a /health endpoint that includes a TypeOrmHealthIndicator ping. Call app.enableShutdownHooks() in bootstrap. Add a Dockerfile HEALTHCHECK (or k8s liveness/readiness probes) against /health. Consider `tini` or `docker run --init` as PID 1.

**Also found at:** [`Dockerfile:8`](../../Dockerfile#L8), [`src/app.module.ts:8`](../../src/app.module.ts#L8)
