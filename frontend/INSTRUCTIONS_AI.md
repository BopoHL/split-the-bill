# AI Agent Instructions - Split the Bill Frontend

Welcome to the **Split the Bill** frontend project. To ensure consistency and maintainable architecture, please follow these guidelines strictly.

## 🛠 Project Overview

- **Framework**: Next.js with App Router.
- **State Management**: Zustand (see `src/lib/store/useStore.ts`).
- **Styling**: Tailwind CSS & Framer Motion for animations.
- **Design System**: Notebook/Handwritten aesthetic with a focus on premium feel.

## 📡 API Conventions

- **Method Preference**: Use **`POST`** for almost all state-changing operations (updates, toggles, etc.), even if they conceptually map to `PATCH` or `PUT`.
- **API Client**: Always use the central `apiClient` in `src/lib/api/client.ts`.

## 🏗 Architectural Integrity (Clean Backend)

This project follows a "Clean Backend" philosophy. The frontend should remain a pure presentation layer.

- **No Complex Logic**: Do not implement complex calculations, redistribution logic, or data-integrity checks on the frontend.
- **Backend Responsibility**: All heavy lifting (e.g., splitting sums, calculating remainders, validating transition states) must happen on the backend.

### ⚠️ Critical Agent Rule

If you encounter a task that requires:

1. Significant frontend "hacks" or complex calculations.
2. Logic that clearly belongs to the domain/business layer (backend).
3. "Manual" synchronization of states that the backend should handle atomically.

**STOP EXECUTION** and notify the user. Explain why the current approach violates clean architecture and what changes are needed on the backend or in the API design to solve the problem properly.

## 📊 Analytics

Every new feature or user action ships with its PostHog events, typed in `src/lib/analytics/events.ts` and sent with `track()`. The rules are in the root [CLAUDE.md](../CLAUDE.md#product-analytics-is-part-of-every-feature).

## 🎨 UI & UX

- Maintain the "Notebook" aesthetic: use hand-drawn icons (Lucide), specific typography, and subtle paper textures/shadows.
- Use `framer-motion` for all transitions and interactive feedback.
- Every interactive element should have a clear hover/tap state.
- **Minimal text.** People don't read in the regular app. Ordinary screens, sheets and buttons get no hint paragraphs, no «Например: …» examples and no instructions under controls — a short label at most. Make the action obvious through the control itself: icon, shape, state, motion. Explaining is for onboarding and the guided tour only.
