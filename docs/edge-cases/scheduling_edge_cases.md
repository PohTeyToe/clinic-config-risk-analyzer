# Scheduling Configuration Edge Cases

Scheduling configuration edge cases arise from the complex interplay between provider assignments, room allocations, appointment types, billing codes, and patient check-in workflows in Ava's EMR. Clinics use a variety of scheduling models -- pod-based, room-based, provider-based, and hybrid -- and each model introduces configuration assumptions that can conflict with others. Locum physicians, walk-in patients, and QR-based self-check-in add additional variables that the scheduling system must reconcile in real time. When these variables conflict, the result can range from double-bookings and billing mismatches to duplicate patient records that create downstream charting and safety risks.

---

## Case 1: Locum Physician Inheriting Wrong Permission Set

**Affected Dimensions:** Provider Permissions, Scheduling, Billing, Feature Access

**Severity:** High

**Scenario:**
A clinic brings in a locum physician to cover for a provider on leave. The clinic administrator creates the locum's profile by duplicating the absent physician's account and changing the name and billing number. The duplicated profile inherits all of the original physician's configuration, including their custom encounter templates, billing preferences, specific module access (Ava Scribe premium tier, AutoChart settings), and panel patient assignments. The locum now has access to the original physician's patient panel, can bill under the original physician's preferences (which may include billing codes the locum is not authorized for), and has premium feature access that the locum's contract does not cover. The locum also receives the original physician's inbox items, including unsigned lab results and pending referrals.

**Why It's Hard to Catch:**
Profile duplication is a common and efficient workflow for onboarding locums because it avoids configuring every setting from scratch. The administrator may not review every inherited setting, especially if the duplication copies dozens of configuration fields. The locum may not realize they are seeing another physician's inbox items or using features beyond their contract scope. Billing under the wrong preferences may not cause immediate errors but will create reconciliation issues at month-end when the locum's billed services do not match their contracted rate or authorized codes.

**Impact:**
The locum receiving the original physician's inbox items may act on pending lab results or referrals without full clinical context, creating continuity-of-care risks. Billing under the original physician's preferences may result in claims submitted under the wrong practitioner identifier, which is a compliance violation. Access to Ava Scribe premium tier without a valid license incurs costs the clinic did not budget for. The original physician returning from leave may find that their inbox items were marked as reviewed by the locum, creating gaps in their follow-up workflow.

**Test Approach:**
Duplicate a fully configured physician profile to create a locum account. Verify that the system either (a) strips clinical-specific settings (panel assignments, inbox items, premium feature access) during duplication and requires explicit re-configuration, or (b) presents a checklist during duplication showing all inherited settings with checkboxes to include/exclude each one. Test that the risk analyzer flags newly duplicated profiles that retain another provider's panel assignments or billing number as high-risk configurations. Verify that the locum onboarding workflow includes a validation step that compares the duplicated profile against a "locum baseline" template to identify inherited settings that should be removed.

---

## Case 2: Pod Assignment Conflicts with Room-Based Scheduling

**Affected Dimensions:** Scheduling, Room Management, Provider Assignment, Patient Flow

**Severity:** Medium

**Scenario:**
A clinic uses pod-based scheduling where physicians are assigned to pods (Pod A, Pod B), and each pod has designated exam rooms. The scheduling system assigns patients to pods based on their panel physician. Separately, the clinic also uses room-based scheduling for walk-in patients, where the next available room determines the assigned provider. A walk-in patient is assigned to Room 3 (part of Pod A) because it is the next available room, but the patient's panel physician is in Pod B. The Pod B physician sees the patient on their panel list but the room assignment shows Pod A. The Pod A physician sees the room as occupied in their pod but does not see the patient on their schedule. Both physicians are uncertain who should see the patient.

**Why It's Hard to Catch:**
Pod-based and room-based scheduling are both valid configuration options, but their interaction is not explicitly defined in the configuration model. The system does not enforce that room assignments must align with pod assignments because some clinics intentionally use flexible room allocation. The conflict only surfaces in the UI as ambiguous assignment indicators -- the patient appears in two different contexts (pod panel vs room board) with conflicting provider assignments. Staff must manually resolve the conflict, and there is no configuration-level rule that prevents it.

**Impact:**
Provider confusion about patient assignments delays care. In a busy clinic, a patient caught between two pod assignments may wait significantly longer than necessary because each physician assumes the other will see the patient. The MOA at the front desk spends time manually resolving the conflict, reducing their availability for other tasks. If the conflict goes unresolved and the patient leaves without being seen, it creates both a patient satisfaction issue and a missed billing opportunity.

**Test Approach:**
Configure a clinic with both pod-based and room-based scheduling active. Create a walk-in appointment that assigns a room belonging to Pod A for a patient paneled to a Pod B physician. Verify that the scheduling system either (a) constrains walk-in room assignment to the patient's panel physician's pod, or (b) displays a clear conflict notification to front desk staff with options to reassign. Test that the risk analyzer flags clinics with both scheduling modes active and no conflict resolution rule configured. Simulate a full clinic day with mixed booked and walk-in patients to verify that scheduling conflicts are resolved consistently under load.

