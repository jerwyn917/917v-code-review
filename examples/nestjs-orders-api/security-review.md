# Security Review

**Repository:** nestjs-orders-api · **Review type:** Full codebase review · **Date:** 2026-11-03

## Summary

Authentication is a hand-written `JwtGuard` that only *decodes* tokens (SEC-002), applied to a single route (POST /orders). Every read endpoint is public, with no ownership checks (SEC-007), and returns full entities including password hashes (SEC-008), which are unsalted MD5 (SEC-006). The only raw SQL in the codebase is injectable and reachable anonymously (SEC-004). Order totals come from client-supplied prices, so a negative price credits the balance (SEC-003). Secrets: the database password is in `app.module.ts` and `.env` (SEC-001, OPS-001) and the JWT signing key is in `auth.service.ts` and the Dockerfile (SEC-005, OPS-002). Rotate all of them; moving them is not enough.

| Severity | Count |
|---|---:|
| Critical | 4 |
| High | 4 |
| Medium | 2 |
| Low | 1 |
| Informational | 0 |
| **Total** | **11** |

## OWASP Top 10 (2021) coverage

| ID | Category | Findings | Notes |
|---|---|---:|---|
| A01 | Broken Access Control | SEC-007, SEC-008 | No guards or ownership checks on read endpoints; full entities exposed |
| A02 | Cryptographic Failures | SEC-005, SEC-006 | Unsalted MD5 password hashing; hard-coded signing key |
| A03 | Injection | SEC-004 | Raw SQL template string in UsersService.search |
| A04 | Insecure Design | SEC-003 | Client-controlled prices in the money path |
| A05 | Security Misconfiguration | OPS-001, OPS-002, SEC-011 | Secrets in .env and image ENV; permissive CORS; no helmet |
| A06 | Vulnerable and Outdated Components | 0 | Not assessed online (no network authorization); no lockfile committed (OPS-006) |
| A07 | Identification and Authentication Failures | SEC-001, SEC-002, SEC-009, SEC-010 | Signature never verified; tokens never expire; no login throttling |
| A08 | Software and Data Integrity Failures | 0 | No deserialization or unsigned-webhook surface found |
| A09 | Security Logging and Monitoring Failures | 0 | Failures in POST /orders are swallowed with no logging (API-001) |
| A10 | Server-Side Request Forgery | 0 | No outbound HTTP calls found |

## Security findings

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


## Security-relevant findings from other categories

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


## Areas checked with no issues found

- UsersService.findById/findByEmail use TypeORM repository `where` objects (parameterized), so there is no injection there (src/users/users.service.ts:15-21) _(security-reviewer)_
- OrdersService queries use repository find/save with parameterized where clauses, so no raw SQL (src/orders/orders.service.ts) _(security-reviewer)_
- Login returns the same generic 'Invalid credentials' message for unknown email and wrong password, so no user enumeration through the login response (src/auth/auth.service.ts:19) _(security-reviewer)_
- No child_process, eval, filesystem, redirect or outbound HTTP sinks found in the source files read (no SSRF or command-injection surface) _(security-reviewer)_
- No passwords or tokens written to logs: the only log statement is a static string in main.ts:8 _(security-reviewer)_

> Findings marked **Potential** are risks that need confirmation in their deployment context; they are not confirmed vulnerabilities. Secret values are redacted in this report.
