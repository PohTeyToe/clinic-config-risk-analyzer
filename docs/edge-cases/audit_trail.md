# Audit Trail and Data Integrity

Audit trail and data integrity edge cases involve scenarios where Ava's logging, versioning, and data interpretation mechanisms produce gaps, contradictions, or misleading records. EMR audit trails are a regulatory requirement -- they must accurately record who accessed what data, when, and what changes were made. These edge cases are particularly dangerous because they undermine the trust model that clinics, regulators, and patients rely on. A gap in the audit log can mean that a privacy breach goes undetected. A schema change that reinterprets historical data can mean that a clinician reviewing a patient's history sees information that was never actually recorded in that form. These issues are subtle, often latent, and typically only surface during compliance audits or legal proceedings.

---

## Case 1: Feature Flag Flip Gap in Audit Log

**Affected Dimensions:** Audit Trail, Feature Flags, Compliance, Accountability

**Severity:** High

**Scenario:**
Ava's feature flag system allows administrators to enable or disable features in real time. When a feature flag is toggled, the change is logged in the feature flag management system (LaunchDarkly or equivalent). However, the EMR's clinical audit trail -- the log that records user actions within the EMR -- does not capture feature flag changes because the flag management system is external to the EMR's audit infrastructure. A clinic administrator disables the Ava Scribe feature flag at 2:00 PM and re-enables it at 2:15 PM (perhaps to test a reported issue). During that 15-minute window, physicians cannot use Ava Scribe and must document encounters manually. The clinical audit trail shows no entries for that 15-minute gap (because no Ava Scribe actions occurred), but it does not record why the gap exists. If a compliance audit asks "why were there no AI-assisted documentation entries between 2:00 and 2:15 PM?", the answer requires cross-referencing the feature flag system's logs, which the compliance auditor may not have access to.

**Why It's Hard to Catch:**
The absence of audit log entries is inherently invisible -- you cannot detect missing data by looking at existing data. The feature flag change is logged in a different system with different access controls, different retention policies, and a different timestamp format. Correlating the two logs requires knowledge that the gap was caused by a feature flag change, which is a circular problem. Routine compliance audits check for the presence and completeness of audit entries, not for the absence of expected entries during specific time windows. The 15-minute gap is small enough to be dismissed as normal variation in documentation timing.

**Impact:**
During a compliance audit or legal proceeding, the inability to explain a gap in the audit trail can create an inference of tampering or negligence. If a patient alleges that their chart was accessed during the 15-minute gap and the clinic cannot prove otherwise, the clinic bears the burden of demonstrating compliance. The separation between the feature flag log and the clinical audit trail means that a complete audit requires access to multiple systems with different authentication, which may not be feasible for an external auditor or a court-ordered records review.

**Test Approach:**
Toggle a clinical feature flag and verify that the EMR's audit trail records the flag change as a system event, including the flag name, old value, new value, timestamp, and the administrator who made the change. Test that the risk analyzer can cross-reference feature flag change logs with clinical audit trail gaps and flag unexplained gaps that correlate with feature flag toggles. Verify that the audit trail includes a "system events" category that captures infrastructure-level changes alongside clinical actions. Test that the unified audit view presents feature flag changes inline with clinical events so that auditors can understand the full context without switching between systems.

---

## Case 2: Historical Data Viewed Under New Schema Interpretation

**Affected Dimensions:** Data Schema, Historical Records, Clinical Interpretation, Patient Safety

**Severity:** Critical

**Scenario:**
Two years ago, Ava's EMR stored blood pressure as a single text field: "120/80". The schema was updated to split blood pressure into separate numeric fields: `systolic: 120, diastolic: 80`. A migration script parsed historical text entries and populated the new fields. For entries like "120/80", the migration works correctly. But for entries like "120/80 (lying), 135/85 (standing)" (positional blood pressure readings), the migration extracted only the first reading (120/80), losing the standing reading. A physician reviewing the patient's historical vitals in the new UI sees only the lying blood pressure values and does not realize that standing readings were also recorded. For a patient being evaluated for orthostatic hypotension, the missing standing readings could lead to a missed diagnosis.

**Why It's Hard to Catch:**
The migration script was tested against common blood pressure entry formats and handled the majority correctly. Positional readings, multi-reading entries, and free-text annotations (e.g., "120/80 after medication") are edge cases that represent a small percentage of historical entries. The migrated data passes validation (systolic and diastolic are valid numbers within expected ranges), so there is no technical error flag. The lost data is not deleted -- the original text field may still exist in an archived column -- but the clinical UI only displays the new structured fields. The physician has no indication that additional data existed in the original entry.

**Impact:**
Missing standing blood pressure readings for a patient with symptoms of orthostatic hypotension (dizziness on standing, falls) means the physician reviewing the historical data cannot see the evidence that was previously documented. They may order new tests that duplicate work already done, or they may miss the diagnosis entirely because the historical trend is incomplete. The data loss is permanent in the structured schema -- the original text entries may be in an archive table, but physicians do not routinely check archive tables during clinical encounters.

