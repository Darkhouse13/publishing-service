---
name: frontend-worker
description: Builds Next.js 14+ frontend dashboard with neo-brutalist design. Handles project initialization, UI components, pages, SWR hooks, and API integration. All work must stay within frontend/ directory.
---

# Frontend Worker

NOTE: Startup and cleanup are handled by `worker-base`. This skill defines the WORK PROCEDURE.

## When to Use This Skill

Features involving:
- Next.js 14 App Router pages and layouts
- React components (UI, layout, page-specific)
- Tailwind CSS styling matching design tokens
- SWR data fetching hooks
- TypeScript types and API client
- Mock data fixtures

## Required Skills

- `agent-browser` — for manual verification of rendered pages and design compliance

## Work Procedure

### 1. Project Setup (Milestone 1 features)
- Run `cd frontend && npm install` to install dependencies
- Create `next.config.js` with API rewrites (`/api/:path*` → backend URL)
- Create `tailwind.config.ts` with exact design tokens (colors, shadows, no border-radius)
- Create `postcss.config.js`, `tsconfig.json` with strict mode
- Verify `npm run dev` starts on port 3000 without errors

### 2. Implementation Order
- Foundation features first (project init, globals.css, layout, lib files)
- Design system components (Milestone 2) — all 13 UI primitives before pages
- Pages (Milestones 3-5) — build pages only after foundational components exist
- Never use shadcn/ui or other component libraries — custom-built only

### 3. TDD Approach
- Write the component/page first with mock data
- Verify visually with agent-browser
- Then integrate with SWR hooks and real API paths
- All mock data in `src/lib/mock-data.ts`

### 4. Design Token Compliance (CRITICAL)
- ZERO border-radius everywhere — no `rounded-*` utility
- Colors: base=#000000, panel=#f2f1eb, accent=#ffcc00, muted=#666666, error=#ff4444
- Borders: `border-[3px] border-base` (3px solid black)
- Shadows: `shadow-solid-sm` (4px), `shadow-solid-md` (8px), `shadow-solid-lg` (12px)
- Typography: `font-black` (900) headings, `font-bold` (700) body, `uppercase` ALL labels
- Interactive: card hover `hover:-translate-y-1 hover:shadow-solid-lg`, button hover `hover:translate-x-[2px] hover:translate-y-[2px] hover:shadow-[2px_2px_0px_0px_rgba(0,0,0,1)]`

### 5. Component Construction
- Layout components first (`src/components/layout/`)
- UI primitives (`src/components/ui/`) — Button, Card, Badge, Input, etc.
- Page-specific components (`src/components/{area}/`)
- Mark client components with `'use client'` explicitly

### 6. API Integration
- API client in `src/lib/api.ts` calls `/api/v1/...` (proxied through Next.js rewrites)
- SWR hooks in `src/hooks/` with `refreshInterval` for polling
- Use SWR `fallback` for mock data during development
- No React Query — SWR only

### 7. Manual Verification (agent-browser)
After each feature:
- Start dev server: `cd frontend && npm run dev`
- Open browser at the page being built
- Verify design tokens applied correctly (DevTools: no border-radius, correct colors)
- Verify interactive states work (hover effects, animations)
- Verify uppercase labels on all text
- Check for any console errors

### 8. Automated Verification
Before marking feature complete:
- `cd frontend && npm run build` — must complete without errors
- `cd frontend && npm run typecheck` — no TypeScript errors
- `cd frontend && npm run lint` — no lint errors

### 9. Scope Enforcement
- NEVER modify any file outside `frontend/`
- If blocked, return to orchestrator
- Do not suggest backend changes

## Example Handoff

```json
{
  "salientSummary": "Implemented StatCard, TabBar, and LiveDot UI components with neo-brutalist styling. All 13 design system components now complete. Verified hover effects, animations, and zero border-radius in browser.",
  "whatWasImplemented": "Created src/components/ui/StatCard.tsx (large number display, shadow-solid-md card), src/components/ui/TabBar.tsx (horizontal tabs, active bg-accent), src/components/ui/LiveDot.tsx (blinking square, sharp-blink animation). All components use exact design tokens: colors, 3px borders, zero border-radius, uppercase labels.",
  "whatWasLeftUndone": "",
  "verification": {
    "commandsRun": [
      { "command": "cd frontend && npm run build", "exitCode": 0, "observation": "Build completed without errors" },
      { "command": "cd frontend && npm run typecheck", "exitCode": 0, "observation": "No TypeScript errors" }
    ],
    "interactiveChecks": [
      { "action": "Visit /dashboard, inspect StatCard in DevTools", "observed": "Zero border-radius, 3px border, shadow-solid-md, hover lift works" },
      { "action": "Screenshot LiveDot on /runs", "observed": "Yellow dot blinks at 1.5s intervals in stepped fashion" },
      { "action": "Verify TabBar on /connections/[id]", "observed": "5 tabs uppercase, active tab highlighted with #ffcc00" }
    ]
  },
  "tests": { "added": [] },
  "discoveredIssues": []
}
```

## When to Return to Orchestrator

- Feature blocked by missing preconditions (another feature not yet complete)
- Ambiguous requirement or design specification
- Backend API mismatch discovered (document in frontend/README.md as known issue)
- Cannot complete work within scope constraint (frontend/ only)
- Found visual/design issue that requires design system clarification
