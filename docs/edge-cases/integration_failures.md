# Integration Dependency Failures

Integration dependency failures occur when external systems that Ava's EMR relies on behave unexpectedly, return ambiguous errors, or go offline entirely. These edge cases are critical because Ava Connect, PrescribeIT, Netcare, Pharmanet, and third-party pharmacy (TPP) integrations form the backbone of clinical workflows. A misconfigured fallback behavior or an unhandled error code can lead to lost prescriptions, missed medication alerts, or silent data gaps that clinicians may not discover until a patient safety event surfaces. The risk is compounded by the fact that different provinces use different integration stacks with subtly different error semantics.

---

## Case 1: PrescribeIT Error 901 vs 999 Handling Differences by Province

**Affected Dimensions:** Prescriptions, PrescribeIT, Error Handling, Province Configuration

**Severity:** Critical

**Scenario:**
When Ava Connect submits a prescription via PrescribeIT, the response may include error code 901 (pharmacy not accepting electronic prescriptions) or error code 999 (generic system error). In Alberta, error 901 should trigger an automatic fallback to fax-based prescription delivery. In British Columbia, the same error should prompt the prescriber to select an alternative pharmacy because fax fallback is not supported for certain controlled substances. A clinic configuration that applies AB error-handling logic in a BC context silently faxes a controlled substance prescription that should have been redirected, creating a compliance gap.

**Why It's Hard to Catch:**
Error 901 and 999 are infrequent in production -- most prescriptions succeed on the first attempt. The error-handling logic is buried in integration configuration rather than in the clinical workflow, so prescribers never see the branching behavior during normal use. QA environments may not simulate these specific error codes, and the difference between AB and BC handling is a business rule, not a technical one, so it passes all integration tests.

**Impact:**
A controlled substance prescription delivered via fax in BC without proper authorization tracking creates a compliance gap that could be flagged during a College of Pharmacists of BC audit. The prescriber may face disciplinary action, and the clinic's PrescribeIT integration may be suspended pending review. The patient may also experience a delay in receiving their medication if the pharmacy rejects the faxed controlled substance prescription.

**Test Approach:**
Mock PrescribeIT responses with error codes 901 and 999 for both AB and BC clinic configurations. Verify that error 901 in AB triggers fax fallback, while in BC it prompts pharmacy selection. Verify that error 999 in both provinces triggers a retry with exponential backoff and alerts the prescriber after three failures. Confirm that controlled substance prescriptions never silently fall back to fax in BC. Test that the error-handling configuration includes a province-specific rule engine and that the risk analyzer flags clinics where the error-handling rules do not match the clinic's province.

---

## Case 2: Netcare and Pharmanet Downtime Fallback Behavior

**Affected Dimensions:** Lab Results, Medication History, Clinical Decision Support, Patient Safety

**Severity:** Critical

**Scenario:**
Netcare (AB) or Pharmanet (BC) experiences scheduled or unscheduled downtime. Ava's EMR is configured to display a "provincial data unavailable" banner and allow clinicians to proceed without medication history. However, the AutoChart feature continues to generate clinical summaries that reference "no known drug interactions" based on the empty medication list, rather than flagging that the medication history could not be retrieved. A physician relies on the AutoChart summary, prescribes a medication, and the patient experiences an adverse drug interaction with a medication that would have appeared in the provincial record.

**Why It's Hard to Catch:**
AutoChart's AI summarization treats an empty medication list the same way it treats a confirmed empty medication history. There is no metadata flag distinguishing "no medications found" from "medication source unavailable." The banner warning is displayed in the demographics area of the chart, but AutoChart's summary panel is in a different section of the UI, so the clinician may not connect the two. Integration downtime is also inherently transient, making it difficult to reproduce during testing.

**Impact:**
An adverse drug interaction caused by missing medication history is a patient safety event that may require hospitalization, result in a malpractice claim, and trigger a College of Physicians investigation. The physician's defense that they relied on the EMR's drug interaction check is undermined by the fact that the system displayed "no known drug interactions" rather than "medication data unavailable." The liability falls on both the physician (for not recognizing the data gap) and Ava (for presenting absence of data as absence of risk).

**Test Approach:**
Simulate Netcare/Pharmanet downtime by blocking the integration endpoint. Open a patient chart and verify that AutoChart's summary explicitly states "medication history could not be retrieved from [Netcare/Pharmanet]" rather than "no known drug interactions." Verify that the clinical decision support module suppresses interaction checks and displays a warning rather than returning false negatives. Test both scheduled downtime (with advance notice flag) and unscheduled downtime (connection timeout). Confirm that Ava Scribe's transcription notes include a caveat about unavailable medication data when the integration is down during an encounter.

