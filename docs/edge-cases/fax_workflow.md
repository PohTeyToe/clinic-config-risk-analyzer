# Fax Workflow Edge Cases

Fax workflow edge cases are among the most operationally impactful issues in Ava's EMR because fax remains the primary communication channel between clinics, specialists, pharmacies, and hospitals in the Canadian healthcare system. Ava integrates with fax providers (SRFax, eFax) to manage inbound and outbound fax workflows, including document receipt, classification, routing, sending, and delivery confirmation. The edge cases in this domain involve multi-page document handling, provider-specific delivery semantics, duplicate creation from retries, and the intersection of fax delivery with confidentiality controls. Each of these scenarios can result in lost clinical information, duplicate records, or privacy violations.

---

## Case 1: Multi-Page Fax Split Loses Context Between Inbound Queues

**Affected Dimensions:** Fax Processing, Document Integrity, Inbound Routing, Clinical Completeness

**Severity:** High

**Scenario:**
A hospital discharge summary arrives as a 12-page fax. The document contains the discharge summary (pages 1-4), medication reconciliation (pages 5-7), follow-up instructions (pages 8-10), and attached lab results (pages 11-12). Ava's inbound fax processor uses a page-splitting algorithm that separates the fax into logical documents based on detected page breaks and header patterns. The algorithm correctly identifies the discharge summary and medication reconciliation as separate documents but fails to detect the transition between follow-up instructions and lab results (pages 10-11) because the lab results start mid-page without a header. Pages 8-12 are grouped as a single document and classified as "Follow-Up Instructions." The lab results on pages 11-12 are filed under the wrong document type and may not be reviewed by the physician as lab results.

**Why It's Hard to Catch:**
The page-splitting algorithm works correctly for the majority of faxes where document boundaries align with page boundaries and include clear headers. Mid-page document transitions are uncommon in well-formatted faxes but occur frequently with hospital discharge packages where different departments contribute sections without standardized page formatting. The misclassification does not produce an error -- the document is filed in the patient's chart, just under the wrong type. The physician reviewing "Follow-Up Instructions" may skim past the lab results appendix, especially if the follow-up instructions themselves are the primary clinical interest. The lab results are in the chart but effectively invisible because they are not indexed as lab results and do not appear in the lab results view.

**Impact:**
Lab results buried within a misclassified "Follow-Up Instructions" document do not appear in the patient's lab results timeline, are not flagged by critical value alerts, and are not included in AutoChart's clinical summary. If the lab results contain critical values (e.g., elevated troponin, positive blood culture), the delay in physician review can have life-threatening consequences. The clinic may also fail provincial lab result management audits because the results are not tracked in the lab results workflow.

**Test Approach:**
Send a multi-page fax with a mid-page document type transition (e.g., follow-up instructions flowing directly into lab results without a page break). Verify that the classifier either (a) detects the content type change mid-page and splits the document accordingly, or (b) tags the document with multiple document types so it appears in both the follow-up and lab result views. Test that the risk analyzer flags inbound fax configurations where the page-splitting algorithm is set to "header-based only" and recommends enabling "content-based" splitting for clinics that receive hospital discharge packages. Verify that the system includes a page count check that alerts staff when a fax from a known hospital source has fewer pages than expected based on historical patterns.

---

## Case 2: SRFax vs eFax Delivery Confirmation Differences

**Affected Dimensions:** Outbound Fax, Delivery Confirmation, Provider Integration, Workflow Reliability

**Severity:** Medium

**Scenario:**
A clinic uses SRFax for outbound fax delivery. SRFax provides delivery confirmation via a callback webhook that reports success or failure within 60-90 seconds. The clinic's Ava configuration relies on this confirmation to update the fax status in the sent items queue (marking it as "Delivered" or "Failed"). The clinic switches to eFax as their fax provider. eFax uses a different confirmation model -- it provides an initial "Accepted" status immediately but delivers the final "Delivered" or "Failed" status asynchronously, sometimes up to 15 minutes later. Ava's fax workflow was designed around SRFax's near-immediate confirmation timing. After the switch to eFax, outbound faxes show "Accepted" status but never update to "Delivered" because the delayed eFax callback arrives after Ava's webhook listener has timed out (configured for a 2-minute window based on SRFax timing).

**Why It's Hard to Catch:**
The fax appears to send successfully -- the "Accepted" status is displayed, and the document leaves the outbox. The missing "Delivered" confirmation is a subtle status gap that most users do not check. The physician or MOA who sent the fax assumes it was delivered. The issue only surfaces when a recipient (specialist, pharmacy) reports they never received the fax, and the clinic checks the fax log to find a permanent "Accepted" status that never progressed to "Delivered" or "Failed." The webhook timeout configuration is a system-level setting that was not updated during the provider switch because the fax provider migration guide did not mention provider-specific timing differences.

**Impact:**
Faxes stuck in permanent "Accepted" status give staff a false sense of delivery. Critical referrals, prescription faxes (in provinces where fax is used as a PrescribeIT fallback), and authorization forms may never reach their recipients. The clinic discovers the delivery failure only when the recipient follows up asking for the document, by which time days or weeks may have passed. For urgent referrals, this delay directly impacts patient care. The systemic nature of the problem (all eFax-sent faxes are affected) means the issue is widespread but invisible until individual faxes are investigated.

