# Goofish Insight UI Constitution v2

Status: Active baseline
Date: 2026-04-26
Scope: `apps/dashboard-react` and all future dashboard UI PRs

This constitution supersedes the earlier dashboard UI migration notes. When this document conflicts with older UI specs or implementation details, this document wins and code must move toward it.

## 0. Meta Rules

- M1: The visual reference is Bloomberg Terminal plus Linear plus Notion Calendar. PR screenshots must not feel cheap beside them.
- M2: Every page starts with a pixel-level Figma or hand wireframe before implementation.
- M3: Finish one page to 100% before starting the next page.
- M4: Production UI must never show debug strings, raw JSON, internal enum leakage, or strings like `template:xxx|model_name=xxx`.
- M5: If constitution and code disagree, change code.

## 1. Color

- C1: Legal colors per theme are limited to 13 roles: 4 surface, 4 ink, 1 brand, 2 direction, 1 hairline, 1 focus ring.
- C2: No radar teal, neon, fluorescent, pink-purple, or pure black `#000`. Dark background may not be deeper than `#0E0E0C`.
- C3: The only accent is `#0066FF` in Light and `#3B8AFF` in Dark, for links, selected states, primary CTAs, and focus rings only.
- C4: Up/down colors are for numeric values only. They must not color buttons, tags, or generic icons.
- C5: Surface, ink, hairline, and focus tokens must map to the constitution palette.
- C6: No raw hex, rgb, hsl, or oklch values outside theme token files. UI code must use CSS variables.
- C7: A component may use at most five colors.
- C8: No gradient backgrounds except chart area alpha fills.
- C9: No decorative solid color blocks larger than 200 by 200px.
- C10: Hover may only nudge brightness; no semantic color swaps.
- C11: Selected state is a 2px accent left border plus `surface-2`; no full-color inverse blocks.
- C12: Error and warning colors appear only for real errors, not permanent decoration.

## 2. Typography

- T1: Only two font stacks are allowed: `--font-sans` and `--font-mono`.
- T2: All numbers use mono plus tabular numerals.
- T3: Type scale has only display, h1, body, caption, and mono.
- T4: Chinese text weight is limited to 400, 500, or 600.
- T5: Line heights are explicit and never `normal` or `unset`.
- T6: h1/display tightening is a constitution target; code changes must also obey the active frontend toolchain rule in the current execution environment.
- T7: Body copy max width is 72 characters.
- T8: Truncated one-line text must have `title` or tooltip recovery.
- T9: Do not mix Chinese and English inside one label.
- T10: Titles do not end with punctuation.
- T11: Numeric columns align right; text columns align left.
- T12: Prices use `¥3,450`, not `3450` or `3450元`.
- T13: Thousands separators are mandatory.
- T14: Percentages use one decimal place.
- T15: Lists show relative time; detail views show localized absolute timestamps.
- T16: Status words are `running`, `stopped`, `degraded`, and `idle`.
- T17: Emoji are forbidden as UI elements. Status uses shape tokens such as `● ○ ◆ ▲ ▾`.
- T18: English headings use sentence case unless the term is a proper noun.
- T19: SKU fingerprints use mono.
- T20: Internal keys must not appear in production UI.

## 3. Spacing And Grid

- S1: Spacing scale is only 2, 4, 8, 12, 16, and 24.
- S2: Outer page padding is 24; section gaps are at most 24; component inner padding is at most 16.
- S3: No visible blank area greater than 32px.
- S4: Layout uses a 12-column grid, 24px gutter, and max width 1440.
- S5: Main content minimum width is 960 before sidebar collapse.
- S6: List row heights are only 32, 40, and 56.
- S7: Cards use 16 outer margin and 16 inner padding.
- S8: Table cells use 8 by 12 padding.
- S9: Icon and text gap is 6px.
- S10: Button heights are only 28, 32, or 36.
- S11: Input height is 32.
- S12: No negative margin hacks or vertical centering via `margin: auto` outside flex/grid.

## 4. Border, Radius, Shadow

- B1: Borders are 1px.
- B2: Border color is `--hair` or its mapped hairline token.
- B3: Radius values are only 0, 4, 6, and 10.
- B4: No box shadow except floating layers.
- B5: Hairlines beat shadows.
- B6: No inset shadow.
- B7: No blur filters except Dialog/Sheet overlay blur up to 4px.
- B8: Separators are 1px hairlines or 16px gaps.

## 5. Motion

- A1: Durations are only 120ms, 200ms, and 320ms.
- A2: No `transition: all`.
- A3: No page or component entry animations except spatial Sheet/Dialog/Drawer motion.
- A4: No hover scale or movement.
- A5: No looping animation except loading spinner and one live status point.
- A6: No route transition animation.
- A7: At most two concurrent animations per viewport.
- A8: Easing uses only `--ease-standard` and `--ease-emphasized`.

