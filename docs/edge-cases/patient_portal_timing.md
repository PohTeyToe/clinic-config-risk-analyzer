# Patient Portal and Auto-Release Timing

Patient portal and auto-release timing edge cases involve the interaction between Ava's configurable auto-release rules, provider review workflows, confidentiality settings, and patient-facing portal access. Ava's patient portal allows patients (and authorized caregivers) to view their clinical notes, lab results, and documents after a configurable delay period. The auto-release mechanism is designed to give providers time to review and finalize notes before patients see them, but the timing logic interacts with timezone handling, confidentiality toggles, system updates, and caregiver access rules in ways that can expose sensitive information prematurely or suppress information that should be released.

---

## Case 1: Auto-Release Clock Edge at Exactly N Days with Timezone Issues

**Affected Dimensions:** Patient Portal, Auto-Release, Timezone, Data Visibility

**Severity:** High

**Scenario:**
A clinic in Alberta (Mountain Time, UTC-7) configures auto-release to 3 days after note creation. A physician finalizes a note at 11:30 PM MT on Monday. The auto-release timer stores the creation timestamp in UTC (6:30 AM Tuesday UTC). The release calculation runs on the server using UTC, computing the release time as 6:30 AM Friday UTC, which is 11:30 PM Thursday MT. The patient, expecting the note to be available Friday morning (3 full days after Monday), checks the portal at 8:00 AM Friday MT and finds the note was already released Thursday night. For most notes this is inconsequential, but for sensitive results (cancer diagnosis, STI results), the early release means the patient sees the result 8+ hours before the physician's Friday morning call to discuss it.

**Why It's Hard to Catch:**
The auto-release system works correctly from a technical standpoint -- 3 days from Tuesday 6:30 AM UTC is Friday 6:30 AM UTC. The problem is that the clinic and patient both think in local time, where the note was created Monday and should release Thursday (or Friday depending on interpretation). The half-day offset caused by timezone conversion is small enough that most patients do not notice or care, but for sensitive results, the timing matters. QA testing typically uses a single timezone and does not test edge cases at the day boundary where timezone offsets change the date.

**Impact:**
For sensitive results, premature release means the patient learns about a serious diagnosis (cancer, HIV, pregnancy) from a clinical note on their phone screen rather than during a planned conversation with their physician. This can cause significant emotional distress and erodes trust in the clinic's communication processes. The physician may also be unprepared for the patient's call or message, as they expected the note to be released later.

**Test Approach:**
Create a note at 11:30 PM in a Mountain Time clinic. Verify that the auto-release calculation uses the clinic's local timezone, not UTC, for the "N days" computation. Test with notes created at various times near midnight in MT, PT, and ET timezones. Verify that the patient portal displays the expected release date/time in the patient's local timezone. Test with Daylight Saving Time transitions where the UTC offset changes mid-release-period (e.g., note created Saturday before spring-forward, released after spring-forward Tuesday). Confirm that the risk analyzer flags clinic configurations where the auto-release calculation timezone is set to UTC rather than the clinic's local timezone.

---

## Case 2: Confidential Toggle and Auto-Release Interaction

**Affected Dimensions:** Confidentiality, Patient Portal, Auto-Release, Privacy

**Severity:** Critical

**Scenario:**
A physician documents a sensitive encounter (e.g., substance use counseling session) and marks the note as "Confidential" using Ava's confidentiality toggle. Confidential notes are excluded from the patient portal and are only visible to the authoring provider and explicitly authorized staff. The auto-release timer is still created for the note because the auto-release system processes all notes regardless of confidentiality status. After 3 days, the auto-release job runs and releases the note to the patient portal. The auto-release job checks the note's status (finalized = yes) and the elapsed time (>3 days) but does not check the confidentiality flag. The confidential substance use counseling note appears in the patient's portal.

**Why It's Hard to Catch:**
The confidentiality toggle and the auto-release system are implemented by different modules with different data models. The confidentiality flag is stored as a note-level attribute in the clinical documentation module, while the auto-release system operates on a queue of note IDs with timestamps in the portal module. The auto-release job was built before the confidentiality feature was added and was never updated to check confidentiality status. In testing, confidential notes are rare and are usually created by specific test scenarios that do not also test auto-release timing. The two features are tested independently but not in combination.

**Impact:**
A confidential substance use counseling note appearing in the patient portal may be visible to family members who share portal access, to employers who require portal access for disability claims, or to the patient in a context where they did not expect the information to be visible. The privacy violation may violate specific confidentiality provisions of provincial health information acts and could expose the clinic to legal liability. The patient may also lose trust in the physician's assurance that the note would remain confidential and may withhold sensitive information in future encounters.

