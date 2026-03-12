# Configuration Mutation Mid-Session

Configuration mutation mid-session refers to scenarios where an administrator or system process changes a configuration value while clinicians are actively using the EMR. These edge cases are particularly insidious because the clinician's session was initialized with one set of rules, but the underlying configuration has shifted. Ava's EMR caches certain configuration values at session start and reads others in real time, creating a split-brain situation where some parts of the UI reflect the old configuration and others reflect the new one. The risk is highest when the mutation affects clinical workflows -- billing, prescriptions, or feature access -- because the clinician may complete an action that was valid at session start but is now invalid under the new configuration.

---

## Case 1: Admin Changes Settings While Physician Has Chart Open

**Affected Dimensions:** Clinical Workflow, Session State, Data Integrity

**Severity:** High

**Scenario:**
A physician opens a patient chart and begins documenting an encounter using Ava Scribe. The chart loads with the clinic's current configuration, including the active encounter template, required fields, and AutoChart settings. While the physician is mid-documentation, the clinic administrator updates the encounter template to add a mandatory "Social History" section and changes the default billing code for general assessments. The physician completes the encounter and saves the chart. The saved encounter uses the old template (missing the now-required Social History section) and the old billing code. The chart passes validation because the physician's session still holds the pre-mutation schema.

**Why It's Hard to Catch:**
The physician's session loaded the template at chart-open time, and the save operation validates against the cached template. The new template requirement only applies to charts opened after the configuration change. There is no mechanism to push configuration updates to active sessions, and forcing a session refresh mid-encounter would risk data loss. The discrepancy only surfaces when a compliance audit checks for the mandatory Social History field and finds charts created during the mutation window that lack it.

**Impact:**
Charts saved during the mutation window become non-compliant with the current template schema. If the mandatory Social History section was added for regulatory compliance (e.g., a new provincial reporting requirement), every chart missing that section represents a compliance gap. Retroactively adding the section requires a chart amendment workflow, which is time-consuming and may not be possible if the physician does not recall the patient's social history from the encounter.

**Test Approach:**
Open a test chart in one session. In a separate admin session, update the encounter template to add a required field. Attempt to save the chart in the physician session. Verify that either (a) the system warns the physician about the template change and prompts them to add the new required field, or (b) the save succeeds but flags the chart for post-hoc review. Check that the audit trail records which template version was active when the chart was opened versus when it was saved. Test that the risk analyzer identifies active sessions using outdated template versions and quantifies the number of affected encounters.

---

## Case 2: Feature Flag Toggled During Active Patient Encounter

**Affected Dimensions:** Feature Flags, Clinical Workflow, Patient Safety

**Severity:** Critical

**Scenario:**
The clinic has the Ava Scribe AI-assisted documentation feature enabled via a feature flag. A physician is using Ava Scribe to transcribe a patient encounter in real time. An administrator disables the Ava Scribe feature flag (perhaps due to a reported issue or a licensing change). The physician's active Ava Scribe session does not terminate immediately, but the next API call to the Ava Scribe service fails with an authorization error. The transcription stops mid-encounter, and the partially transcribed note is saved without the remaining content. The physician may not notice the gap if they are focused on the patient rather than the screen.

**Why It's Hard to Catch:**
Feature flag changes are designed to take effect quickly for operational agility -- this is a feature, not a bug. The problem is that the immediate effect on active sessions is undefined. Some feature-flagged components check the flag on every API call (and will fail mid-use), while others check only at component initialization (and will continue working until the session ends). There is no unified policy for how active sessions should handle mid-session flag changes, and the behavior varies by feature.

**Impact:**
A partially transcribed note missing key clinical details (assessment, plan, medication changes) is a patient safety risk. If the physician does not notice the truncation, the incomplete note becomes part of the permanent medical record. Other providers reviewing the chart may make clinical decisions based on incomplete information. The gap in the note may also create billing issues if the documented services do not support the billed code.