**Test Approach:**
Configure the fax integration with eFax and send a test fax. Verify that the webhook listener timeout is configurable per fax provider and is set appropriately for eFax's asynchronous confirmation model (minimum 15-minute window). Test that faxes in "Accepted" status for longer than the expected confirmation window are flagged as "Confirmation Pending" with an alert to the sender. Verify that the risk analyzer checks the fax provider configuration against the webhook timeout setting and warns when the timeout is shorter than the provider's expected confirmation delivery time. Test that the fax provider migration checklist includes provider-specific webhook timing parameters as a mandatory configuration step.

---

## Case 3: Fax Retry Creating Duplicate Records

**Affected Dimensions:** Outbound Fax, Retry Logic, Duplicate Detection, Clinical Communication

**Severity:** High

**Scenario:**
A physician sends a referral fax to a specialist. The fax fails on the first attempt (busy signal). Ava's retry logic automatically retries the fax after 5 minutes. The retry succeeds, but the original attempt also eventually succeeds (the busy signal was transient, and the fax provider's internal retry delivered the original attempt). The specialist receives two identical referral faxes. The specialist's office, following their intake process, creates two referral records for the same patient -- one for each received fax. The patient is contacted twice for scheduling and may end up with duplicate appointments, duplicate intake paperwork, or confusion about whether two separate referrals were intended.

**Why It's Hard to Catch:**
Ava's retry logic correctly detected the initial failure and correctly retried. The problem is that the fax provider's internal retry mechanism also retried the original attempt, creating a double-send that Ava is unaware of. From Ava's perspective, the first attempt failed and the second succeeded -- there is no indication that both were ultimately delivered. The duplicate is on the recipient's side, outside Ava's visibility. The specialist's office has no way to know whether two identical faxes represent one referral sent twice or two separate referrals (e.g., for different conditions), so they conservatively create two records.

**Impact:**
Duplicate referrals at the specialist's office waste administrative resources and may result in the patient being scheduled for two appointments. If the specialist's intake process includes pre-appointment diagnostics (blood work, imaging), the patient may undergo unnecessary duplicate testing. The specialist may also be confused by receiving two identical referrals and contact the clinic for clarification, consuming staff time on both sides. In aggregate, duplicate faxes erode the specialist's confidence in referrals from the clinic and may lead them to delay processing until they can verify each referral's uniqueness.

**Test Approach:**
Simulate a fax delivery where the initial attempt returns a failure status but the fax provider eventually delivers it. Verify that Ava's retry logic includes a deduplication mechanism such as a unique fax ID embedded in the document header or a cover page that the recipient can use to identify duplicates. Test that the system tracks both the original and retry attempt statuses and updates the original to "Delivered" if the provider reports late success. Verify that the risk analyzer flags retry configurations where no deduplication mechanism is enabled and the retry interval is shorter than the fax provider's internal retry window.

---

## Case 4: Outbound Fax Containing Confidential Note Despite Toggle

**Affected Dimensions:** Confidentiality, Outbound Fax, Privacy, Compliance

**Severity:** Critical

**Scenario:**
A physician marks a patient encounter note as "Confidential" using Ava's confidentiality toggle. The confidential note contains details about a substance use disorder assessment. Later, the physician generates a "Complete Chart Summary" to fax to a specialist as part of a referral. The chart summary generation pulls from all encounter notes in the patient's chart. The confidentiality toggle controls visibility within the EMR's UI (restricting which users can view the note) but does not apply a data-level filter to document generation workflows. The chart summary PDF includes the confidential substance use note, and the fax is sent to the specialist. The specialist's office, which has multiple staff processing incoming faxes, now has access to the confidential note content.

**Why It's Hard to Catch:**
The confidentiality toggle is implemented as a UI-level access control, not a data-level classification. The document generation engine (which produces the chart summary PDF) accesses the database directly using a service account with full read permissions, bypassing the UI-level confidentiality filter. The physician who generated the chart summary may not realize the confidential note is included because the PDF is generated as a single combined document, and they may not review every page before sending. The generated PDF does not visually distinguish confidential content from non-confidential content. The privacy violation occurs silently, and the physician may never learn that confidential information was disclosed.

**Impact:**
A confidential substance use assessment faxed to a specialist's office is received by intake staff who may not have appropriate training or authorization to handle sensitive information. The document may be stored in the specialist's paper or electronic filing system without appropriate access controls, creating a permanent copy of the confidential information outside the originating clinic's control. The patient may discover the disclosure when the specialist's office references their substance use history in a subsequent visit, causing a loss of trust and a potential complaint to the provincial privacy commissioner.

**Test Approach:**
Create a patient chart with a mix of regular and confidential encounter notes. Generate a "Complete Chart Summary" PDF and verify that confidential notes are excluded by default, with an explicit opt-in checkbox that warns about the inclusion of confidential content. Verify that if confidential content is included (with physician consent), the confidential sections are visually marked in the PDF (e.g., bordered, labeled "CONFIDENTIAL"). Test that the fax workflow checks for confidential content in the outbound document and requires physician confirmation before sending. Verify the risk analyzer flags clinic configurations where the chart summary generator does not filter confidential notes. Test that the PDF preview step in the fax workflow highlights confidential content with a visual indicator so the physician can review and redact before sending.
