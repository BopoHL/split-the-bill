# Split the Bill — rules for agents

Frontend conventions live in [frontend/INSTRUCTIONS_AI.md](frontend/INSTRUCTIONS_AI.md); read it before touching `frontend/`.

## Product analytics is part of every feature

A feature is not done until what people do with it reaches PostHog. Every new
screen, flow or user action — and every change to an existing one — ships with
its events in the same branch, covered by tests like the rest of the code.

- **Mini App** (`frontend/`): add the event and its typed props to
  `src/lib/analytics/events.ts`, send it with `track()` from
  `@/lib/analytics`. The compiler rejects an event without its props.
- **Server and bot** (`backend/`): what only the server sees — a payment, the
  bot's chat, a scheduled job acting for someone — goes through
  `capture()` in `app/services/product_events.py`, with a `ProductEvent` and
  a `Surface`. Tests read what would have been sent from the `product_events`
  fixture.
- **One name per action across surfaces.** Use the same event name for the same
  thing wherever it happens (`bill_created` from the app and the bot) and tell
  them apart by properties (`source`, `surface`), so one funnel counts both.
- **Naming:** `object_action`, snake_case, the action in the past tense or as a
  state reached (`bill_closed`, `paywall_opened`, `receipt_scan_result`).
- **Send it once the server agreed**, not when the button was pressed: when an
  action goes to the server, track it after the request succeeds, so a failed
  request is not counted as done. A funnel whose
  steps can fail gets a result event with the outcome (`ok`, `status`, `reason`).
- **Say which bill:** bill-scoped events carry `bill_id`. Nothing else that
  identifies a person or their money — no names, card details, amounts typed
  in, tokens or invite codes.
- **Funnels first.** For a flow with steps (creating, inviting, paying, buying
  Pro) track the entry, each step and the outcome, so drop-off shows between
  them.
- Events fired during the guided tour carry `in_tour` on their own; nothing to
  do for it.
