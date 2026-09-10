import re
import unittest

import app as shelter_app


class ShelterAppTests(unittest.TestCase):
    def setUp(self):
        self.original_shelters = [dict(item) for item in shelter_app.shelters]
        shelter_app.shelters[:] = [
            {"id": 1, "name": "A", "capacity": 10, "current": 8},
            {"id": 2, "name": "B", "capacity": 20, "current": 0},
            {"id": 3, "name": "C", "capacity": 15, "current": 4},
        ]
        self.client = shelter_app.app.test_client()

    def tearDown(self):
        shelter_app.shelters[:] = self.original_shelters

    def get_shelter_names(self, html):
        rows = re.findall(r'<tr[^>]*>\s*<td[^>]*>(.*?)</td>', html, flags=re.DOTALL)
        return [row.strip() for row in rows]

    def test_search_results_sort_by_remaining_capacity_desc(self):
        response = self.client.get('/search_results?sort=remaining_desc')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get_shelter_names(html), ['B', 'C', 'A'])

    def test_shelter_search_page_has_search_controls_and_results(self):
        response = self.client.get('/shelter_search')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('避難所検索', html)
        self.assertIn('避難所を選んだ基準の順に表示します', html)
        self.assertIn('name="conditions"', html)
        self.assertIn('最も重視する条件', html)
        self.assertIn('A', html)
        self.assertIn('B', html)
        self.assertIn('C', html)

    def test_shelter_search_keeps_sort_and_district_params(self):
        response = self.client.get('/shelter_search?sort=occupancy&district=A')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('value="occupancy"', html)
        self.assertIn('name="district"', html)
        self.assertIn('避難所検索', html)

    def test_full_shelters_are_not_hidden_from_search_results(self):
        shelter_app.shelters[0] = {"id": 1, "name": "A", "capacity": 10, "current": 10}

        response = self.client.get('/search_results?sort=remaining_desc')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get_shelter_names(html), ['B', 'C', 'A'])

    def test_search_results_show_remaining_rate_and_row_colors(self):
        response = self.client.get('/search_results?sort=remaining_desc')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('残り空き率', html)
        self.assertIn('20%', html)
        self.assertIn('100%', html)
        self.assertIn('73%', html)

    def test_search_results_page_has_map_section(self):
        response = self.client.get('/search_results?sort=remaining_desc')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('shelterMap', html)
        self.assertIn('leaflet', html)

    def test_shelter_register_accepts_capacity_and_current(self):
        with self.client.session_transaction() as session:
            session['logged_in'] = True

        response = self.client.post(
            '/shelter_register',
            data={
                'name': 'D',
                'capacity': '13',
                'current': '5',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('D', response.get_data(as_text=True))
        self.assertEqual(shelter_app.shelters[-1]['capacity'], 13)
        self.assertEqual(shelter_app.shelters[-1]['current'], 5)

    def test_shelter_register_assigns_default_coordinates(self):
        with self.client.session_transaction() as session:
            session['logged_in'] = True

        self.client.post(
            '/shelter_register',
            data={
                'name': 'E',
                'capacity': '9',
                'current': '1',
            },
        )

        self.assertIn('lat', shelter_app.shelters[-1])
        self.assertIn('lng', shelter_app.shelters[-1])
        self.assertIsInstance(shelter_app.shelters[-1]['lat'], float)
        self.assertIsInstance(shelter_app.shelters[-1]['lng'], float)

    def test_shelter_register_does_not_show_registered_list(self):
        with self.client.session_transaction() as session:
            session['logged_in'] = True

        response = self.client.get('/shelter_register')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('登録済み避難所一覧', html)

    def test_shelter_register_warns_when_current_exceeds_capacity(self):
        with self.client.session_transaction() as session:
            session['logged_in'] = True

        response = self.client.post(
            '/shelter_register',
            data={
                'name': 'D',
                'capacity': '10',
                'current': '11',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn('受け入れ人数が受け入れ可能人数を上回っています。', response.get_data(as_text=True))

    def test_login_redirect_uses_relative_next_path(self):
        response = self.client.get('/shelter_register', follow_redirects=False)

        self.assertEqual(response.status_code, 302)
        self.assertIn('/login?next=/shelter_register', response.location)

    def test_board_page_is_public(self):
        response = self.client.get('/board')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('発信ボード', html)
        self.assertIn('B避難所へ避難してください', html)


if __name__ == '__main__':
    unittest.main()
