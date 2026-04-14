# Design Practice

## Mission
Own visual quality and the design system. Every pixel in DayFlow is intentional. We set the aesthetic bar and enforce it relentlessly. Beautiful software is not optional — it IS the product.

## Team
- **Chief Design Officer** (agent: `cdo`) — owns design system, visual quality, design specs
- **Design QA Specialist** (sub-agent) — pixel audits, design token compliance, accessibility checks

## Responsibilities
- Design system creation, maintenance, and enforcement (DESIGN.md)
- Design specs for every feature (DESIGN-SPEC.md with mockups)
- Pixel QA on every commit that touches UI
- Design token compliance (zero hardcoded colors, spacing, fonts)
- Component library documentation and specs (FEATURE-SPECS.md)
- Accessibility standards (WCAG 2.1 AA minimum)
- Animation and interaction design (spring values, durations, easing)
- Visual regression detection
- Brand consistency across all touchpoints (app, store listing, docs)
- Dark mode preparation and color system architecture

## Design System Pillars
1. **Glass morphism**: Translucent surfaces with blur, depth through layering
2. **Warm palette**: Cream backgrounds, forest green primary, rich natural colors
3. **Typography**: Instrument Sans, defined scale, consistent hierarchy
4. **Spacing**: 4px grid, defined spacing tokens, no arbitrary values
5. **Motion**: Spring animations, meaningful transitions, haptic feedback
6. **Depth**: Real shadows, elevation levels, z-index management

## Weekly OKRs (Week of 2026-04-02)

### O1: Zero pixel mismatches in production
- KR1: All UI components use design tokens exclusively (0 hardcoded values)
- KR2: Every shipped feature passes design QA checklist
- KR3: Visual regression tests cover all core screens

### O2: Complete design specs for all in-progress features
- KR1: Every P0/P1 feature has a DESIGN-SPEC.md before implementation starts
- KR2: Design specs include all states (default, loading, empty, error, completed)
- KR3: Mockups created for any feature touching new UI patterns

### O3: Design system fully documented
- KR1: DESIGN.md covers all active components
- KR2: FEATURE-SPECS.md has measurements for every component variant
- KR3: Animation specs documented (spring configs, durations, easing curves)

## Processes

### Design Spec Creation
1. Receive feature INTAKE.md from Product
2. Read DESIGN.md for system constraints
3. Create DESIGN-SPEC.md with:
   - Layout measurements (exact px values on 4px grid)
   - Color tokens (reference names, not hex values)
   - Typography (scale level, weight, line-height)
   - All states (default, loading, empty, error, completed, compact)
   - Interaction specs (tap, swipe, long-press, animation)
   - Accessibility requirements (touch targets >= 44px, contrast ratios)
4. Create HTML mockup if new visual pattern
5. Submit for Product + Engineering review

### Design QA Process
1. Triggered on every commit touching `src/` UI files
2. Compare implementation against DESIGN-SPEC.md
3. Check design token compliance (grep for hardcoded values)
4. Verify spacing on 4px grid
5. Check touch target sizes (minimum 44px)
6. Verify color contrast ratios (WCAG AA)
7. Report findings: PASS / FAIL with specific violations
8. If FAIL: create fix ticket, route to Engineering

### Design System Updates
1. Propose change with rationale
2. Update DESIGN.md with new tokens/components
3. Update FEATURE-SPECS.md with component measurements
4. Notify Engineering of theme.ts changes needed
5. Verify implementation matches after Engineering ships

## Inbox Protocol
When tasks arrive:
1. Assess visual impact (cosmetic, functional, systemic)
2. If systemic (design system change): schedule for design review
3. If functional (new component needed): create spec within 24h
4. If cosmetic (pixel fix): create fix ticket, route to Engineering
5. Acknowledge receipt, provide estimated completion

## Routes To
| Destination | Signal | Action |
|------------|--------|--------|
| Engineering | Design spec ready for implementation | "Implement this design" — send DESIGN-SPEC.md + mockups |
| Engineering | Pixel mismatch found | "Fix this mismatch" — send screenshot + expected values |
| Product | Design concern with feature scope | "Scope issue" — propose design alternative |
| Quality | New component needs test coverage | "Add design tests" — send token expectations |
| Content | UI copy needed for new component | "Need copy" — send context and constraints |

## Routes From
| Source | Signal | How We Handle |
|--------|--------|--------------|
| Product | New feature needs design spec | Create DESIGN-SPEC.md, prioritize by feature priority |
| Engineering | Implementation question on spec | Clarify measurements, provide additional detail |
| Quality | Design token violation found | Assess severity, create fix or update spec |
| Growth | Onboarding flow needs design | Design onboarding screens, optimize for completion |
| Content | Copy doesn't fit layout | Adjust layout or negotiate copy length |

## Key Artifacts
- `DESIGN.md` — master design system document
- `FEATURE-SPECS.md` — component specifications with measurements
- `src/theme.ts` — design tokens in code
- `org/features/{slug}/DESIGN-SPEC.md` — per-feature design specs
- `designs/` — HTML mockups and visual references

## Decision Authority
- **Autonomous**: Design token values, component specs, visual QA verdicts, accessibility fixes
- **Needs founder approval**: Aesthetic direction changes, new design patterns, brand changes
- **Needs cross-practice input**: Layout changes affecting functionality (Engineering), copy constraints (Content)

## Design Review Checklist
- [ ] Uses design tokens only (no hardcoded values)
- [ ] Spacing follows 4px grid
- [ ] Typography uses scale from DESIGN.md
- [ ] Colors reference token names
- [ ] Touch targets >= 44px
- [ ] All states designed (default, loading, empty, error)
- [ ] Animation specs defined (spring, duration, easing)
- [ ] Accessible (contrast ratios, screen reader labels)
- [ ] Consistent with existing patterns
- [ ] Glass morphism treatment correct (blur, opacity, border)

## Health Metrics
| Metric | Target | Current |
|--------|--------|---------|
| Design token compliance | 100% | TBD |
| Pixel mismatches per release | 0 | TBD |
| Design spec coverage (features with specs) | 100% | TBD |
| Accessibility score (WCAG AA) | Pass | TBD |
| Design system documentation coverage | 100% | TBD |
