# Nexus Frontend

This is the Next.js 16 operations console for Nexus.

## What It Shows

- source directory with health, grouping, tags, and crawl-method visibility
- crawler control panel for batch runs and exports
- knowledge overview cards fed by institutions, scholars, projects, events, leadership, and report APIs
- intelligence panel with report-dimension status and latest sentiment report preview

## Local Development

Prefer the repo-level runner for full-stack startup:

```bash
./nexus.sh start
```

Frontend-only development:

```bash
cd frontend
npm ci
NEXT_PUBLIC_API_BASE_URL=http://localhost:43817/api/v1 npm run dev
```

Default local URL: `http://localhost:43819`

## Validation

```bash
npm run lint
npm run build
```

## Important Files

- `src/app/page.tsx`: main dashboard composition
- `src/components/sources/SourcePanel.tsx`: source catalog and selection UX
- `src/components/dashboard/KnowledgeOverview.tsx`: knowledge graph overview cards
- `src/components/dashboard/IntelligencePanel.tsx`: report and leadership previews
- `src/lib/api.ts`: typed API access layer
- `src/types/index.ts`: shared frontend data contracts

For future dedicated institution pages, prefer the explicit backend list endpoints:

- `/api/v1/institutions/flat`
- `/api/v1/institutions/hierarchy`