**Test Approach:**
Start an Ava Scribe transcription session. Toggle the Ava Scribe feature flag to disabled. Verify that the active session either (a) continues until the encounter is saved with a warning that the feature will be unavailable for future encounters, or (b) gracefully pauses with a clear notification and preserves all transcribed content. Confirm that no partial note is silently saved. Test the same scenario with AutoChart and Ava Connect feature flags. Verify that the system implements a "grace period" policy for feature flags affecting active clinical sessions, where the flag change is queued until the session completes.

---

## Case 3: Module Disabled While Provider Is Using Dependent Feature

**Affected Dimensions:** Module Dependencies, Clinical Workflow, Data Loss

**Severity:** High

**Scenario:**
A clinic has the eLabs module enabled, which integrates with Ava's charting system to display lab results inline within patient charts. A provider is reviewing a patient's chart and has the lab results panel open, cross-referencing results with their clinical notes. The administrator disables the eLabs module because the clinic is switching lab integration providers. The provider's lab results panel goes blank or displays an error. They attempt to refresh the page, and the entire labs section disappears from the chart because the module is now disabled. The provider loses their workflow context and cannot reference the lab values they were just reviewing.

**Why It's Hard to Catch:**
Module enable/disable is treated as an admin operation that affects the next page load, not active pages. The UI component for labs checks module status on render, so a refresh after module disable removes the component entirely. There is no "read-only legacy" mode that would allow viewing previously loaded data after a module is disabled. The provider's frustration is immediate, but there is no data loss per se -- the lab results are still in the database. The risk is clinical: a provider making decisions without access to data they were just reviewing.

**Impact:**
The provider may need to make a clinical decision (e.g., adjusting a medication dose based on renal function labs) without access to the data they were reviewing moments ago. Navigating to an external lab portal or calling the lab introduces delay in a workflow that was previously seamless. If the provider proceeds from memory rather than re-verifying the lab value, there is a risk of error, especially for values with narrow therapeutic ranges (e.g., warfarin INR, digoxin levels).

**Test Approach:**
Open a patient chart with lab results visible. Disable the eLabs module via admin settings. Refresh the provider's page and verify behavior. The expected safe behavior is that previously loaded lab data remains visible in read-only mode with a banner indicating the module is disabled, rather than disappearing entirely. Test that re-enabling the module restores full functionality without requiring a new session. Verify that the risk analyzer warns administrators about active provider sessions that will be affected before a module is disabled.

---

## Case 4: Billing Type Removed While Claim in Progress

**Affected Dimensions:** Billing, Claims, Data Integrity, Revenue

**Severity:** Critical

**Scenario:**
A physician starts creating a billing claim for a patient encounter using billing type "03.04A - Complete Assessment" (Alberta fee schedule). The claim form is partially filled out with diagnostic codes and service date. Before the physician submits the claim, the administrator removes billing code 03.04A from the clinic's active fee schedule (perhaps because it was replaced by a new code in an AHS fee schedule update). The physician clicks "Submit Claim" and receives a cryptic validation error ("Invalid billing code") without any indication of what changed or what the replacement code should be. The physician abandons the claim, and the encounter goes unbilled.

**Why It's Hard to Catch:**
Billing code removal is a legitimate administrative action during fee schedule updates. The system validates the billing code at submission time against the current fee schedule, which no longer includes the removed code. However, the error message does not explain that the code was recently removed or suggest a replacement. The physician may assume the error is a system glitch and retry several times before giving up. The unbilled encounter creates a revenue gap that may not be caught until end-of-month reconciliation.

**Impact:**
Unbilled encounters represent direct revenue loss for the clinic. If the physician abandons the claim and does not follow up, the encounter may never be billed. Even if the billing staff catches the issue during reconciliation, they must determine the correct replacement code and may need the physician's input to confirm the service type. For clinics processing hundreds of claims per week, even a small percentage of abandoned claims during fee schedule transitions adds up to significant lost revenue.

**Test Approach:**
Create a billing claim with a valid code. Before submitting, remove that code from the fee schedule via admin settings. Submit the claim and verify that the error message explicitly identifies the code as recently removed and suggests the replacement code (if one exists). Verify that the claim draft is preserved with the original code flagged for update rather than being rejected entirely. Test that the risk analyzer flags fee schedule changes that affect in-progress claims and alerts administrators to schedule fee changes during off-hours when fewer claims are in progress.
