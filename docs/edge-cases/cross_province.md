# Cross-Province Configuration Conflicts

Cross-province configuration conflicts arise when clinics operate across multiple Canadian provinces or when patients from one province receive care in another. These edge cases are particularly dangerous because they often pass surface-level validation -- the configuration looks correct for the home province but silently produces errors when applied in a different provincial context. Ava's multi-province deployment model (primarily AB and BC, with ON expansion) means that province-specific billing codes, formulary rules, consent requirements, and integration endpoints can collide in ways that are difficult to detect without explicit cross-province testing.

---

## Case 1: Alberta Billing Codes Submitted to BC Clinic

**Affected Dimensions:** Billing, Province Configuration, Claims Processing

**Severity:** Critical

**Scenario:**
A physician who practices in both Alberta and British Columbia has their Ava EMR profile configured with Alberta Health Services (AHS) billing codes. When they log into a BC clinic location, the system pre-populates claim forms with AB fee schedule codes (e.g., 03.04A for a complete assessment) instead of the corresponding BC MSP fee item (00100). The claim is submitted to BC MSP with an Alberta billing code, resulting in automatic rejection. If the clinic has auto-submission enabled, dozens of claims may be sent before anyone notices.

**Why It's Hard to Catch:**
The billing code field accepts any alphanumeric string, so there is no immediate validation error. AB codes and BC fee items have completely different formats (AB uses XX.XXX letter suffixes, BC uses five-digit numeric codes), but the system treats them as opaque strings. The rejection only surfaces days later when MSP returns the remittance advice.

**Impact:**
Rejected claims create a backlog in the clinic's billing queue. The billing staff must identify the province mismatch, re-code each claim with the correct BC fee item, and resubmit. For a physician seeing 20+ patients per day, a full day of miscoded claims can take hours to remediate. If the clinic does not catch the rejections promptly, they risk exceeding MSP's resubmission window, resulting in permanent revenue loss.

**Test Approach:**
Configure a test physician with an AB billing profile and simulate a login at a BC clinic location. Verify that the billing module either switches to BC fee items automatically or blocks claim creation with an explicit province mismatch warning. Validate that the province associated with the clinic location is cross-referenced against the fee schedule loaded for the active session. Additionally, test the auto-submission pathway: enable auto-submit and verify that a province mismatch halts the batch rather than submitting invalid claims. Confirm that the risk analyzer produces a specific warning when a physician profile's billing province differs from any clinic location they are assigned to.

---

## Case 2: Out-of-Province Patient Triggering Wrong Formulary

**Affected Dimensions:** Prescriptions, Formulary, PrescribeIT Integration

**Severity:** High

**Scenario:**
A patient with an Alberta health care number visits a walk-in clinic in BC. The physician uses Ava Scribe to document the encounter and prescribes a medication. The system checks the formulary based on the clinic's province (BC PharmaCare) rather than the patient's home province. The medication is covered under Alberta's drug plan but requires Special Authorization under BC PharmaCare. Ava Connect sends the prescription via PrescribeIT with BC formulary flags, and the pharmacy rejects it because the coverage check references the wrong provincial plan.

**Why It's Hard to Catch:**
The formulary lookup defaults to the clinic's configured province, which is correct for 95%+ of patients. Out-of-province patients are rare in most clinics, so this path is almost never exercised. The patient's province of registration is stored in their demographics but is not automatically linked to the formulary engine's province selector.

**Impact:**
The patient may leave the pharmacy without their medication if the pharmacy cannot resolve the coverage issue on the spot. For time-sensitive medications (antibiotics, pain management), this delay has direct clinical consequences. The prescriber may need to be contacted to reissue the prescription with correct provincial coverage flags, adding friction to both the clinic and pharmacy workflows.

