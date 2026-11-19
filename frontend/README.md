# StudyMate AI — Frontend Visual Foundation

An original, editorial-style landing page for an AI study assistant. This
stage is the **visual foundation only** — no backend, no database, no real
AI calls. Everything shown (progress numbers, quiz result) is either static
demo content or starts at zero, per the "new user" spec.

## Stack

- React 18 + TypeScript
- Vite
- Tailwind CSS (custom design tokens in `tailwind.config.ts`)
- Framer Motion (scroll-driven and hover animations)

## Run locally

```bash
npm install
npm run dev
```

Then open the printed local URL. `npm run build` produces a production
build in `dist/` (runs a TypeScript check first).

## Account profile

Sign in with Google or email and password to use the profile controls. Select
your avatar or greeting in the navigation to view your profile, edit your
display name, and sign out. The display name is saved to Supabase user metadata
and updates the hero greeting immediately. A Google profile image is shown
when the account provides one.

## Study history database setup

Study history requires the `study_history` table and its Row Level Security
policies. The migration is at
`supabase/migrations/001_create_study_history.sql`. To apply it:

1. Open the project's Supabase dashboard and select **SQL Editor**.
2. Create a new query, paste the complete migration file contents, and run it.
3. Confirm that `public.study_history` exists and that row-level security is
   enabled before testing history in the app.

The frontend uses the existing authenticated Supabase client and does not use
or expose a service-role key. The migration has not been applied automatically.

## Structure

```
src/
  components/    Navigation, AnimatedBackground, PipelineThread (shared)
  sections/      Hero + the five scroll-story sections
  animations/    Shared Framer Motion variants
  hooks/         useSectionProgress — scroll-linked animation driver
  data/          Pipeline stage copy, sample quiz question
```

## Design concept

The five-stage pipeline — **Notes → Understand → Remember → Practice →
Master** — is the structural spine of the page. A single vertical thread
(`PipelineThread.tsx`) runs down the left margin and fills as you scroll,
so the five sections read as one continuous transformation rather than
five separate feature blocks.

- **Notes**: a document enters, key lines highlight, then split off as
  extracted fragments.
- **Understand**: the fragments resolve into a plain-language summary and
  a concept map (nodes + connecting lines draw in on scroll).
- **Remember**: concepts become flashcards — hover lifts a card, click
  flips it (3D flip, real interaction).
- **Practice**: a flashcard becomes a working multiple-choice quiz
  question with real answer feedback.
- **Master**: the quiz result becomes a progress panel — all values start
  at zero, with an explicit empty-state message for a brand-new user.

## Accessibility & performance notes

- Respects `prefers-reduced-motion` (disables background drift + shortens
  transitions globally via `index.css`).
- Visible focus rings on all interactive elements.
- No WebGL — all motion is CSS/SVG/Framer Motion, kept light for lower-end
  hardware.
- Layout tested down to small mobile widths; the pipeline thread hides
  below the `lg` breakpoint where there isn't room for a side margin.

## Known follow-ups (intentionally not built yet)

- Real file upload / parsing for Notes
- Persisted user progress (currently all zero, static)
- AI tutor chat (the hero bubble is a static illustration)
- Full flashcard/quiz decks beyond the demo content shown per section
