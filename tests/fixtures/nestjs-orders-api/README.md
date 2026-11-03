# Orders API

NestJS service that manages users and their orders. Orders debit the user's balance.

## Conventions
- Business logic lives in services, controllers only map HTTP to service calls.
- Use the Nest `Logger`, never `console.log`.