---

## Case 3: Third-Party Pharmacy Monitored Medications Alerts

**Affected Dimensions:** Prescriptions, TPP Integration, Monitored Drug Alerts, Compliance

**Severity:** High

**Scenario:**
Alberta's Triplicate Prescription Program (TPP) requires special handling for monitored medications (opioids, benzodiazepines, etc.). When a physician prescribes a monitored medication, Ava Connect should query the TPP registry and display the patient's monitored drug history before the prescription is finalized. A configuration error sets the TPP query to asynchronous mode, meaning the prescription is submitted via PrescribeIT before the TPP response arrives. The TPP alert showing recent opioid fills at other pharmacies appears in the physician's inbox 30 seconds later, but the prescription has already been sent.

**Why It's Hard to Catch:**
The asynchronous TPP query is a valid configuration option designed for non-monitored medication workflows where the TPP check is informational rather than blocking. The misconfiguration is a single field (tpp_query_mode: "async" vs "sync") that does not produce any error. The prescription submission succeeds, the TPP response arrives, and both events are logged -- but the temporal ordering is wrong. Auditing the logs shows both events occurred, and without checking timestamps, the gap is invisible.

**Impact:**
A prescription sent without reviewing the patient's monitored drug history may contribute to opioid misuse or drug-seeking behavior going undetected. Alberta's TPP program exists specifically to prevent this scenario. If the physician later discovers the patient had recent opioid fills at multiple pharmacies, the prescription cannot be recalled from PrescribeIT -- it has already been dispensed. The clinic may face a TPP compliance review, and the prescriber may be flagged for inadequate monitoring of controlled substance prescriptions.

**Test Approach:**
Configure TPP query mode to async and prescribe a monitored medication for a test patient with existing TPP history. Verify that the system either blocks async mode for monitored medications or delays PrescribeIT submission until the TPP response is received. Add a test that checks the timestamp ordering: TPP response must precede PrescribeIT submission for any medication flagged as monitored. Run the risk analyzer against the configuration and confirm it flags async TPP mode as high severity. Verify that the risk analyzer distinguishes between monitored and non-monitored medication configurations and only flags async mode for monitored drug classes.

---

## Case 4: eDelivery Format Differences Between AB and BC

**Affected Dimensions:** Prescriptions, eDelivery, PrescribeIT, Province Configuration

**Severity:** Medium

**Scenario:**
Ava Connect uses eDelivery to transmit prescription data to pharmacies. The eDelivery message format includes province-specific fields: Alberta requires the practitioner's CPSA (College of Physicians and Surgeons of Alberta) identifier, while BC requires the CPSBC identifier and a different prescriber class code. A multi-province clinic group uses a shared eDelivery template that includes the AB-specific CPSA field but omits the BC CPSBC field. Prescriptions from BC clinics are submitted with a missing prescriber identifier, causing pharmacies to reject or manually process the prescription.

**Why It's Hard to Catch:**
The eDelivery schema validation in Ava Connect checks that required fields are present but uses the AB schema for all provinces because the schema selector defaults to the first configured province. BC prescriptions pass validation (CPSA field is populated from the physician's profile) but contain the wrong identifier type. The pharmacy's system rejects the message or flags it for manual review, but the error response from eDelivery is a generic "prescriber validation failed" that does not indicate the province-specific field mismatch.

**Impact:**
Rejected or manually processed prescriptions at the pharmacy create delays for patients and additional work for pharmacy staff who must contact the clinic to verify prescriber credentials. Repeated issues may lead the pharmacy to flag Ava-originated prescriptions as unreliable, undermining trust in the electronic prescription system and potentially causing pharmacies to request fax-based prescriptions as a workaround -- defeating the purpose of the PrescribeIT integration.

**Test Approach:**
Generate eDelivery messages for both AB and BC clinics and validate them against the province-specific schema. Verify that AB messages include CPSA identifiers and BC messages include CPSBC identifiers. Test that the schema selector uses the clinic's province, not a hardcoded default. Submit test messages to the eDelivery sandbox and confirm that both province variants are accepted without manual intervention. Verify that the risk analyzer checks all eDelivery template configurations for province-specific field completeness during clinic onboarding and flags any template missing province-required fields.