**Test Approach:**
Create a note with the confidentiality toggle enabled. Wait for (or simulate) the auto-release period to elapse. Verify that the auto-release job skips confidential notes entirely. Check that confidential notes do not appear in the auto-release queue at all, rather than being added and then filtered at release time. Test that removing the confidential flag from a note re-enrolls it in the auto-release queue with the timer starting from the flag removal date, not the original note creation date. Verify that the risk analyzer flags clinic configurations where both auto-release and confidentiality features are enabled but no integration test exists.

---

## Case 3: Manual Override of Auto-Release Not Persisting After System Update

**Affected Dimensions:** Auto-Release, System Updates, Configuration Persistence, Provider Control

**Severity:** High

**Scenario:**
A physician manually overrides the auto-release for a specific note, setting it to "Do Not Release" because they want to discuss abnormal lab results with the patient in person before the patient sees them in the portal. The override is stored as a note-level flag in the auto-release queue. During a scheduled system update over the weekend, the auto-release queue is rebuilt from the notes database as part of a migration step. The migration script populates the queue based on note creation timestamps and finalization status but does not preserve manual override flags because the override data was stored in the queue table (which was dropped and rebuilt) rather than in the notes table. Monday morning, the auto-release job processes the rebuilt queue and releases the note. The patient sees their abnormal lab results in the portal before the physician's scheduled call.

**Why It's Hard to Catch:**
System update migrations are tested against schema correctness and data integrity for the primary clinical tables. The auto-release queue is treated as a derived/cached data structure that can be rebuilt from source data, so dropping and rebuilding it is considered safe. Manual overrides are an edge case within the auto-release feature (most notes are released on schedule), and the migration test plan does not include verifying that override flags survive queue rebuilds. The override flag's storage location (queue table vs notes table) is an implementation detail that is not visible to the administrator or the physician who set the override.

**Impact:**
The patient receives abnormal results without the context that the physician intended to provide during a scheduled discussion. Depending on the nature of the results (e.g., elevated PSA suggesting prostate cancer, abnormal fetal screening results), the uncontextualized release can cause significant patient anxiety and potentially harmful self-directed actions (e.g., stopping medications, seeking emergency care unnecessarily). The physician's trust in the manual override feature is undermined, and they may resort to not documenting sensitive findings in the EMR at all, creating a different but equally serious problem.

**Test Approach:**
Set a manual "Do Not Release" override on a test note. Simulate a system update that includes an auto-release queue rebuild. Verify that the override persists after the rebuild. If the queue is rebuilt from source data, verify that override flags are stored in the notes table (source of truth), not only in the queue table. Test that the risk analyzer checks for override flags before queue rebuild operations and warns if any overrides would be lost. Verify that physicians are notified if their manual overrides are cleared by any system process.

---

## Case 4: Caregiver Access Seeing Notes Before Provider Review

**Affected Dimensions:** Caregiver Portal, Provider Review, Patient Safety, Privacy

**Severity:** Critical

**Scenario:**
A pediatric clinic configures caregiver access so that parents can view their child's clinical notes through the patient portal. The auto-release timer is set to 2 days for the clinic. A physician documents a visit for a 15-year-old patient that includes a discussion about sexual health and contraception. The physician intends to review the note and redact the sexual health discussion before the parent can see it (in accordance with the clinic's mature minor policy). However, the physician's review queue is backed up, and the 2-day auto-release timer expires before the review is completed. The note, including the sexual health discussion, is released to the portal and is visible to the caregiver (parent) account. The minor's confidential health information is disclosed to the parent.

**Why It's Hard to Catch:**
The auto-release timer does not distinguish between adult patient portal access and caregiver portal access. The timer is a clinic-wide setting, not a per-patient or per-note setting. The physician's intent to redact before release is not encoded in the system -- there is no "pending review before release" status that would pause the auto-release timer. The mature minor policy is a clinical guideline, not a system-enforced rule, so the system has no way to identify notes that require pre-release review for caregiver access. The clinic may have a manual workflow (e.g., flagging notes for review) but the auto-release timer does not check for pending review flags.

**Impact:**
Disclosure of a minor's confidential sexual health information to a parent can have serious consequences for the patient, including family conflict, loss of access to healthcare, or in severe cases, abuse. The disclosure violates the mature minor's right to confidential healthcare and may breach provincial privacy legislation. The physician's trust in the EMR's ability to protect sensitive information is damaged, and they may avoid documenting sensitive topics in the chart entirely, leaving gaps in the medical record that affect future care.

**Test Approach:**
Configure a patient under 18 with an active caregiver portal account. Create a note containing content that should be redacted for caregiver viewing (sexual health, mental health, substance use). Verify that the auto-release system either (a) suppresses caregiver access for patients under a configurable age threshold until explicit physician approval, or (b) flags notes containing sensitive content categories for mandatory review before caregiver release. Test that the risk analyzer identifies clinics with both caregiver access and auto-release enabled for pediatric patients without a mandatory review workflow configured. Verify that the age threshold is configurable (12, 14, or 16 depending on provincial mature minor guidelines) and that the system correctly calculates the patient's age at the time of the encounter, not at the time of auto-release.
