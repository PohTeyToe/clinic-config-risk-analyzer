# Multi-Role Permission Conflicts

Multi-role permission conflicts emerge when users hold multiple roles within Ava's EMR or when different users with different permission levels interact with the same resources simultaneously. Ava's role-based access control (RBAC) system assigns permissions based on roles such as Physician (MD), Nurse Practitioner (NP), Medical Office Assistant (MOA), and Administrator. These roles are not always mutually exclusive, and the permission resolution logic can produce unexpected results when roles overlap, conflict, or interact through shared resources like charts, templates, and billing forms. These edge cases are dangerous because they can either expose sensitive data to unauthorized users or block authorized users from completing clinical workflows.

---

## Case 1: Concurrent Chart Access with Different Permission Levels

**Affected Dimensions:** Chart Access, RBAC, Data Visibility, Audit Trail

**Severity:** High

**Scenario:**
A physician (MD role) and a Medical Office Assistant (MOA role) have the same patient chart open simultaneously. The physician can see all chart sections including psychiatric notes, substance use history, and HIV status. The MOA's view should be restricted to demographics, appointment history, and billing information. However, when the physician adds a note to the psychiatric section and saves, the real-time update mechanism pushes a notification to all active sessions viewing that chart. The MOA's session receives the update event, and depending on the UI component implementation, the notification preview may include a snippet of the psychiatric note content -- content the MOA is not authorized to view.

**Why It's Hard to Catch:**
The access control check is performed at the API level when data is initially loaded, but real-time update notifications may bypass the per-field permission check because they use a different data pathway (WebSocket push vs REST API pull). The notification system is designed for performance and sends chart-level change events rather than field-level filtered events. The privacy violation is transient -- it appears in a notification toast for a few seconds and is not persisted in the MOA's view -- making it nearly impossible to catch through standard QA testing that focuses on page load states.

**Impact:**
Even a brief exposure of restricted clinical data to an unauthorized role constitutes a privacy breach under provincial health information legislation (HIA in Alberta, FIPPA in BC). The breach must be reported to the clinic's privacy officer, and depending on the sensitivity of the exposed information, it may need to be reported to the provincial privacy commissioner. The patient must also be notified, which can damage the patient-provider relationship and the clinic's reputation.

**Test Approach:**
Open the same patient chart in two sessions: one as MD, one as MOA. In the MD session, add a note to a restricted section (psychiatric, substance use). Observe the MOA session for any notification content that includes restricted data. Verify that the WebSocket notification payload is filtered based on the receiving user's role before being sent. Confirm that the MOA's chart view does not update to show restricted sections even after a page refresh. Test with multiple restricted data types (psychiatric, substance use, sexual health, HIV status) to ensure comprehensive field-level filtering.

---

## Case 2: NP Prescription Authority vs MD-Only Features

**Affected Dimensions:** Prescriptions, Scope of Practice, PrescribeIT, Compliance

**Severity:** Critical

**Scenario:**
A Nurse Practitioner (NP) logs into Ava's EMR and opens the prescription module. In Alberta, NPs have independent prescribing authority for most medications but cannot prescribe certain controlled substances (Schedule 1 narcotics) without a collaborative practice agreement with a physician. The system's prescription module checks the user's role and applies prescribing restrictions. However, the NP is also assigned a "Clinic Lead" administrative role that grants broader system access. The permission resolver uses a "most permissive" union of all assigned roles, and the Clinic Lead role inherits MD-level prescription permissions because it was cloned from the MD role template during initial clinic setup. The NP can now prescribe Schedule 1 narcotics without the system flagging the scope-of-practice violation.

**Why It's Hard to Catch:**
The "most permissive" permission resolution is the correct default behavior for most administrative permissions (an NP who is also a Clinic Lead should be able to access admin dashboards). The problem is that clinical scope-of-practice restrictions should use "most restrictive" resolution, not "most permissive." The configuration does not distinguish between administrative permissions (which should union) and clinical permissions (which should intersect). The Clinic Lead role was cloned from MD without removing clinical permissions because the cloning tool copies all permissions by default.

**Impact:**
An NP prescribing outside their scope of practice is a regulatory violation that can result in disciplinary action from the College of Registered Nurses of Alberta (CRNA), suspension of prescribing privileges, and liability for the clinic. The prescription itself, once dispensed, cannot be retroactively voided, and the patient may be harmed by receiving a medication that the NP was not clinically authorized to assess and prescribe. The Clinic Lead role template that carries inherited MD permissions becomes a systemic vulnerability affecting every NP assigned that role.

