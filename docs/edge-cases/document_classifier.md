# Document Classifier Edge Cases

Document classifier edge cases involve Ava's AI-powered document classification system that processes incoming documents -- primarily inbound faxes, scanned records, and electronically received files -- and routes them to the appropriate patient chart, provider inbox, or workflow queue. The classifier uses machine learning models trained on labeled document samples to identify document type (lab result, referral letter, insurance form, specialist report), extract patient identifiers, and assign routing. These edge cases are critical because misclassification or misrouting can result in clinical information landing in the wrong patient's chart, critical results going unseen, or documents being lost in unmonitored queues.

---

## Case 1: Misrouted Fax Classified to Wrong Patient

**Affected Dimensions:** Document Classification, Patient Matching, Data Integrity, Patient Safety

**Severity:** Critical

**Scenario:**
An inbound fax from a specialist contains a consultation report for "Sarah Johnson, DOB 1985-03-14, PHN 4523-xxxxx." The clinic has two patients: "Sarah Johnson, DOB 1985-03-14, PHN 4523-12345" and "Sara Johnston, DOB 1985-03-15, PHN 4523-12346." The document classifier extracts the patient name and date of birth from the fax using OCR, but the fax quality is poor and the OCR reads the DOB as "1985-03-15" (misreading the "4" as "5"). The classifier matches the document to "Sara Johnston" based on the OCR-extracted DOB, and the specialist report is filed in the wrong patient's chart. The correct patient ("Sarah Johnson") never receives the specialist report, and the wrong patient has an unrelated specialist report in their chart.

**Why It's Hard to Catch:**
The classifier's confidence score for the match to "Sara Johnston" is high (0.92) because the OCR-extracted name is close ("Sarah Johnson" vs "Sara Johnston") and the DOB appears to match exactly. The PHN is partially redacted in the fax (common practice), so only the first four digits are available for matching, and both patients share the same prefix. The misroute is invisible unless a clinician reads the specialist report in Sara Johnston's chart and realizes it discusses conditions irrelevant to that patient. The correct patient's physician may eventually notice the missing specialist report but may attribute the delay to the specialist's office rather than a routing error.

**Impact:**
A specialist report filed in the wrong patient's chart may lead to inappropriate clinical actions -- the wrong patient may be contacted about conditions they do not have, while the correct patient misses critical follow-up. If the misrouted report contains actionable findings (e.g., malignancy, urgent surgical need), the delay in reaching the correct physician can have life-threatening consequences. Discovering and correcting the misroute requires auditing both patients' charts, removing the document from the wrong chart (which creates an audit trail entry that must be explained), and re-filing it in the correct chart.

**Test Approach:**
Create two test patients with similar names and adjacent DOBs. Send a fax with a slightly degraded image quality that targets one patient. Verify that the classifier flags the match as ambiguous when multiple near-matches exist and routes the document to a manual review queue rather than auto-filing. Test that the confidence threshold for auto-filing is configurable and that the risk analyzer warns when the threshold is set above 0.90 for clinics with patient populations that have high name similarity (e.g., clinics serving communities with common surnames). Verify that the classifier cross-references PHN digits when available, even if partially redacted, to improve match accuracy.

---

## Case 2: Split Multi-Page Document Losing Context Between Pages

**Affected Dimensions:** Document Processing, Fax Handling, Clinical Completeness

**Severity:** High

**Scenario:**
A specialist sends a 6-page consultation report via fax. The fax arrives at Ava's inbound fax queue and is processed by the document classifier. Pages 1-3 contain the patient demographics, reason for referral, and examination findings. Pages 4-6 contain the diagnosis, treatment plan, and follow-up recommendations. The classifier processes each page group independently (due to a page-splitting configuration that separates documents at detected page boundaries). Pages 1-3 are correctly classified as a specialist consultation and filed in the patient's chart. Pages 4-6, which lack patient demographics (they are a continuation), are classified as "Unknown Document Type" with no patient match and are routed to the clinic's general unclassified document queue. The physician reviews the filed consultation report and sees examination findings but no diagnosis or treatment plan.

**Why It's Hard to Catch:**
The page-splitting logic is designed to handle multi-document faxes (e.g., a pharmacy sending refill requests for multiple patients in a single fax). The splitter looks for page boundaries where demographics or document headers appear, and it treats a page without demographics as the start of a new document. For continuation pages within a single document, this heuristic fails. The physician sees a consultation report that appears complete at first glance (it has a header, patient info, and clinical content) and may not realize additional pages exist. The unclassified document queue accumulates orphaned pages that may not be reviewed for days or weeks.

**Impact:**
The physician reviewing an incomplete consultation report may make clinical decisions without the specialist's diagnosis or treatment recommendations. If the diagnosis section on pages 4-6 contains a cancer diagnosis or a recommendation to discontinue a medication, the missing pages represent a direct patient safety risk. The orphaned pages in the unclassified queue may be reviewed by a staff member who lacks the clinical context to recognize their importance and may archive them as "junk fax" without further investigation.

