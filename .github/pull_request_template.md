## UI Constitution

For dashboard UI changes, complete this checklist against `docs/39-goofish-insight-ui-constitution-v2-20260426.md`.

- [ ] Compared with Bloomberg / Linear / Notion Calendar references without feeling cheap
- [ ] Light and Dark screenshots attached
- [ ] No raw hex / rgb / hsl / oklch outside theme token files
- [ ] All numbers use mono + tabular nums
- [ ] Theme color roles stay within the constitution palette
- [ ] First viewport shows at least 10 core opportunity rows where applicable
- [ ] List row height is 56px or less
- [ ] No emoji, debug strings, or mixed Chinese-English labels in production UI
- [ ] Actions are hidden until row hover or focus
- [ ] Prices include `¥`, thousands separators, and discount direction marks
- [ ] Inline `PriceGauge` exists where price bands are shown
- [ ] score / risk are badge-like, not bare numbers
- [ ] No visible blank gap greater than 32px
- [ ] Top navigation is a single 56px row without duplicate shells
- [ ] Command, J/K, Esc, and G+key keyboard paths work
- [ ] Detail opens in a Sheet instead of losing list context
- [ ] No box-shadow outside floating layers
- [ ] No `transition: all`
- [ ] Accessibility and performance targets remain green or have explicit follow-up owners
- [ ] UI work did not grow `cli.py`, `pricing.py`, or `specs.py`

## Verification

- [ ] `npm run design-system:check -w @goofish/dashboard-react`
- [ ] `npm run design-system:audit -w @goofish/dashboard-react` for broad UI changes
- [ ] `npm run verify-baseline` before declaring the change complete
