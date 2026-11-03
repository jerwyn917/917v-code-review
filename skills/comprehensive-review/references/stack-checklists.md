# Stack-specific review checklists

Hot spots per technology. Each agent reads the sections for the detected stack and checks only the items in its own categories. Confirm every item in the source; none of them is a finding by itself.

## Node.js (any)
- Unhandled promise rejections; `async` callbacks in `forEach`; missing `await`; sync fs/crypto in request paths.
- `process.env` read at import time without validation; secrets defaulting to literals (`process.env.JWT_SECRET || 'secret'`).
- `child_process.exec` with interpolated input; `eval`/`new Function`.
- Listeners and `setInterval` never cleared; module-level caches that grow without bound.

## NestJS
- `ValidationPipe` registered globally with `whitelist: true` (and `forbidNonWhitelisted`)? Otherwise DTO validation decorators are ignored, and missing `class-validator` decorators let any shape through.
- Guards: `@UseGuards(AuthGuard)` on controllers. Is there a global `APP_GUARD`? Look for `@Public()` decorators that bypass it.
- Ownership checks (IDOR): services that take `id` from params without comparing it to `req.user`.
- Business logic in controllers, and repositories or `DataSource` injected into controllers, are layering violations.
- Circular module imports (`forwardRef`) are an architecture smell.
- TypeORM `synchronize: true`; `query()` with template strings; missing `@Transactional`/`queryRunner` around multi-writes.
- Exception filters: consistent error shape; no stack traces in production responses.
- `enableCors()` with no options; `helmet` absent.

## Next.js
- App Router: secrets or DB clients imported into `'use client'` components; `NEXT_PUBLIC_*` env vars holding secrets.
- Route handlers (`app/**/route.ts`) and server actions (`'use server'`): authentication and authorization checks inside each action, input validation, CSRF considerations for actions.
- `dangerouslySetInnerHTML` with CMS or user content; `next/image` remote patterns set to `**`.
- `middleware.ts` matchers that leave sensitive routes unprotected.
- Data fetching: `cache: 'no-store'` everywhere, or missing `revalidate`, waterfalls of sequential `await fetch`.
- Large client components that could be server components; heavy imports without `dynamic()`.
- `useEffect` fetching that duplicates server data; missing dependency arrays; derived state stored in state.

## React / Vue (SPA)
- Keys from array index on reorderable lists; inline object/function props to memoized children.
- Context providers whose value is recreated every render; global stores with no selectors.
- Tokens in `localStorage`; `v-html` / `dangerouslySetInnerHTML`.
- Accessibility: buttons as `div`, missing labels, focus management in modals, color-only state.

## Java / Spring Boot
- `@Transactional` on private methods or on self-invoked methods, where the proxy does not apply; `@Transactional` missing on multi-repository writes; `readOnly` reads.
- JPA N+1: `@OneToMany` / `@ManyToMany` traversed in loops; `FetchType.EAGER` everywhere; missing `@EntityGraph` or `JOIN FETCH`.
- `@Query(nativeQuery=true)` or `createQuery` with string concatenation; `JdbcTemplate` with `+`.
- Security: `SecurityFilterChain` with `permitAll()` on broad matchers, `csrf().disable()` for cookie-session apps, `@CrossOrigin("*")`, method security (`@PreAuthorize`) absent on admin operations.
- Entities returned directly from controllers (over-exposure, lazy-loading exceptions); missing `@Valid` on `@RequestBody`.
- `application.properties`/`yml`: plaintext passwords, `ddl-auto=update`, `show-sql=true`, actuator endpoints exposed (`management.endpoints.web.exposure.include=*`).
- Exceptions: `catch (Exception e) { e.printStackTrace(); }`; missing `@ControllerAdvice`; returning 200 with error bodies.
- Field injection (`@Autowired` on fields) instead of constructor injection.

## Python / Django / FastAPI / Flask
- Django: `DEBUG=True`, `ALLOWED_HOSTS=['*']`, `SECRET_KEY` literal, `raw()`/`extra()`/`cursor.execute` with f-strings, `mark_safe`, `@csrf_exempt`, missing `select_related`/`prefetch_related`, migrations with `RunPython` lacking reverse.
- FastAPI: endpoints without `Depends(auth)`; Pydantic models with `extra = "allow"`; sync DB calls in `async def`; `allow_origins=["*"]` with credentials.
- Flask: `app.run(debug=True)`; `render_template_string` with input; `send_file` with request paths.
- `pickle`/`yaml.load`; `subprocess(..., shell=True)`; `requests` without timeouts; `verify=False`.

## PHP / Laravel
- Mass assignment: `$guarded = []` or `$request->all()` passed to `create`/`update`.
- `DB::raw`/`whereRaw` with interpolation; `{!! !!}` in Blade with user data.
- Missing `authorize()` / policies; routes outside `auth` middleware; `APP_DEBUG=true` in committed env.
- N+1: relationships accessed in loops without `with()`.
- Queued jobs without retries/timeouts; `env()` called outside config files.

## Go
- Goroutine leaks (no context cancellation); unbuffered channel deadlocks; `defer` in loops.
- Ignored errors (`_ =`), `panic` in request handlers; `http.Client` without timeout.
- `fmt.Sprintf` into SQL; `InsecureSkipVerify: true`; `math/rand` for tokens.
- `database/sql` rows not closed; missing `rows.Err()` check.

## Docker / Compose
- Unpinned or `:latest` base images; running as root; secrets in `ENV`/`ARG`; `COPY . .` without `.dockerignore`; no multi-stage build for compiled apps; no `HEALTHCHECK`; dev dependencies in the runtime image.
- Compose: plaintext passwords; ports bound to `0.0.0.0` for databases; `privileged: true`; volumes mounting the Docker socket.

## Terraform / IaC
- Public S3 buckets / ACLs; security groups open to `0.0.0.0/0` on admin ports; unencrypted storage/RDS; `publicly_accessible = true`; IAM `*` actions/resources; state stored locally or in an unencrypted backend; secrets in `.tfvars` committed; missing provider version pins.

## CI/CD (GitHub Actions, GitLab CI, Jenkins)
- Third-party actions pinned to branches instead of SHAs; `pull_request_target` with checkout of PR code; secrets echoed; `curl | sh`; no dependency/lockfile caching; no tests or lint gates before deploy; long-lived cloud credentials instead of OIDC.