---

## Case 3: QR Check-In for Walk-In Creating Duplicate Records

**Affected Dimensions:** Patient Registration, Check-In, Data Integrity, Chart Duplication

**Severity:** Critical

**Scenario:**
A walk-in patient uses the clinic's QR code self-check-in kiosk. The patient scans the QR code and enters their name and date of birth. The check-in system searches for a matching patient record but the patient's name is entered with a slight variation (e.g., "Mohammed" vs the registered "Mohammad"). The fuzzy matching algorithm returns no confident match (similarity score below the configured threshold of 0.85), so the system creates a new patient record. The patient now has two records in the EMR: one with their historical chart data (under "Mohammad") and one created by the QR check-in (under "Mohammed"). The physician sees the new, empty chart and has no access to the patient's medical history, previous prescriptions, or lab results.

**Why It's Hard to Catch:**
The fuzzy matching threshold is a configuration value that balances false negatives (missed matches creating duplicates) against false positives (incorrectly merging different patients). The threshold of 0.85 is conservative to avoid the more dangerous error of merging two different patients' records. But common name variations (transliteration differences, hyphenated vs non-hyphenated, preferred name vs legal name) can produce similarity scores between 0.70 and 0.84, falling just below the threshold. The duplicate record is created silently, and the QR check-in flow does not include a "did you mean this patient?" confirmation step for near-matches because it is designed for speed and minimal friction.

**Impact:**
A duplicate patient record splits the patient's medical history across two charts. The physician treating the patient under the new, empty chart has no access to previous encounter notes, medication history, allergies, or lab results. This creates a direct patient safety risk -- the physician may prescribe a medication the patient is allergic to, or miss a critical diagnosis documented in a previous visit. Merging duplicate records after the fact is a manual, time-consuming process that requires clinical review to reconcile conflicting data between the two charts.

**Test Approach:**
Register a test patient as "Mohammad Ali" and attempt QR check-in as "Mohammed Ali." Verify that the system presents the near-match for confirmation rather than silently creating a new record. Test with various common name variations (hyphenation, transliteration, middle name inclusion/exclusion). Verify that the risk analyzer flags the fuzzy matching threshold setting and recommends a value based on the clinic's patient demographic profile. Test that duplicate records created during QR check-in are flagged for merge review in the MOA's task queue. Verify that the QR check-in flow includes a secondary identifier check (e.g., health care number, phone number) when the name match confidence is between 0.70 and 0.85.

---

## Case 4: Appointment Type Mismatch Between Booking and Billing

**Affected Dimensions:** Scheduling, Billing, Claims, Revenue

**Severity:** High

**Scenario:**
A patient books a "Mental Health Assessment" appointment (30-minute slot, billing code 08.19A in Alberta fee schedule). During the visit, the physician determines that a comprehensive assessment is needed and spends 45 minutes with the patient, which should be billed as a "Comprehensive Mental Health Assessment" (billing code 08.19C). However, the billing module pre-populates the claim with the appointment type's associated billing code (08.19A) rather than prompting the physician to select the appropriate code based on the actual service provided. The physician, accustomed to the pre-populated billing code being correct, submits the claim without changing it. The clinic bills 08.19A ($82.08) instead of 08.19C ($195.62), losing $113.54 on this encounter.

**Why It's Hard to Catch:**
Pre-populating the billing code from the appointment type is a convenience feature that is correct for the majority of encounters where the appointment type matches the service provided. The feature saves physicians time by eliminating a billing code selection step. The under-billing is invisible to the physician unless they actively compare the pre-populated code against the actual service. The financial impact is diffuse -- each individual under-billed claim is a modest amount, but across hundreds of encounters per month, the aggregate revenue loss is significant. The discrepancy only surfaces in detailed billing analytics that compare appointment duration against billed code expected duration.

**Impact:**
Systematic under-billing from appointment type/billing code mismatches represents one of the most common sources of revenue leakage in primary care clinics. Over a year, a clinic with 10 physicians each seeing 5 mental health patients per week could lose over $250,000 in under-billed claims if even 40% of encounters are billed at the wrong code. The financial impact is invisible at the individual claim level and only becomes apparent in aggregate billing analytics that most clinics do not routinely perform.

**Test Approach:**
Book a "Mental Health Assessment" appointment and extend the encounter duration beyond the appointment type's expected range. Verify that the billing module either (a) warns the physician that the appointment duration exceeds the pre-populated billing code's expected range, or (b) suggests alternative billing codes based on actual encounter duration. Test that the risk analyzer flags appointment types where the associated billing code's expected duration is significantly shorter than the average actual encounter duration for that appointment type. Verify that the billing analytics dashboard includes a "billing code optimization" report that identifies encounters where the billed code may not match the service provided based on duration, complexity, or encounter content.