**Test Approach:**
Register a test patient with an AB health care number in a BC clinic. Initiate a prescription workflow and verify that the formulary check either uses the patient's home province or flags the province mismatch to the prescriber. Check that PrescribeIT messages include the correct provincial drug plan identifier based on patient registration, not clinic location. Test with medications that have different coverage status across provinces (covered in AB, Special Authorization in BC) to verify the formulary engine correctly identifies the discrepancy.

---

## Case 3: Ontario Expansion Clinic Missing Province-Specific Integrations

**Affected Dimensions:** Integrations, Lab Results, Provincial Health Network

**Severity:** Critical

**Scenario:**
A new Ava client in Ontario is onboarded using a configuration template derived from an Alberta clinic. The template includes Netcare integration settings for lab results and medication history. Ontario uses the Ontario Laboratories Information System (OLIS) and the Digital Health Drug Repository (DHDR), not Netcare. The clinic goes live, and lab orders are routed to a Netcare endpoint that either does not respond or returns errors. Clinicians have no lab results flowing into the EMR and resort to manual workarounds, creating patient safety risk.

**Why It's Hard to Catch:**
The configuration template passes validation because the integration fields are populated with syntactically valid URLs and credentials. There is no province-aware validation that checks whether the configured integration endpoints match the clinic's province. The error only manifests at runtime when the integration attempts to connect, and the error messages from Netcare may be generic timeouts rather than explicit "wrong province" rejections.

**Impact:**
A clinic without functioning lab integration is effectively operating without electronic lab results. Physicians must call labs for results, check external portals, or rely on faxed copies -- all of which introduce delays and increase the risk of missed critical results. The clinic may not discover the integration failure until after go-live if the onboarding team only tested connectivity to the endpoint (which may accept connections) without verifying that the endpoint returns valid province-specific data.

**Test Approach:**
Create a clinic configuration with province set to ON but integration endpoints pointing to AB Netcare. Run the configuration risk analyzer and verify it flags the mismatch between clinic province and integration endpoint province. Additionally, simulate a lab order submission and confirm the system produces a clear error identifying the province-integration mismatch rather than a generic connection timeout. Verify that the onboarding checklist includes a province-integration compatibility check that runs automatically before a clinic is marked as go-live ready.

---

## Case 4: Province-Specific Consent Requirements Mismatch

**Affected Dimensions:** Patient Consent, Privacy, Audit Trail

**Severity:** High

**Scenario:**
Alberta's Health Information Act (HIA) allows implied consent for the "circle of care," meaning providers can access a patient's Netcare records without explicit patient consent in most treatment scenarios. British Columbia's Freedom of Information and Protection of Privacy Act (FIPPA) and E-Health Act have different consent directives, requiring explicit patient consent for certain data-sharing activities. A clinic operating in BC uses a configuration copied from an AB template that has the consent gate disabled (relying on AB implied consent rules). Providers access patient records via Pharmanet without the required BC consent workflow, creating a privacy compliance violation.

**Why It's Hard to Catch:**
Consent configuration is a boolean or enum field that does not inherently encode provincial legal requirements. An admin reviewing the configuration sees "consent_required: false" and may not realize this is a compliance violation in BC. The system functions correctly from a technical standpoint -- data flows as expected -- but the clinic is operating outside its legal obligations. This only surfaces during a privacy audit or a patient complaint.

**Impact:**
A privacy compliance violation in BC can result in investigation by the Office of the Information and Privacy Commissioner, potential fines, and reputational damage to both the clinic and Ava. If a patient files a complaint about unauthorized data sharing, the clinic cannot demonstrate that consent was obtained because the consent workflow was never triggered. The violation may also affect the clinic's participation in provincial health information exchanges.

**Test Approach:**
Configure a BC clinic with consent_required set to false. Verify that the risk analyzer flags this as a compliance violation based on the province field. Test that when a BC clinician attempts to access Pharmanet data, the system enforces the consent workflow regardless of the configuration flag, treating the provincial legal requirement as a hard constraint that overrides clinic-level settings. Verify that the compliance check runs at configuration save time (not just at runtime) and prevents saving a non-compliant consent configuration for BC clinics.
