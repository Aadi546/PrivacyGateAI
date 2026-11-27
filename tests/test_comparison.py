import json
import time
import unittest
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from backend import comparison, disclosure, engine
from backend.main import app, receiver_app, SESSIONS, TOKEN, TTL


def extracted(*texts, **overrides):
    return {"lines": [{"text": text, "chars": []} for text in texts], "qr": "not_detected", "limitations": [], **overrides}


def pdf(text):
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((50, 50), text, fontsize=12)
        doc.set_metadata({})
        return doc.tobytes()


class DisclosureRulesTests(unittest.TestCase):
    def categories(self, *texts):
        return {item["id"] for item in comparison.inspect_lines(extracted(*texts))["categories"]}

    def test_positive_financial_evidence_without_raw_values(self):
        text = extracted("Name: Alex Sample, Address: 14 Cedar Lane", "Account number: 112233445566",
                         "Closing balance: INR 40,750.00", "Date Description Debit Credit", "2026-11-01 Taxi 1,250.00 0.00")
        result = comparison.inspect_lines(text)
        self.assertEqual({item["id"] for item in result["categories"]}, {"bank_account", "balance", "transactions"})
        self.assertNotIn("112233445566", json.dumps(result))
        self.assertNotIn("40,750.00", json.dumps(result))

    def test_blank_headings_masked_values_and_date_only_rows_are_not_disclosures(self):
        self.assertEqual(self.categories("Bank statement / synthetic demonstration", "Closing balance:",
                                        "Account number: XXXX XXXX 5566", "Date Description Debit Credit", "2026-11-01"), set())
        self.assertNotIn("transactions", self.categories("Date Description Amount", "2026-11-01 Taxi XXXX"))

    def test_name_address_and_document_title_are_not_scored(self):
        self.assertEqual(self.categories("Bank statement", "Name: Alex Sample", "Address: 14 Cedar Lane, Bengaluru 560001"), set())
        self.assertNotIn("aadhaar", self.categories("Account number: 112233445566"))
        self.assertNotIn("phone", self.categories("Consumer ID: 9876543210"))

    def test_qr_uncertain_ocr_and_limited_extraction_block_ranking(self):
        cases = [extracted("Some readable document content here", qr="detected"),
                 extracted("Some readable document content here", lines=[{"text":"Some readable document content here", "chars":[{"precise":False}]}]),
                 extracted("Some readable document content here", limitations=["Unsupported PDF structures: attachments"]),
                 extracted(""), extracted("यह एक परीक्षण दस्तावेज है जिसमें पता लिखा हुआ है")]
        for case in cases:
            with self.subTest(case=case):
                self.assertEqual(comparison.inspect_lines(case)["coverage"], "inconclusive")


