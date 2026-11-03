# Recommendations

**Repository:** nestjs-orders-api · **Review type:** Full codebase review · **Date:** 2026-11-03

Recommendations build on the existing architecture. None of them require new libraries unless stated, and none were applied: this review is read-only.

## Strategic recommendations

- **Make authentication real, then apply it by default** — Replace the hand-written guard with @nestjs/jwt (`JwtService.verifyAsync`) configured once in AuthModule from ConfigService, register it as a global `APP_GUARD` with an `@Public()` decorator for login, and add ownership checks in the services. (SEC-002, SEC-005, SEC-007, SEC-010, ARC-001)
- **Make placeOrder a single, server-priced transaction** — Accept only `{ sku, quantity }` through a validated DTO, price items server-side, and perform the conditional debit, the order insert and a bulk item insert inside one `dataSource.transaction`, keyed by an idempotency key. Then cover it with unit and e2e tests. (SEC-003, API-002, API-005, PERF-003, DB-006, TEST-002, ARC-003)
- **Move every secret and setting into validated configuration** — Adopt @nestjs/config with a schema that requires DB_* and JWT_SECRET, use `TypeOrmModule.forRootAsync`, delete `.env` and the Dockerfile ENV, add `.gitignore`, `.dockerignore` and `.env.example`, and rotate the exposed credentials. (SEC-001, SEC-005, OPS-001, OPS-002, OPS-010)
- **Switch schema management to migrations and fix the money types** — Turn off `synchronize`, generate a baseline migration, then migrate money columns to `numeric(12,2)` or integer cents and add constraints (unique email, FK on order items, non-negative balance, indexes). (DB-001, DB-002, DB-003, DB-004, DB-005, DB-006)
- **Turn CI into a real gate** — Commit a lockfile, add @nestjs/cli, fix the Jest config, run `npm ci`, tests and `npm audit` on pull requests, and pin actions and the Node image to the same LTS. (OPS-003, OPS-004, OPS-005, OPS-006, TEST-003, OPS-007)

## Priority 1 — fix now (Critical and High)