**Test Approach:**
Create test patient records with various historical blood pressure entry formats: standard ("120/80"), positional ("120/80 lying, 135/85 standing"), annotated ("120/80 post-exercise"), and multi-reading ("120/80, 125/82, 118/78"). Run the migration script and verify that all readings are preserved in the new schema, with multi-value entries stored as arrays or linked records rather than single values. Test that the clinical UI displays a "view original entry" link for migrated data, allowing physicians to see the raw historical text. Verify that the risk analyzer flags schema migrations that reduce data cardinality (multi-value to single-value) as high-risk. Test that the migration includes a pre-run analysis that identifies entries matching edge-case patterns and reports them for manual review before migration execution.

---

## Case 3: Permission Change Not Reflected in Active Sessions

**Affected Dimensions:** RBAC, Session Management, Audit Trail, Security

**Severity:** High

**Scenario:**
A clinic discovers that an MOA has been accessing patient charts outside their assigned panel (a privacy concern). The administrator immediately revokes the MOA's chart access permissions. However, the MOA currently has an active session with a patient chart open. The permission revocation updates the authorization database, but the MOA's active session token was issued before the revocation and carries the pre-revocation permissions as cached claims. The MOA continues to access the open chart and can open additional charts for another 2 hours until their session token expires and they must re-authenticate. The audit trail shows chart access events after the permission revocation timestamp, creating a confusing record where a user without chart access permissions appears to be accessing charts.

**Why It's Hard to Catch:**
Session-based authentication with token caching is standard practice for performance reasons -- checking the authorization database on every API call would add unacceptable latency to clinical workflows. The trade-off is a window of vulnerability between permission revocation and session token expiration. Most permission changes (role adjustments, scope modifications) are routine and the delay is acceptable. But emergency revocations (responding to a privacy incident) require immediate effect, and the system does not distinguish between routine and emergency permission changes. The audit trail records the access events but does not flag that they occurred after a permission revocation.

**Impact:**
The 2-hour window between permission revocation and session expiration allows the MOA to continue accessing charts, potentially exfiltrating data or viewing additional unauthorized records. The audit trail shows continued access after the revocation, which during a privacy investigation creates the impression that the revocation was ineffective. The clinic's privacy officer must explain why chart access continued after the revocation was processed, which undermines the clinic's ability to demonstrate that it took prompt corrective action. Provincial privacy commissioners may view the continued access as a failure of the clinic's access control system, extending the scope of the investigation.

**Test Approach:**
Create an active session with chart access permissions. Revoke chart access permissions in a separate admin session. Attempt to access additional charts from the original session. Verify that either (a) the permission revocation triggers immediate session token invalidation, forcing re-authentication, or (b) the API layer checks a revocation list on each request for critical permissions (chart access, prescription authority). Test that the audit trail annotates post-revocation access events with a flag indicating they occurred after the permission change. Verify the risk analyzer flags clinics where session token lifetime exceeds a configurable maximum (e.g., 4 hours) as a security risk.

---

## Case 4: Deleted Template Still Referenced in Historical Notes

**Affected Dimensions:** Templates, Historical Records, Data Integrity, Clinical Review

**Severity:** Medium

**Scenario:**
A clinic used a custom encounter template called "COVID-19 Screening v1" during the pandemic. The template included specific fields for symptom tracking, exposure history, and testing results. After the pandemic, the administrator deletes the template to reduce clutter in the template picker. Historical encounters that were documented using this template still reference the template ID in their metadata. When a physician opens a historical chart note from 2021, the system attempts to render the note using the referenced template. The template no longer exists, so the rendering engine falls back to a generic plain-text display that shows the raw field values without the structured layout, labels, or conditional sections that the original template provided. The historical note is technically readable but loses its clinical context and structure.

**Why It's Hard to Catch:**
Template deletion is a soft delete in the database (the template is marked as inactive), but the rendering engine only loads active templates. The fallback to plain-text rendering is a design choice that prevents errors but degrades the user experience. The raw field values include internal field names (e.g., `covid_exposure_14d: true`) rather than display labels (e.g., "Exposure in last 14 days: Yes"), making the historical note difficult to interpret. The issue only surfaces when someone reviews a historical note that used the deleted template, which may be months or years after deletion. By then, the connection between the rendering issue and the template deletion is not obvious.

**Impact:**
Historical notes rendered in plain text with internal field names are difficult for physicians to interpret, especially during time-sensitive clinical situations (e.g., reviewing a patient's COVID screening history during a new respiratory illness). The loss of structured layout means that conditional sections (e.g., "if positive, show isolation instructions") are displayed as raw boolean values without context. For medico-legal purposes, historical notes must be presentable in their original form -- a plain-text rendering of internal field names may be challenged in court as an incomplete or inaccurate representation of the original clinical documentation.

**Test Approach:**
Create encounters using a custom template. Delete (soft-delete) the template. Open a historical encounter that references the deleted template. Verify that the rendering engine loads inactive templates in read-only mode for historical rendering, preserving the original layout and labels. Test that template deletion warns the administrator how many historical encounters reference the template and offers an "archive" option (hidden from picker but available for rendering) instead of deletion. Verify that the risk analyzer flags template deletions that affect more than a configurable threshold of historical encounters. Test that archived templates are included in the template version history and can be restored by administrators if needed.
