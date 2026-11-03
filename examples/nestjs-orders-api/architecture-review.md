# Architecture Review

**Repository:** nestjs-orders-api · **Review type:** Full codebase review · **Date:** 2026-11-03

## Architecture overview

Three feature modules (`auth`, `users`, `orders`) follow Nest conventions, each with its own module, controller and service, plus TypeORM entities. Requests flow controller → service → TypeORM repository. `AuthModule` depends one-way on `UsersModule`. `UsersModule` and `OrdersModule` depend on each other through `forwardRef` (ARC-004) because `UsersService.getProfileWithOrders` composes order data. Business rules leak into `OrdersController` (discount and validation, ARC-002), and the balance debit is implemented in `OrdersService` against another module's entity (ARC-003). Token issuing and verification are split between `AuthService` and a free-standing `JwtGuard` that shares no configuration (ARC-001).

## Structure

| Area | Detected |
|---|---|
| Languages | TypeScript (16 files) |
| Runtimes | Node.js |
| Frameworks | NestJS ^10.3.0 |
| Databases / ORM | TypeORM, PostgreSQL (manifest only) |
| Testing | Jest, Supertest (2 test files) |
| Infrastructure | Environment files, Docker |
| CI/CD | GitHub Actions |
| Package managers | npm |
| Shape | single project |

## Dependency analysis

`scripts/import-graph.py` found 27 internal import edges and three cycles:

- `src/orders/orders.service.ts` ↔ `src/users/users.service.ts`: a real design cycle (ARC-004)
- `src/orders/orders.module.ts` ↔ `src/users/users.module.ts`: the module-level mirror of the same cycle, papered over with `forwardRef` (ARC-004)
- `src/orders/order.entity.ts` ↔ `src/users/user.entity.ts`: the standard TypeORM bidirectional relation with lazy types, which is benign

Removing `getProfileWithOrders` from `UsersService` makes the dependency one-way (Orders → Users) and removes both `forwardRef`s.

## Architecture findings

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


## Code quality findings

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


## Areas checked with no issues found

- UsersController and AuthController are thin: each handler maps HTTP input to a single service call, consistent with the README convention (src/users/users.controller.ts:8-16, src/auth/auth.controller.ts:8-11) _(architecture-reviewer)_
- Constructor-based dependency injection is used consistently across services and controllers; no field injection or manual instantiation in production code _(architecture-reviewer)_
- Folder structure matches Nest module boundaries (auth/, users/, orders/, each with its own module, service and controller) _(architecture-reviewer)_
- AuthModule -> UsersModule dependency is one-way and acyclic (src/auth/auth.module.ts:7) _(architecture-reviewer)_
- The entity-level Order <-> User import cycle is the standard TypeORM bidirectional relation using lazy arrow-function types and is not itself a defect (src/orders/order.entity.ts:9, src/users/user.entity.ts:24) _(architecture-reviewer)_
- No console.log found in the other source files read; the only occurrence is src/main.ts:8 _(architecture-reviewer)_