- **SEC-001 — Hard-coded production database password in source and committed .env** (Critical, Confirmed) — [`src/app.module.ts:13`](../../src/app.module.ts#L13)  
  Rotate the database password now. Read it from the environment (for example `password: process.env.DB_PASSWORD` via @nestjs/config with a validated schema that fails at startup when it is missing), remove .env from version control, add a .gitignore, commit only a .env.example with placeholder values, and purge the secret from git history.
- **SEC-002 — JwtGuard decodes the JWT without verifying its signature** (Critical, Confirmed) — [`src/auth/jwt.guard.ts:8`](../../src/auth/jwt.guard.ts#L8)  
  Verify the token: `[REDACTED] payload = jwt.verify(token, secret, { algorithms: ['HS256'] })` in a try/catch that throws UnauthorizedException, with the secret coming from config. Better, adopt @nestjs/jwt + JwtService.verifyAsync (or @nestjs/passport's JwtStrategy) and require the 'Bearer ' prefix explicitly.
- **SEC-003 — Order prices and quantities trusted from the client (balance manipulation)** (Critical, Confirmed) — [`src/orders/orders.controller.ts:21`](../../src/orders/orders.controller.ts#L21)  
  Accept only `{ sku, quantity }` through a class-validator DTO (`@IsString() sku`, `@IsInt() @Min(1) quantity`, `@ArrayNotEmpty`, `@ValidateNested`), with a global `ValidationPipe({ whitelist: true, forbidNonWhitelisted: true })`. Look up prices server-side in OrdersService, and reject the order when `total > user.balance`.
- **SEC-004 — Unauthenticated SQL injection in GET /users/search** (Critical, Confirmed) — [`src/users/users.service.ts:23`](../../src/users/users.service.ts#L23)  
  Use a parameterized query: `this.dataSource.query('SELECT id, name FROM "user" WHERE name ILIKE $1', [`%${q}%`])`, or the repository: `this.repo.find({ where: { name: ILike(`%${q}%`) }, select: ['id', 'name'] })`. Also put the route behind authentication.
- **SEC-005 — Hard-coded JWT signing secret in AuthService** (High, Confirmed) — [`src/auth/auth.service.ts:6`](../../src/auth/auth.service.ts#L6)  
  Rotate the key and load it from configuration (for example ConfigService/JwtModule.registerAsync with `secret: config.getOrThrow('JWT_SECRET')`), with no literal fallback. Use a long random value from a secret manager.
- **SEC-006 — Passwords hashed with unsalted MD5** (High, Confirmed) — [`src/auth/auth.service.ts:12`](../../src/auth/auth.service.ts#L12)  
  Use a slow, salted password hash: bcrypt (cost >= 12) or argon2id via `argon2.hash` / `argon2.verify`. Rehash on next successful login to migrate existing users. This needs a new dependency (bcrypt or argon2), because Node's built-in alternative is crypto.scrypt with a per-user salt.
- **SEC-007 — User and order read endpoints have no authentication or ownership check** (High, Confirmed) — [`src/users/users.controller.ts:13`](../../src/users/users.controller.ts#L13)  
  Apply a verified JWT guard globally (APP_GUARD) and mark only /auth/login as @Public(). In the services, enforce ownership, for example `if (id !== req.user.sub && req.user.role !== 'admin') throw new ForbiddenException()`. Restrict GET /orders (list all) to an admin role.
- **SEC-008 — Password hashes and full user rows returned in API responses** (High, Confirmed) — [`src/users/users.service.ts:27`](../../src/users/users.service.ts#L27)  
  Return an explicit response DTO (id, name, email only where authorized). Mark passwordHash `@Column({ select: false })` and/or use class-transformer `@Exclude()` with a ClassSerializerInterceptor. Select explicit columns in search().
- **PERF-001 — N+1 query loading order items in OrdersService.listForUser** (High, Confirmed) — [`src/orders/orders.service.ts:15`](../../src/orders/orders.service.ts#L15)  
  Fetch all items in one query and group them in memory: `const orders = await this.orders.find({ where: { userId }, order: { id: 'DESC' }, take, skip }); const items = orders.length ? await this.items.find({ where: { orderId: In(orders.map(o => o.id)) } }) : []; const byOrder = new Map<number, OrderItem[]>(); items.forEach(i => (byOrder.get(i.orderId) ?? byOrder.set(i.orderId, []).get(i.orderId)!).push(i)); orders.forEach(o => (o as any).items = byOrder.get(o.id) ?? []);`. A better option is to declare an `@OneToMany(() => OrderItem, i => i.order)` relation on Order and use `find({ where: { userId }, relations: { items: true } })`. Either way, total queries drop to 2 (or 1). Also paginate this list.
- **API-001 — POST /orders returns 201 for validation errors and all failures** (High, Confirmed) — [`src/orders/orders.controller.ts:22`](../../src/orders/orders.controller.ts#L22)  
  Remove the try/catch and throw Nest HTTP exceptions instead: `BadRequestException` for an empty items list (or let a DTO with `@ArrayNotEmpty()` and a global ValidationPipe handle it), and `NotFoundException` or `ConflictException` from the service for domain errors. If a uniform error envelope is wanted, register one global ExceptionFilter in main.ts.
- **API-002 — placeOrder debits balance and writes order without a transaction** (High, Confirmed) — [`src/orders/orders.service.ts:28`](../../src/orders/orders.service.ts#L28)  
  Wrap the whole operation in `this.dataSource.transaction(async (m) => { ... })`. Inside it, load the user with `m.findOne(User, { where: { id }, lock: { mode: 'pessimistic_write' } })`, or do an atomic `UPDATE user SET balance = balance - :total WHERE id = :id AND balance >= :total`. Throw NotFoundException when the user does not exist and a ConflictException or UnprocessableEntityException when funds are insufficient. Save the order and its items through the same manager `m`.
- **DB-001 — TypeORM synchronize: true enabled unconditionally against the production DB** (High, Confirmed) — [`src/app.module.ts:9`](../../src/app.module.ts#L9)  
  Set `synchronize: false` (or `synchronize: process.env.NODE_ENV === 'development'` at most), add a TypeORM DataSource config with `migrations: ['dist/migrations/*.js']` and `migrationsRun: false`, generate an initial migration from the current schema with `typeorm migration:generate`, and run migrations as an explicit deploy step.
- **DB-002 — Monetary columns stored as float (double precision)** (High, Confirmed) — [`src/users/user.entity.ts:21`](../../src/users/user.entity.ts#L21)  
  Use `@Column('numeric', { precision: 12, scale: 2, transformer: ... })` (or store integer minor units as `bigint`, e.g. `balanceCents`). Do arithmetic with integers or a decimal library, and add a migration that converts existing values with explicit rounding.
- **TEST-001 — Authentication (AuthService.login, JwtGuard) has no tests** (High, Confirmed) — [`src/auth/jwt.guard.ts:6`](../../src/auth/jwt.guard.ts#L6)  
  Add src/auth/jwt.guard.spec.ts that builds an ExecutionContext stub and asserts: no header gives false/401, a malformed token is rejected, a token signed with the wrong secret is rejected, an expired token is rejected, and a valid token sets req.user. Add src/auth/auth.service.spec.ts covering an unknown email, a wrong password and a successful login (decode the token and assert the sub/role claims). Add an e2e case: POST /orders with a forged token returns 401.
- **TEST-002 — OrdersService.placeOrder (balance debit) has no tests** (High, Confirmed) — [`src/orders/orders.service.ts:27`](../../src/orders/orders.service.ts#L27)  
  Add src/orders/orders.service.spec.ts using Test.createTestingModule with mocked Repository<Order>, Repository<OrderItem> and UsersService, and assert outcomes rather than calls: the balance is debited by the exact total, an unknown user is rejected, insufficient balance is rejected with no writes, invalid quantity or price is rejected, and when items.save fails the debit is not persisted. Add an e2e test for POST /orders against a real Postgres (testcontainers or a test DB) that covers the discount boundary (10 vs 11 items) and two concurrent orders that together exceed the balance.
- **OPS-001 — Committed .env holds production DB host and password, and there is no .gitignore** (High, Confirmed) — [`.env:1`](../../.env#L1)  
  Delete .env from the repo and purge it from history (git filter-repo/BFG). Rotate the database password. Add a .gitignore listing .env, node_modules and dist. Commit a .env.example with placeholder values for DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_NAME, JWT_SECRET and PORT.
- **OPS-002 — JWT signing secret baked into the Docker image via ENV** (High, Confirmed) — [`Dockerfile:5`](../../Dockerfile#L5)  
  Remove the ENV line. Inject JWT_SECRET at runtime from the orchestrator's secret store (Kubernetes Secret, ECS/SSM, Docker secrets), read it via process.env / @nestjs/config in AuthService, and fail startup if it is missing. Rotate the key, because it is now in image history and git history.
- **OPS-003 — @nestjs/cli missing from devDependencies, so `nest build` fails in CI and Docker** (High, Confirmed) — [`package.json:6`](../../package.json#L6)  
  Add "@nestjs/cli": "^10.3.0" (and "@types/node") to devDependencies and commit the resulting package-lock.json. Alternatively, change the script to `tsc -p tsconfig.json`.

## Priority 2 — plan for the next iterations (Medium)

- **ARC-001 — Token issuing and checking split across classes with no shared auth module API** (Medium, Confirmed) — [`src/auth/jwt.guard.ts:7`](../../src/auth/jwt.guard.ts#L7)  
  Centralise token handling in AuthModule: register `JwtModule.registerAsync` from @nestjs/jwt (or a small TokenService) that is configured once from ConfigService. Inject JwtService into both AuthService and JwtGuard, provide and export JwtGuard from AuthModule, and have OrdersModule import AuthModule (or register the guard as APP_GUARD with a @Public() decorator).
- **ARC-002 — Order validation and bulk-discount pricing rule live in the controller** (Medium, Confirmed) — [`src/orders/orders.controller.ts:23`](../../src/orders/orders.controller.ts#L23)  
  Move the discount computation into OrdersService (or a small pricing method it owns), with named constants such as BULK_DISCOUNT_MIN_LINES = 10 and BULK_DISCOUNT_RATE = 0.1. Move the shape and emptiness checks to a CreateOrderDto with class-validator decorators (`@ArrayNotEmpty`, `@ValidateNested`). The controller then becomes `return this.orders.placeOrder(req.user.sub, dto.items)`.
- **ARC-003 — Balance debit rule lives in OrdersService and bypasses the Users domain** (Medium, Confirmed) — [`src/orders/orders.service.ts:28`](../../src/orders/orders.service.ts#L28)  
  Add an intention-revealing method on UsersService, for example `debitBalance(userId: number, amount: number, manager?: EntityManager)`, that loads the user, throws NotFoundException or a domain error for a missing user or insufficient funds, and persists the change. Call it from placeOrder (inside the transaction the backend reviewer will recommend) and remove the public generic `save(user)`.
- **ARC-004 — Circular dependency between Users and Orders, hidden with forwardRef** (Medium, Confirmed) — [`src/users/users.service.ts:5`](../../src/users/users.service.ts#L5)  
  Make the dependency one-way: Orders -> Users. Move getProfileWithOrders out of UsersService, either into OrdersService (for example `getUserProfileWithOrders`) or into a small composing ProfileService/controller that lives in OrdersModule. Alternatively, load it through the existing `User.orders` relation (`repo.findOne({ where: { id }, relations: { orders: true } })`). Then drop OrdersService from UsersService, and forwardRef(() => OrdersModule) from UsersModule, along with the remaining forwardRefs.
- **SEC-009 — No brute-force protection on POST /auth/login** (Medium, Confirmed) — [`src/auth/auth.controller.ts:8`](../../src/auth/auth.controller.ts#L8)  
  Add @nestjs/throttler (ThrottlerModule + ThrottlerGuard) with a strict per-IP and per-account limit on /auth/login, for example 5 attempts per minute, and consider progressive lockout.
- **SEC-010 — Login tokens issued without expiry** (Medium, Confirmed) — [`src/auth/auth.service.ts:21`](../../src/auth/auth.service.ts#L21)  
  Sign with a short lifetime and pinned algorithm: `jwt.sign(payload, secret, { expiresIn: '15m', algorithm: 'HS256' })`, and enforce `exp` in verification. Add refresh tokens if longer sessions are needed.
- **PERF-002 — Unbounded full-table fetch of all orders on GET /orders** (Medium, Confirmed) — [`src/orders/orders.service.ts:23`](../../src/orders/orders.service.ts#L23)  
  Paginate with a capped page size: `listAll(page = 1, limit = 50) { const take = Math.min(limit, 100); return this.orders.find({ order: { id: 'DESC' }, take, skip: (page - 1) * take }); }`. For large tables, switch to keyset pagination (`where: { id: LessThan(cursor) }`). Apply a LIMIT (and select only the needed columns) to UsersService.search too.
- **PERF-003 — Order items inserted one-by-one with sequential awaits in placeOrder** (Medium, Confirmed) — [`src/orders/orders.service.ts:33`](../../src/orders/orders.service.ts#L33)  
  Insert all items in one statement: `await this.items.insert(items.map(i => ({ orderId: order.id, ...i })));`, or `this.items.save(array)`, which batches. When transactional correctness is fixed (backend/database own that), run this inside the same transaction/EntityManager as the balance and order writes.
- **API-003 — No rate limiting on login or the search endpoint** (Medium, Potential) — [`src/app.module.ts:8`](../../src/app.module.ts#L8)  
  Add @nestjs/throttler: register `ThrottlerModule.forRoot([{ ttl: 60000, limit: 100 }])` and `{ provide: APP_GUARD, useClass: ThrottlerGuard }`, with stricter `@Throttle()` limits on `auth/login` and `users/search`.
- **API-004 — No request validation: no global ValidationPipe, untyped bodies and params** (Medium, Confirmed) — [`src/main.ts:5`](../../src/main.ts#L5)  
  Add `app.useGlobalPipes(new ValidationPipe({ whitelist: true, forbidNonWhitelisted: true, transform: true }))` and install class-transformer. Create LoginDto (`@IsEmail()`, `@IsString() @MinLength(...)`) and CreateOrderDto, and use `@Param('id', ParseIntPipe) id: number` on the users and orders routes.
- **API-005 — POST /orders debits balance with no idempotency protection** (Medium, Confirmed) — [`src/orders/orders.controller.ts:19`](../../src/orders/orders.controller.ts#L19)  
  Accept an `Idempotency-Key` header and store it in the same transaction as the order, for example in a unique `(userId, idempotencyKey)` column on Order. On a repeat key, return the existing order instead of creating a new one.
- **API-006 — GET /users/:id returns 200 for missing users and the raw User entity** (Medium, Confirmed) — [`src/users/users.service.ts:27`](../../src/users/users.service.ts#L27)  
  Throw `NotFoundException` when `user` is null. Map the result to a UserProfileDto (id, name, email, orders), or mark sensitive columns with `@Exclude()` and register ClassSerializerInterceptor globally. Apply the same mapping to search results.
- **DB-003 — OrderItem.orderId has no foreign key to Order** (Medium, Confirmed) — [`src/orders/order.entity.ts:22`](../../src/orders/order.entity.ts#L22)  
  Add `@ManyToOne(() => Order, (o) => o.items, { onDelete: 'CASCADE', nullable: false }) @JoinColumn({ name: 'orderId' }) order: Order;` and keep `@Column() orderId`. Add the matching `@OneToMany` on Order and create the constraint through a migration after cleaning up any orphans.
- **DB-004 — Missing indexes on order.userId and order_item.orderId** (Medium, Confirmed) — [`src/orders/orders.service.ts:16`](../../src/orders/orders.service.ts#L16)  
  Add `@Index()` on `Order.userId` and `OrderItem.orderId` (or `@Index(['userId', 'id'])` if results get ordered or paginated), created through a migration with `CREATE INDEX CONCURRENTLY`.
- **DB-005 — User.email has no unique constraint though login treats it as unique** (Medium, Confirmed) — [`src/users/user.entity.ts:9`](../../src/users/user.entity.ts#L9)  
  Add `@Index({ unique: true })` on email (ideally a unique index on `lower(email)`, or the `citext` type). Deduplicate existing rows in the migration before creating the index.
- **DB-006 — No CHECK constraint keeps user.balance non-negative** (Medium, Confirmed) — [`src/users/user.entity.ts:21`](../../src/users/user.entity.ts#L21)  
  Add `@Check('"balance" >= 0')` on the User entity (created through a migration) as a backstop, alongside the conditional atomic debit described in the lost-update finding.
- **TEST-003 — Jest config missing: no ts-jest transform, e2e config file absent** (Medium, Confirmed) — [`package.json:8`](../../package.json#L8)  
  Add Jest config to package.json (or jest.config.ts): `{"moduleFileExtensions":["js","json","ts"],"rootDir":"src","testRegex":".*\\.spec\\.ts$","transform":{"^.+\\.(t|j)s$":"ts-jest"},"testEnvironment":"node"}`, and create test/jest-e2e.json with the same transform plus `"rootDir":".","testRegex":".e2e-spec.ts$"`. This matches the standard Nest CLI scaffold.
- **TEST-004 — UsersService spec asserts only instantiation; no behaviour tested** (Medium, Confirmed) — [`src/users/users.service.spec.ts:4`](../../src/users/users.service.spec.ts#L4)  
  Use Test.createTestingModule with getRepositoryToken(User), a DataSource mock and an OrdersService mock. Assert outcomes: getProfileWithOrders returns the user's fields plus orders, and handles an unknown id (expect a NotFoundException once that is implemented). search passes the term as a bound parameter, not interpolated (assert the query text and params); input containing a quote should not alter the SQL. Cover search further in the e2e suite against a real DB.
- **TEST-005 — No e2e/integration tests: only a skipped placeholder exists** (Medium, Confirmed) — [`test/app.e2e-spec.ts:1`](../../test/app.e2e-spec.ts#L1)  
  Replace the placeholder with a real suite. Bootstrap AppModule via Test.createTestingModule against a disposable Postgres (testcontainers or a CI service DB), then use supertest for the main flows: login success and failure, unauthenticated vs authenticated POST /orders, profile retrieval, and search with special characters such as a quote or percent sign. Remove it.skip, and consider a lint rule (jest/no-disabled-tests) so skipped tests cannot be committed silently.
- **OPS-004 — CI runs no tests, lint or dependency audit, and only on push** (Medium, Confirmed) — [`.github/workflows/ci.yml:2`](../../.github/workflows/ci.yml#L2)  
  Trigger on `push` and `pull_request`. After `npm ci`, add `npm run lint` (once ESLint is configured), `npm test -- --ci`, and `npm audit --audit-level=high`. Make the job a required status check on main.
- **OPS-005 — actions/checkout pinned to a mutable branch (@master)** (Medium, Confirmed) — [`.github/workflows/ci.yml:7`](../../.github/workflows/ci.yml#L7)  
  Pin to a full commit SHA with a version comment, e.g. `actions/checkout@<sha> # v4.x`, and do the same for actions/setup-node. Add `permissions: contents: read` at workflow level. Use Dependabot for github-actions to keep the pins current.
- **OPS-006 — No lockfile, so CI and Docker use non-reproducible `npm install`** (Medium, Confirmed) — [`.github/workflows/ci.yml:11`](../../.github/workflows/ci.yml#L11)  
  Run `npm install` once locally and commit package-lock.json. Switch CI and the Dockerfile to `npm ci` (use `npm ci --omit=dev` in the runtime stage), and enable `cache: npm` in actions/setup-node.
- **OPS-007 — Unpinned node:latest base image** (Medium, Confirmed) — [`Dockerfile:1`](../../Dockerfile#L1)  
  Pin to an active LTS slim or alpine tag, ideally by digest, e.g. `FROM node:22-alpine@sha256:<digest>`, and use the same major in CI (`node-version: 22`).
- **OPS-008 — COPY . . without a .dockerignore copies .env and host artifacts into the image** (Medium, Confirmed) — [`Dockerfile:3`](../../Dockerfile#L3)  
  Add a .dockerignore with .env*, .git, node_modules, dist, docs, test and coverage. Copy package.json and package-lock.json first, run `npm ci`, then `COPY src ./src` and the tsconfig.
- **OPS-009 — Container runs as root (no USER instruction)** (Medium, Confirmed) — [`Dockerfile:8`](../../Dockerfile#L8)  
  In the runtime stage, `COPY --chown=node:node` the app files and add `USER node` (the official node images ship a `node` user) before CMD. Also set `runAsNonRoot: true` in the deployment manifest.
- **OPS-010 — Deployment env vars do not match what the code reads** (Medium, Confirmed) — [`src/app.module.ts:11`](../../src/app.module.ts#L11)  
  Add @nestjs/config with a validation schema (Joi or class-validator) that requires DB_HOST, DB_PORT, DB_USERNAME, DB_PASSWORD, DB_NAME and JWT_SECRET. Use TypeOrmModule.forRootAsync with ConfigService and inject the JWT secret the same way. Document every key in .env.example.

## Priority 3 — backlog and best practice (Low and Informational)

- **CQ-001 — console.log in bootstrap violates the Nest Logger convention** (Low, Confirmed) — [`src/main.ts:8`](../../src/main.ts#L8)  
  Use `const logger = new Logger('Bootstrap');` and `logger.log(`Orders API listening on port ${port}`)`, where `port` is the resolved `process.env.PORT || 3000`.
- **SEC-011 — CORS enabled for all origins and no security headers** (Low, Confirmed) — [`src/main.ts:5`](../../src/main.ts#L5)  
  Configure an explicit allow-list: `app.enableCors({ origin: config.get('CORS_ORIGINS').split(','), credentials: false })`, and register `app.use(helmet())`.
- **API-007 — Non-RESTful route for a user's orders, and no API versioning** (Low, Confirmed) — [`src/orders/orders.controller.ts:14`](../../src/orders/orders.controller.ts#L14)  
  Call `app.setGlobalPrefix('api')` and `app.enableVersioning({ type: VersioningType.URI, defaultVersion: '1' })` in main.ts. Move the listing to `GET /users/:id/orders` or `GET /orders?userId=`, and ship the contract fixes under v1.
- **DB-007 — DB connection has no SSL or pool configuration** (Low, Potential) — [`src/app.module.ts:9`](../../src/app.module.ts#L9)  
  Use `TypeOrmModule.forRootAsync` with ConfigService. Set `ssl: { rejectUnauthorized: true, ca: ... }` for non-local hosts and `extra: { max: Number(process.env.DB_POOL_MAX ?? 10) }`.
- **DB-008 — role and status are unconstrained free-text columns** (Low, Confirmed) — [`src/users/user.entity.ts:18`](../../src/users/user.entity.ts#L18)  
  Use `@Column({ type: 'enum', enum: UserRole, default: UserRole.Customer })` and an `OrderStatus` enum, or add CHECK constraints, through a migration.
- **DB-009 — Leading-wildcard ILIKE user search cannot use an index** (Low, Potential) — [`src/users/users.service.ts:24`](../../src/users/users.service.ts#L24)  
  Use QueryBuilder with a parameter, select only the needed columns, add a limit, and if search volume warrants it create a `pg_trgm` GIN index: `CREATE INDEX CONCURRENTLY user_name_trgm ON "user" USING gin (name gin_trgm_ops)`.
- **OPS-011 — CI targets end-of-life Node 20** (Low, Confirmed) — [`.github/workflows/ci.yml:10`](../../.github/workflows/ci.yml#L10)  
  Move CI and the Docker base image to the same active LTS major (e.g. 22 or 24), and declare it in package.json `engines` and an `.nvmrc`.
- **OPS-012 — Single-stage image ships devDependencies, sources and build toolchain** (Low, Confirmed) — [`Dockerfile:1`](../../Dockerfile#L1)  
  Use a multi-stage build. The builder stage runs `npm ci && npm run build`. The runtime stage (node:<lts>-alpine) copies package*.json, runs `npm ci --omit=dev`, copies `dist/` from the builder, sets `ENV NODE_ENV=production`, and runs `USER node`.
- **OPS-013 — No health endpoint, HEALTHCHECK or graceful shutdown hooks** (Low, Confirmed) — [`src/main.ts:4`](../../src/main.ts#L4)  
  Add @nestjs/terminus with a /health endpoint that includes a TypeOrmHealthIndicator ping. Call app.enableShutdownHooks() in bootstrap. Add a Dockerfile HEALTHCHECK (or k8s liveness/readiness probes) against /health. Consider `tini` or `docker run --init` as PID 1.

## What is already done well

- Clear module boundaries: each feature folder has its own module, controller, service and entity
- UsersController and AuthController are thin and follow the README's layering convention
- Constructor injection is used consistently, with no field injection
- Login returns one generic error for unknown email and wrong password, so it does not enable user enumeration
- Repository lookups outside UsersService.search use parameterized TypeORM where clauses
