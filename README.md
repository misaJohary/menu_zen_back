# menu_zen_back

## API behavior notes

### Implicit table status transitions

`POST /orders` and `PATCH /orders/{id}/payment` already move the table's
`status` for you — the frontend does **not** need to follow up with
`PATCH /tables/{id}/status`:

- **Creating an order** claims the table (→ `assigned` if the creator is a
  server/admin, → `waiting` otherwise). See
  [TABLE_AUTO_CLAIM_PLAN.md](TABLE_AUTO_CLAIM_PLAN.md).
- **Paying all orders** releases the table back to `free`. See
  Step 10 of [RESTAURANT_TABLE_STATUS_PLAN.md](RESTAURANT_TABLE_STATUS_PLAN.md).

`PATCH /tables/{id}/status` remains the canonical path for reservations,
manual overrides, and admin reassignments.
