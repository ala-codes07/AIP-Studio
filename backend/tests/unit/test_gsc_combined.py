"""Unit tests for the narrowly scoped GSC + audit insights patch.

The test rows are fabricated for verification; real GSC exports are never
bundled into the distributable patch.
"""
import unittest
from app.services.search_console import opportunities, parse_queries_csv


class CombinedInsightsTests(unittest.TestCase):
    def test_arabic_headers_and_metrics(self):
        raw = ('أهم طلبات البحث,النقرات,عدد الظهور,نسبة النقر إلى الظهور,موضع\n'
               'تولید کننده میکروسمنت,0,131,0%,38.51\n'
               'میکروسمنت عاج,4,4,100%,1\n').encode('utf-8-sig')
        result = parse_queries_csv(raw)
        self.assertEqual(result['row_count'], 2)
        self.assertEqual(result['total_impressions'], 135)
        self.assertEqual(result['total_clicks'], 4)

    def test_no_pages_never_invents_landing_url(self):
        rows = [{'query': 'قیمت میکروسمنت', 'clicks': 0, 'impressions': 100, 'ctr': 0., 'position': 65.}]
        result = opportunities(rows)[0]
        self.assertIsNone(result['matched_page'])
        self.assertEqual(result['page_match_confidence'], 'none')
        self.assertIn('actual landing URL', result['recommendation'])
        self.assertIn('pricing', result['recommendation'])

    def test_strong_candidate_is_labelled_inference_not_gsc_fact(self):
        rows = [{'query': 'تولید کننده میکروسمنت', 'clicks': 0, 'impressions': 131, 'ctr': 0., 'position': 38.5}]
        page = {'url': 'https://example.com/', 'title': 'تولیدکننده میکروسمنت',
                'h1': ['تولید کننده میکروسمنت'], 'word_count': 120,
                'description': 'فروش میکروسمنت', 'h2': []}
        finding = {'page_url': page['url'], 'title': 'Missing meta description',
                   'severity': 'medium', 'rule': 'missing_description',
                   'recommendation': 'Write an accurate summary.'}
        result = opportunities(rows, [page], [finding])[0]
        self.assertEqual(result['page_match_confidence'], 'strong_candidate')
        self.assertEqual(result['matched_page'], page['url'])
        self.assertIn('NOT a verified GSC landing page', result['recommendation'])
        self.assertIn('Missing meta description', result['recommendation'])
        self.assertEqual(result['position'], 38.5)
        self.assertEqual(result['impressions'], 131)

    def test_ambiguous_pages_are_not_presented_as_matched(self):
        rows = [{'query': 'میکروسمنت', 'clicks': 0, 'impressions': 92, 'ctr': 0., 'position': 52.7}]
        pages = [{'url': f'https://example.com/{i}', 'title': 'میکروسمنت',
                  'h1': ['میکروسمنت'], 'description': '', 'h2': []} for i in range(2)]
        result = opportunities(rows, pages)[0]
        self.assertEqual(result['page_match_confidence'], 'ambiguous')
        self.assertIsNone(result['matched_page'])
        self.assertIn('No uniquely supported landing-page match', result['recommendation'])

    def test_small_sample_does_not_trigger_optimistic_ctr_fix(self):
        rows = [{'query': 'میکروسمنت', 'clicks': 0, 'impressions': 5, 'ctr': 0., 'position': 7.5}]
        result = opportunities(rows)[0]
        self.assertEqual(result['type'], 'Low sample')
        self.assertIn('date window', result['recommendation'])


if __name__ == '__main__':
    unittest.main()
