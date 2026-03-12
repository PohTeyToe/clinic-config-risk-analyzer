# Template and Stencil Divergence

Template and stencil divergence occurs when the reusable clinical components in Ava's EMR -- encounter stencils, letter templates, macro expansions, and PDF form mappings -- fall out of sync with the underlying data schema or field definitions they reference. Ava's template system is powerful because it allows clinics to customize encounter workflows, generate patient letters, and produce standardized forms. But this flexibility creates a maintenance burden: when fields are renamed, data sources are deprecated, or schemas evolve, templates that reference the old structure do not automatically update. The result is silent failures where templates produce incomplete documents, reference nonexistent fields, or pull stale data without any visible error.

---

## Case 1: Custom Stencils Referencing Renamed Fields After Update

**Affected Dimensions:** Encounter Stencils, Schema Migration, Clinical Documentation

**Severity:** High

**Scenario:**
A clinic has built 15 custom encounter stencils for different visit types (diabetes follow-up, prenatal check, mental health assessment). Each stencil references specific data fields by internal field name (e.g., `patient.medications.active_list`, `patient.vitals.bp_systolic`). During a platform update, Ava renames several fields for consistency: `patient.medications.active_list` becomes `patient.medications.current`, and `patient.vitals.bp_systolic` becomes `patient.vitals.blood_pressure.systolic`. The custom stencils still reference the old field names. When a physician opens the diabetes follow-up stencil, the medications section and blood pressure fields appear blank because the field references resolve to null.

**Why It's Hard to Catch:**
The stencil renderer treats null field values as "no data entered" rather than "field not found," because empty fields are a normal state for partially completed encounters. There is no distinction in the UI between "this field exists but has no value" and "this field reference is broken." The physician may assume the patient has no active medications and proceed with the encounter, creating a patient safety risk. Platform updates include migration scripts for the database schema but not for custom stencil field references, because custom stencils are clinic-owned content.

**Impact:**
A physician seeing a blank medications section may prescribe a drug that interacts with the patient's existing medications. A blank blood pressure field may prompt unnecessary diagnostic workup or missed hypertension management. Across 15 custom stencils used by multiple physicians, the impact is systemic -- every encounter using a broken stencil produces an incomplete record. Fixing all stencils requires identifying every broken reference, mapping old field names to new ones, and updating each stencil individually.

**Test Approach:**
Create a custom stencil referencing specific field names. Run a simulated schema migration that renames those fields. Open the stencil and verify that broken field references produce a visible warning (e.g., yellow highlight with "field reference not found" tooltip) rather than silent null values. Test that the risk analyzer scans all custom stencils after a schema migration and produces a report of broken field references with suggested replacements. Verify that the platform update process includes a pre-migration stencil compatibility check that warns administrators about affected stencils before the migration runs.

---

## Case 2: Macro Expansion Producing Invalid Field References

**Affected Dimensions:** Macros, Clinical Documentation, Data Integrity

**Severity:** Medium

**Scenario:**
A physician creates a documentation macro called `.diabetesreview` that expands to a structured template including `{current_medications}`, `{last_a1c}`, `{last_a1c_date}`, and `{active_referrals}`. The macro was created six months ago when these placeholder tokens mapped to valid field paths. Since then, the lab results data model was restructured to separate point-of-care tests from lab-ordered tests, and `{last_a1c}` now resolves to the lab-ordered A1C only, while point-of-care A1C results are under a different path. The physician performs a point-of-care A1C test, types `.diabetesreview`, and the expanded note shows the last lab-ordered A1C from three months ago instead of the point-of-care result from today.

**Why It's Hard to Catch:**
The macro expansion succeeds -- it does not produce an error because `{last_a1c}` still resolves to a valid value (the older lab-ordered result). The problem is that the value is stale, not missing. The physician may or may not notice that the A1C value displayed is from three months ago rather than from the test performed minutes ago. The discrepancy is subtle and depends on the physician remembering the exact value they just tested. If the values are similar (e.g., 7.1 lab vs 7.3 point-of-care), the mismatch may never be caught.

**Impact:**
A stale A1C value in the clinical note may lead to inappropriate diabetes management decisions. If the lab-ordered A1C is 7.1 but the point-of-care result is 8.5, the physician may not intensify treatment because the macro-populated note shows an apparently adequate A1C. The discrepancy is embedded in the permanent medical record and may mislead other providers reviewing the chart. Over time, uncontrolled diabetes progresses silently, and the documentation trail suggests adequate monitoring.