**Test Approach:**
Assign a test user both NP and Clinic Lead roles. Attempt to prescribe a Schedule 1 narcotic. Verify that the system applies scope-of-practice restrictions based on the clinical role (NP) regardless of administrative role permissions. Test that the risk analyzer flags any non-clinical role that inherits clinical permissions (prescription authority, procedure authorization) as a configuration risk. Verify that role cloning warns when clinical permissions are being copied to an administrative role. Test that the permission audit report identifies all users whose effective permissions exceed their clinical role's scope of practice.

---

## Case 3: MOA Accessing Restricted Fields via Template Workaround

**Affected Dimensions:** Templates, RBAC, Data Access, Privacy

**Severity:** High

**Scenario:**
MOAs are restricted from viewing certain clinical data fields (e.g., mental health notes, sexual health history) through Ava's field-level access control. However, MOAs have permission to use letter and referral templates to generate documents for patients. A referral template includes a merge field that pulls from the patient's full clinical history, including restricted fields, to populate the referral letter. When the MOA generates the referral letter, the template engine resolves all merge fields using a system-level data access context (not the MOA's role context), and the generated document contains clinical details the MOA should not be able to see.

**Why It's Hard to Catch:**
The template engine operates as a backend service with elevated permissions so that it can generate complete documents regardless of which user triggers the generation. This is intentional for physician-triggered document generation but creates a privilege escalation vector when MOAs use the same templates. The access control check happens at the UI layer (the MOA cannot navigate to the mental health notes section), but the template engine bypasses the UI layer entirely. The generated document is typically sent directly to a printer or fax, so the MOA may see it briefly on screen during preview.

**Impact:**
The generated referral letter containing restricted clinical data may be printed, faxed, or emailed -- each of which creates additional copies of the restricted information outside the EMR's access control boundary. Revoking access after the document has been generated and distributed is impractical. The privacy violation is amplified because the document may be received by external parties (specialists, insurance companies) who would not otherwise have access to the restricted information.

**Test Approach:**
Log in as MOA and generate a referral letter for a patient with restricted clinical data. Verify that the template engine applies the requesting user's role-based field restrictions when resolving merge fields. Restricted fields should either be omitted or replaced with "[Restricted - physician review required]" in the generated document. Test that the risk analyzer flags templates containing merge fields for restricted data categories when those templates are accessible to non-clinical roles. Verify that the template access control matrix is included in the risk analysis report, showing which roles can trigger which templates and what data each template accesses.

---

## Case 4: Admin Role Escalation During Shift Change

**Affected Dimensions:** Authentication, Role Assignment, Session Management, Audit Trail

**Severity:** Medium

**Scenario:**
During a shift change, the outgoing clinic administrator transfers admin duties to the incoming staff member by updating their role from MOA to Administrator in Ava's user management panel. The role change takes effect immediately for new sessions, but the outgoing administrator's session retains the admin role until it expires (typically 8 hours). Both users now have active admin sessions simultaneously. The incoming administrator changes the clinic's billing configuration, and the outgoing administrator -- unaware of the change -- reverts a different billing setting as part of "finishing up" their shift tasks. The two admin sessions create conflicting configuration states with no conflict detection or merge resolution.

**Why It's Hard to Catch:**
Dual admin sessions are rare but legitimate during shift transitions. The system does not enforce single-admin-session constraints because some clinics have multiple administrators. Configuration changes are applied as last-write-wins without optimistic concurrency control (no version checking). The audit trail records both changes with different timestamps and user IDs, but there is no alerting mechanism for conflicting admin actions within a short time window. The configuration ends up in an inconsistent state that reflects neither administrator's intent.

**Impact:**
An inconsistent billing configuration can result in claims being submitted with mismatched parameters (e.g., one admin set the default billing code while the other changed the diagnostic code requirements). The resulting claim rejections may not be traced back to the conflicting admin actions because each change appears legitimate in isolation. The clinic may spend hours debugging billing rejections without realizing the root cause was a simultaneous configuration conflict during a shift change.

**Test Approach:**
Create two active admin sessions. In session A, change a billing configuration value. In session B (without refreshing), change a different but related billing configuration value. Verify that the system either (a) detects the concurrent admin sessions and warns about potential conflicts, or (b) implements optimistic concurrency control that rejects the second change if the configuration version has changed since session B loaded it. Check that the audit trail clearly identifies the sequence of changes and which admin session made each change. Test that the risk analyzer flags configurations that were modified by multiple admin users within a short time window (e.g., 30 minutes) as potentially conflicting.