## 6. Density

- D1: `/today` first viewport shows at least 10 opportunities.
- D2: `/ops/runtime` first viewport shows at least 11 links.
- D3: Page blank area is at most 25%.
- D4: List row height is 40 or 56, never 72+.
- D5: KPI rows are horizontal; KPI cannot occupy a full-row card alone.
- D6: No one-line-one-field layout; at least three fields share a row or collapse into drilldown.
- D7: Top navigation is one 56px row.
- D8: Global nav, sidebar, and footer mount once.
- D9: Title bars are 48px.
- D10: KPI number is display size; label is caption size.

## 7. Tables And Lists

- L1: Table header is required and sticky.
- L2: Column widths use explicit grid templates.
- L3: Numeric columns right align, text columns left align, status columns center align.
- L4: Rows use either zebra striping or 1px hairline separation.
- L5: Row hover only changes background to `surface-2`.
- L6: Whole row is clickable.
- L7: Actions are hidden until row hover or focus.
- L8: Price columns are mono, tabular, right aligned, with `¥` and thousands separators.
- L9: Discount columns include `▾ -17.4%` or `▴ +3.2%` and use up/down tokens.
- L10: Inline `PriceGauge` is required; text-only P15/P35/P50 summaries are not enough.
- L11: score and risk use badges, not bare numbers.
- L12: Sample size `n=xx` includes a tier badge S/A/B/C/D.
- L13: Listing titles are single-line truncate with tooltip recovery.
- L14: Empty states include a CTA.

## 8. Navigation And Keyboard

- N1: Global nav is TopBar 56px plus Sidebar 232px.
- N2: TopBar contains only logo, command search, category switch, notifications, theme toggle, and user.
- N3: Sidebar supports at least four levels: category, product line, model, SKU fingerprint.
- N4: Collapsed sidebar is 56px wide and icon-only.
- N5: Command bar can jump routes, search SKU, search opportunities, and trigger actions.
- N6: Lists support J/K, Enter, and Esc.
- N7: Route jumps use G plus key: G O, G M, G W, G C, G R.
- N8: Detail opens in a right Sheet, preserving list context.
- N9: Breadcrumbs are at most three levels.
- N10: Pages provide their own back affordance and do not depend on browser back.

## 9. Component Whitelist

- W1: UI primitives are limited to badge, button, card, checkbox, dialog, dropdown-menu, input, radio-group, select, sheet, skeleton, sonner, switch, table, tabs, and tooltip.
- W2: Business composites are limited to AppFrame, PageHero, KpiTile, OpportunityRow, PriceGauge, and AnalyticsCard.
- W3: Features must not create bespoke card, row, or KPI DOM where a business composite exists.
- W4: No new UI libraries.
- W5: Icons come from `lucide-react` only.
- W6: Icon sizes are 14, 16, or 20, except empty-state illustrations.

## 10. Accessibility

- Y1: Contrast must meet WCAG AA.
- Y2: Every interactive element has `:focus-visible` with a 2px accent outline and 2px offset.
- Y3: Decisions and signals use color plus shape.
- Y4: Icon-only controls need accessible labels.
- Y5: Critical data changes use `aria-live="polite"`.
- Y6: Tab order is logical and never uses `tabindex` greater than 0.
- Y7: Command, Escape, J/K, and G+key paths are keyboard reachable.
- Y8: Lighthouse accessibility must be at least 92.

## 11. Engineering Gates

- G1: Style checks forbid raw color values outside token files.
- G2: Single CSS file max is 15KB.
- G3: Total handwritten dashboard CSS max is 40KB.
- G4: UI pages need Storybook stories for Light and Dark.
- G5: Chromatic visual regression must pass once available.
- G6: Playwright axe must pass in Light and Dark once available.
- G7: New components require `design-system:check` and broad migrations require `design-system:audit`.
- G8: PRs include Light and Dark screenshots.
- G9: UI work must not grow `cli.py`, `pricing.py`, or `specs.py`.
- G10: Business UI code must not contain debug strings such as `template:xxx`.
- G11: Inline styles cannot set color, background, or border-color.
- G12: Lighthouse performance must be at least 85.

## 12. PR Checklist

Use the repository pull request template. Missing checklist items block merge.

## 13. Execution Order

1. Freeze non-UI PRs during the redesign window.
2. Finish `/today` first against L1-L14.
3. Compare Figma against Bloomberg, Linear, and Notion Calendar before merge.
4. Copy `/today` layout discipline to other pages instead of inventing new patterns.
5. Require the checklist for every UI PR.