**Test Approach:**
Send a multi-page fax where only the first page contains patient demographics. Verify that the classifier treats all pages as a single document when there is no new demographics header on subsequent pages. Test with varying page counts (2, 5, 10 pages) and verify document integrity. Verify that the risk analyzer flags clinics where the unclassified document queue exceeds a configurable threshold (e.g., more than 20 items older than 48 hours) as a potential indicator of split-document issues. Test that documents classified as consultation reports are checked for completeness indicators (e.g., presence of "Assessment" and "Plan" sections) and flagged as potentially incomplete when key sections are missing.

---

## Case 3: Low-Confidence Classification with No Manual Review Queue

**Affected Dimensions:** Document Classification, Workflow Configuration, Patient Safety

**Severity:** Critical

**Scenario:**
The document classifier processes an incoming lab result and assigns it a confidence score of 0.55 (below the auto-file threshold of 0.80 but above the rejection threshold of 0.30). The system is configured to route low-confidence documents to a manual review queue where a staff member verifies the classification and patient match before filing. However, during clinic setup, the manual review queue was not configured -- the workflow endpoint for low-confidence documents points to a queue that does not exist in the clinic's task management system. The document is sent to the nonexistent queue and effectively disappears. No error is logged because the queue routing uses an asynchronous fire-and-forget pattern.

**Why It's Hard to Catch:**
The queue reference is a configuration string (e.g., `queue://clinic-123/doc-review`) that is not validated against existing queues at configuration time. The integration uses asynchronous messaging, so the sending system receives an acknowledgment from the message broker (confirming delivery to the topic) even though no consumer exists for that topic. The document is technically "in the system" (sitting on an unconsumed message topic) but is invisible to all users. The clinic has no visibility into unconsumed messages because message broker monitoring is an infrastructure concern, not a clinical workflow concern. The issue only surfaces when a physician asks "where is my patient's lab result?" and no one can find it.

**Impact:**
A lost lab result can delay diagnosis and treatment. If the lab result is a critical value (e.g., dangerously elevated potassium, positive blood culture), the delay could be life-threatening. The physician who ordered the lab test will eventually follow up, but the time between when the result was available and when the physician discovers it is missing represents a window of patient risk. The clinic also faces regulatory exposure because provincial lab result management guidelines require that all results be reviewed by a physician within a specified timeframe, and a result lost in a nonexistent queue will never be reviewed.

**Test Approach:**
Configure a clinic without a manual review queue (or with an invalid queue reference). Send a document that triggers low-confidence classification. Verify that the system either (a) validates the queue reference at configuration time and blocks saving an invalid reference, or (b) detects the missing consumer at runtime and falls back to a default queue (e.g., the clinic admin's inbox). Test that the risk analyzer flags clinic configurations where the low-confidence review queue is unconfigured, points to a nonexistent endpoint, or has no active consumers. Verify that the system includes a "dead letter" monitoring alert that fires when documents are sent to queues with no active consumers for more than 1 hour.

---

## Case 4: Classifier Trained on AB Documents Applied to BC Formats

**Affected Dimensions:** Document Classification, Province Configuration, Model Training

**Severity:** Medium

**Scenario:**
Ava's document classifier model was trained primarily on Alberta clinical documents -- lab results from DynaLife and Calgary Lab Services, referral letters following AHS referral templates, and Alberta-format prescription records. A BC clinic onboards with Ava and begins receiving documents from LifeLabs (BC's primary lab provider), BC referral templates, and BC-format prescriptions. The classifier's accuracy drops significantly for BC documents because the document layouts, header formats, and field positions differ from the Alberta training data. LifeLabs results are misclassified as "insurance forms" (30% of the time) because the LifeLabs header layout resembles an insurance document layout in the AB training set. Referral letters from BC specialists are classified with low confidence and routed to manual review, overwhelming the review queue.

**Why It's Hard to Catch:**
The classifier's accuracy metrics are computed on the training/validation dataset, which is predominantly AB documents. The model reports 95%+ accuracy in the AB context, which is the number presented during onboarding. BC-specific accuracy is not measured because BC documents were not in the validation set. The clinic experiences the degraded accuracy as a gradual frustration (more manual review, occasional misroutes) rather than a sudden failure, and they may attribute it to "the system learning" rather than a training data gap. There is no province-specific accuracy dashboard or alert that would flag the performance discrepancy.

**Impact:**
A clinic experiencing 30% misclassification of lab results will quickly lose confidence in Ava's document management system. Staff will begin manually checking every incoming document rather than trusting the classification, negating the efficiency gains that the classifier is designed to provide. The overwhelmed manual review queue creates a backlog that delays all document processing, including time-sensitive results and referrals. The clinic may escalate the issue as a critical defect, consuming support resources and risking client retention.

**Test Approach:**
Run the classifier against a test corpus of BC-formatted documents (LifeLabs results, BC referral letters, BC prescription records) and measure accuracy compared to the AB document baseline. Verify that accuracy exceeds the minimum acceptable threshold (e.g., 0.85) for each document type in each province. Test that the risk analyzer flags clinics in provinces underrepresented in the classifier's training data and recommends a province-specific fine-tuning step during onboarding. Verify that the classifier's confidence scores are calibrated (a 0.90 confidence should mean 90% actual accuracy) across both AB and BC document formats. Test that the onboarding workflow includes a classifier accuracy benchmark against a sample of the clinic's actual incoming documents before go-live.
