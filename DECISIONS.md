# Design Decisions

## Why This Exists

I built this tool to think through the problem of rolling out features across 300+ clinics that each have different configurations, integrations, and regulatory requirements. In a multi-tenant EMR system, a single feature change can interact with province-specific billing codes, custom note templates, optional modules, and role permission sets in ways that are hard to reason about manually. This tool models those interactions -- it takes a feature change specification, checks it against a set of clinic configuration profiles, identifies conflicts, and generates a phased rollout plan that puts lower-risk clinics first.

## Key Assumptions

1. **Province determines integration availability** - I assumed Netcare is AB-only, Pharmanet is BC-only, and Connect Care is AB-only. This might be wrong if clinics near provincial borders have special data-sharing arrangements or if there are pilot programs expanding integrations across provinces.

2. **Billing types are strictly province-constrained** - I assumed AB Health billing is only available for AB clinics and BC MSP is only for BC clinics. In reality, cross-provincial billing might exist for patients who travel between provinces or for telehealth visits that cross provincial lines.

3. **Custom templates are the biggest breakage risk** - I weighted template breakage heavily in the risk scoring. If Ava already has a template migration system that auto-updates stencils when field names change, this assumption overstates the risk. On the other hand, if clinics have built complex custom macros on top of those templates, the risk might be even higher than I modeled.

4. **Module dependencies are binary** - The tool assumes a module is either fully enabled or fully disabled. In practice, modules might have partial activation states, beta flags, or per-provider enablement that creates a middle ground the model doesn't capture.

5. **Risk score formula captures the right tradeoffs** - The weighting (breaking = 10, behavioral = 3, cosmetic = 1) is an educated guess. Real prioritization would need historical incident data showing which conflict types actually generate support tickets and which ones clinics absorb without issues.

6. **15 clinic profiles cover meaningful variation** - I tried to span the configuration space across provinces, clinic types, module combinations, and integration sets. But 300+ real clinics probably have combinations I didn't anticipate. The edge case encyclopedia in `docs/edge-cases/` is my attempt to capture scenarios that the profiles alone might miss.

## What I'd Do Differently With Codebase Access

- Pull actual clinic configurations from the database instead of hand-crafting YAML profiles. The real configuration space is almost certainly weirder than what I imagined.
- Mine support tickets to weight the risk formula based on real incident frequency and severity, rather than guessing at the multipliers.
- Integrate with the CI/CD pipeline to run conflict detection automatically on every feature branch, so the team catches rollout risks before they merge.
- Use actual template schemas to detect field-level breakage with precision, rather than relying on string-matching against template names.
- Add a feedback loop where rollout outcomes (did a cohort actually hit issues?) update future risk predictions.

## What I'd Want to Learn From the Team

1. How does the team currently decide rollout order when shipping a major feature? Is it manual judgment, a formula, geography-based, or something else entirely?
2. What's the actual distribution of custom templates across clinics? Are most clinics running close to default configurations, or is heavy customization the norm?
3. How are province-specific features gated today? Feature flags, separate codepaths, configuration-driven logic, or a mix?
4. What does the support ticket pattern look like after a major release? Which clinic types or configurations tend to generate the most issues?
5. How does the QA team select which clinic configurations to test against before a release? Is there a representative set, or is it more ad-hoc?

## Where I'm Least Confident

- **The interaction between Ava Scribe's confidential toggle and Ava Connect's auto-release.** I modeled this as a potential conflict (confidential notes shouldn't auto-release to the patient portal), but the real system might already handle this gracefully with its own safeguards.
- **Ontario expansion assumptions.** I had less data to work with for ON-specific workflows and integrations. The ON clinic profiles are probably the weakest part of the configuration set, and I may have underrepresented the integration requirements or regulatory nuances.
- **Role permission granularity.** I simplified permissions to flat lists of strings, but the real system likely has a more nuanced access control model with inheritance, overrides, or context-dependent permissions that would change how permission conflicts manifest.
- **Scheduling complexity.** Pod-based scheduling, locum sessions, and room views probably interact with billing, permissions, and patient flow in ways I haven't fully modeled. These seem like areas where configuration edge cases would be especially dense.