**Test Approach:**
Create a test patient with both a lab-ordered A1C and a point-of-care A1C with different values and dates. Expand the `.diabetesreview` macro and verify which A1C value is displayed. The expected behavior is that the macro resolves to the most recent A1C regardless of source, or displays both with source labels. Test that macro field tokens are validated against the current data model during a "macro health check" that can be run after platform updates. Verify that the risk analyzer identifies macros referencing field tokens that have been affected by data model changes and generates a remediation report for each affected physician's macro library.

---

## Case 3: Letter Stencil Pulling from Deprecated Data Source

**Affected Dimensions:** Letter Templates, Data Sources, Patient Communication

**Severity:** Medium

**Scenario:**
Ava's letter template system allows clinics to generate patient letters (referral letters, results notification letters, specialist correspondence) using data pulled from the patient chart. A referral letter template includes a section that pulls the patient's medication list from a data source called `pharmacy_profile_v1`, which was the original medication data endpoint. Ava has since migrated to `pharmacy_profile_v2`, which includes PrescribeIT-sourced data, Pharmanet/Netcare medication history, and patient-reported medications in a unified view. The old `pharmacy_profile_v1` endpoint is still active but only returns EMR-entered medications, missing externally sourced data. The referral letter is generated with an incomplete medication list.

**Why It's Hard to Catch:**
The deprecated data source still functions and returns valid data -- it is not broken, just incomplete. The letter template generates successfully, and the medication list section is populated (not empty), so there is no visible error. The referring physician may not compare the letter's medication list against the full chart view. The specialist receiving the referral letter has no way to know the list is incomplete. The data source deprecation was communicated via release notes, but existing templates were not automatically migrated because the migration could change clinical documents in ways the clinic did not explicitly approve.

**Impact:**
An incomplete medication list in a referral letter can lead the specialist to prescribe medications that interact with the patient's existing regimen. The specialist has no reason to doubt the completeness of the list because it was generated by an EMR system. If the patient experiences an adverse event, the referring physician may face questions about why the referral letter omitted medications that were visible in the chart. The root cause -- a deprecated data source identifier in a template -- is far removed from the clinical outcome, making post-incident investigation difficult.

**Test Approach:**
Create a test patient with medications from three sources: EMR-entered, PrescribeIT-received, and Netcare-sourced. Generate a referral letter using a template that references `pharmacy_profile_v1`. Verify that the letter only contains EMR-entered medications (confirming the bug). Update the template to reference `pharmacy_profile_v2` and verify all three sources appear. Test that the risk analyzer flags templates referencing deprecated data source identifiers and suggests the current replacement. Confirm that deprecated data source endpoints return a warning header that the template engine can intercept and display to the user.

---

## Case 4: PDF Form Field Mapping Broken by Schema Change

**Affected Dimensions:** PDF Generation, Form Mapping, External Submissions

**Severity:** High

**Scenario:**
Alberta Health Services requires specific PDF forms for certain authorization requests (e.g., Special Authorization for medications, AISH medical reports). Ava's EMR maps chart data fields to PDF form fields so that clinicians can auto-populate these forms from the patient chart. The PDF form field mapping is stored as a configuration file that maps EMR field paths (e.g., `patient.demographics.health_care_number`) to PDF form field names (e.g., `PHN_Field_1`). A platform update restructures patient demographics to separate provincial health numbers from federal identifiers, changing `patient.demographics.health_care_number` to `patient.demographics.provincial_ids.ahcip_number` for Alberta. The PDF mapping still references the old path, and the generated PDF has an empty health care number field.

**Why It's Hard to Catch:**
PDF form auto-population is tested infrequently because it is used for specific administrative workflows, not daily clinical encounters. The generated PDF opens and looks correct at first glance -- all the static text and labels are present -- but the health care number field is blank. A clinic staff member may manually fill in the field without reporting the auto-population failure, masking the bug. The issue only becomes systematic when multiple forms are submitted with missing health care numbers and AHS returns them for correction.

**Impact:**
AHS forms submitted with missing health care numbers are returned for correction, delaying authorization decisions by days or weeks. For time-sensitive authorizations (e.g., Special Authorization for cancer medications), the delay has direct patient care implications. If the auto-population failure is widespread across all PDF form mappings that reference the restructured demographics fields, multiple form types are affected simultaneously, creating a batch failure that overwhelms the clinic's administrative staff.

**Test Approach:**
Run a PDF form generation for all configured form mappings after a schema migration. Verify that every mapped field resolves to a non-null value for a test patient with complete demographics. Flag any field mapping where the source path does not exist in the current schema. Test that the risk analyzer includes PDF form field mappings in its schema compatibility check and reports broken mappings with the specific form name and field for easy remediation. Verify that the schema migration process includes a backward compatibility layer that maps old field paths to new ones for a configurable transition period.