class ComparisonAPITests(unittest.TestCase):
    def setUp(self):
        SESSIONS.clear(); disclosure.GRANTS.clear()
        self.client = TestClient(app, base_url="http://127.0.0.1:8765")
        self.receiver = TestClient(receiver_app, base_url="http://127.0.0.1:8766")
        self.headers = {"X-PrivacyGate-Token":TOKEN}

    def tearDown(self):
        self.client.close(); self.receiver.close()
        SESSIONS.clear(); disclosure.GRANTS.clear()

    def inspect(self, kind="bank", data=None, filename=None):
        if data is None:
            data, mime = disclosure.sample(kind)
        result = self.client.post('/api/analyze', headers=self.headers,
                                  files={"file":(filename or disclosure.SAMPLES[kind][0], data, "application/pdf")})
        self.assertEqual(result.status_code, 200, result.text)
        report = result.json()
        self.assertNotIn('_address_disclosure', report)
        return data, report

    def compare(self, reports, acceptance=("accepted", "accepted"), details=(True, True)):
        response = self.client.post('/api/practical/compare', headers=self.headers, json={"candidates":[
            {"session_id":report['session_id'], "acceptance":accepted, "required_details_confirmed":confirmed}
            for report, accepted, confirmed in zip(reports, acceptance, details)]})
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def test_synthetic_bank_vs_utility_recommends_utility_with_evidence(self):
        _, bank = self.inspect(); _, utility = self.inspect('utility')
        result = self.compare([bank, utility])
        self.assertEqual(result['status'], 'recommended')
        self.assertEqual(result['recommended_session_id'], utility['session_id'])
        self.assertIn('Financial balance', result['differences'][0]['unique_categories'])
        self.assertIn('Transaction history', result['differences'][0]['unique_categories'])
        for private in ('112233445566','40,750.00','alex.sample@example.com'):
            self.assertNotIn(private, json.dumps(result))

    def test_contents_determine_result_not_filename_or_document_type(self):
        _, bank = self.inspect(data=pdf('Bank statement\nName: Alex Sample\nAddress: 14 Cedar Lane\nAccount number: XXXX XXXX 5566'), filename='bank-statement.pdf')
        _, bill = self.inspect(data=pdf('Electricity bill\nName: Alex Sample\nAddress: 14 Cedar Lane\nAadhaar number: 2345 6789 0124'), filename='electricity-bill.pdf')
        result = self.compare([bank, bill])
        self.assertEqual(result['status'], 'recommended')
        self.assertEqual(result['recommended_session_id'], bank['session_id'])

    def test_tie_and_acceptance_declarations(self):
        _, left = self.inspect('utility'); _, right = self.inspect('utility')
        self.assertEqual(self.compare([left,right])['status'], 'tie')
        self.assertEqual(self.compare([left,right], ('unknown','unknown'))['status'], 'no_confirmed_option')
        self.assertEqual(self.compare([left,right], ('not_accepted','not_accepted'))['status'], 'no_confirmed_option')
        self.assertEqual(self.compare([left,right], details=(False,False))['status'], 'no_confirmed_option')
        single = self.compare([left,right], ('accepted','unknown'))
        self.assertEqual(single['status'], 'only_confirmed_option')
        self.assertEqual(single['recommended_session_id'], left['session_id'])
        self.assertIn('not a privacy winner', single['reason'])

    def test_incomplete_coverage_is_not_a_lower_disclosure_winner(self):
        _, left = self.inspect(); _, right = self.inspect('utility')
        SESSIONS[right['session_id']].report['_address_disclosure']['coverage'] = 'inconclusive'
        result = self.compare([left,right])
        self.assertEqual(result['status'], 'inconclusive')
        self.assertIsNone(result['recommended_session_id'])

    def test_private_unknown_and_duplicate_sessions_are_rejected(self):
        _, left = self.inspect(); _, right = self.inspect('utility')
        payload = {"candidates":[{"session_id":r['session_id']} for r in [left,right]]}
        self.assertEqual(self.client.post('/api/practical/compare',json=payload).status_code,401)
        payload['candidates'][1]['session_id'] = left['session_id']
        self.assertEqual(self.client.post('/api/practical/compare',headers=self.headers,json=payload).status_code,422)
        payload['candidates'][1]['session_id'] = 'missing-session'
        self.assertEqual(self.client.post('/api/practical/compare',headers=self.headers,json=payload).status_code,404)
        payload['candidates'][1]['session_id'] = right['session_id']
        payload['candidates'][0]['score'] = 0
        self.assertEqual(self.client.post('/api/practical/compare',headers=self.headers,json=payload).status_code,422)
        payload['candidates'][0].pop('score')
        SESSIONS[left['session_id']].touched = time.monotonic() - TTL - 1
        self.assertEqual(self.client.post('/api/practical/compare',headers=self.headers,json=payload).status_code,404)

    def test_comparison_and_clear_endpoint_invalidate_previous_output_and_grants(self):
        _, left = self.inspect(); _, right = self.inspect('utility')
        path = f"/api/practical/sessions/{left['session_id']}"
        protected = self.client.post(path+'/protect',headers=self.headers,json={'approved':True,'remove_metadata':True,'finding_ids':[]})
        self.assertEqual(protected.status_code,200,protected.text)
        grant = self.client.post(path+'/upload-approval',headers=self.headers,json={'approved':True,'variant':'output'}).json()
        self.compare([left,right])
        self.assertNotIn(grant['grant'],disclosure.GRANTS)
        self.assertEqual(self.client.get(path+'/download',headers=self.headers).status_code,409)
        self.client.post(path+'/protect',headers=self.headers,json={'approved':True,'remove_metadata':True,'finding_ids':[]})
        self.assertEqual(self.client.post(path+'/clear-protection',headers=self.headers,json={}).status_code,200)
        self.assertEqual(self.client.get(path+'/download',headers=self.headers).status_code,409)

    def test_chosen_candidate_protected_upload_rejects_other_candidate_bytes(self):
        bank_data, bank = self.inspect(); _, utility = self.inspect('utility')
        self.compare([bank,utility])
        path = f"/api/practical/sessions/{utility['session_id']}"
        ids = [finding['id'] for finding in utility['findings']]
        protected = self.client.post(path+'/protect',headers=self.headers,json={'approved':True,'remove_metadata':True,'finding_ids':ids})
        self.assertEqual(protected.status_code,200,protected.text)
        output = self.client.get(path+'/download',headers=self.headers).content
        def grant():
            return self.client.post(path+'/upload-approval',headers=self.headers,json={'approved':True,'variant':'output','mode':'cross_origin'}).json()
        first = grant()
        headers = {'Origin':'http://127.0.0.1:8765','X-PrivacyGate-Upload-Grant':first['grant']}
        self.assertEqual(self.receiver.post('/mock-upload',headers=headers,content=bank_data).status_code,400)
        second = grant(); headers['X-PrivacyGate-Upload-Grant'] = second['grant']
        response = self.receiver.post('/mock-upload',headers=headers,content=output)
        self.assertEqual(response.status_code,200,response.text)
        self.assertTrue(response.json()['matching_approved_file'])

    def test_signed_document_can_be_compared_but_not_modified(self):
        _, signed = self.inspect('signed'); _, utility = self.inspect('utility')
        result = self.compare([signed,utility])
        self.assertTrue(result['candidates'][0]['signature_indicator'])
        response = self.client.post(f"/api/practical/sessions/{signed['session_id']}/protect",headers=self.headers,
                                    json={'approved':True,'remove_metadata':True,'finding_ids':[]})
        self.assertEqual(response.status_code,422)

    def test_comparison_waits_for_document_processing(self):
        from backend.main import PROCESSING
        _, left = self.inspect(); _, right = self.inspect('utility')
        PROCESSING.acquire()
        try:
            response = self.client.post('/api/practical/compare',headers=self.headers,
                                        json={'candidates':[{'session_id':r['session_id']} for r in [left,right]]})
            self.assertEqual(response.status_code,409)
        finally:
            PROCESSING.release()
