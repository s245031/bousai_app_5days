import json
import re
import pathlib
import unittest

import app as shelter_app


class ShelterAppTests(unittest.TestCase):
    def setUp(self):
        self.original_shelters = [dict(item) for item in shelter_app.shelters]
        self.original_instructions = [dict(item) for item in shelter_app.instructions]
        self.original_disaster_markers = [dict(item) for item in shelter_app.disaster_markers]
        self.original_instructions_file = pathlib.Path(shelter_app.INSTRUCTIONS_FILE).read_text(encoding='utf-8')
        self.original_disaster_markers_file = pathlib.Path(shelter_app.DISASTER_MARKERS_FILE).read_text(encoding='utf-8')
        shelter_app.shelters[:] = [
            {"id": 1, "name": "A", "capacity": 10, "current": 8},
            {"id": 2, "name": "B", "capacity": 20, "current": 0},
            {"id": 3, "name": "C", "capacity": 15, "current": 4},
        ]
        shelter_app.instructions[:] = [dict(item) for item in self.original_instructions]
        shelter_app.disaster_markers[:] = [dict(item) for item in self.original_disaster_markers]
        self.client = shelter_app.app.test_client()

    def tearDown(self):
        shelter_app.shelters[:] = self.original_shelters
        shelter_app.instructions[:] = self.original_instructions
        shelter_app.disaster_markers[:] = self.original_disaster_markers
        pathlib.Path(shelter_app.INSTRUCTIONS_FILE).write_text(self.original_instructions_file, encoding='utf-8')
        pathlib.Path(shelter_app.DISASTER_MARKERS_FILE).write_text(self.original_disaster_markers_file, encoding='utf-8')

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
        self.assertIn('検索ボタン', html)
        self.assertIn('name="conditions"', html)
        self.assertIn('最も重視する条件', html)
        self.assertIn('A', html)
        self.assertIn('B', html)
        self.assertIn('C', html)

    def test_search_results_honors_selected_conditions_order(self):
        response = self.client.get('/search_results?conditions=facilities,distance')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.get_shelter_names(html), ['C', 'B', 'A'])

    def test_parse_area_warnings_ignores_cleared_statuses(self):
        warning_data = [{
            "reportDatetime": "2026-09-10T12:00:00+09:00",
            "warning": {
                "class20Items": [{
                    "areaCode": "0220500",
                    "kinds": [{
                        "status": "解除",
                        "code": "00"
                    }]
                }]
            }
        }]

        warnings, _ = shelter_app.parse_area_warnings(warning_data)

        self.assertEqual(warnings, [])

    def test_shelter_search_uses_sort_param_without_district_field(self):
        response = self.client.get('/shelter_search?sort=occupancy&district=A')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('value="occupancy"', html)
        self.assertNotIn('name="district"', html)
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

    def test_board_page_uses_single_disaster_selection(self):
        response = self.client.get('/board')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertNotIn('name="icon"', html)
        self.assertIn('disasterPinPreview', html)
        self.assertIn('disaster-pin-drop-zone', html)
        self.assertIn('🌊 河川洪水', html)
        self.assertIn('⛰ 土砂災害', html)

    def test_board_page_has_instruction_input_toggle(self):
        response = self.client.get('/board')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('災害情報の入力', html)
        self.assertIn('発信情報の入力', html)
        self.assertIn('instructionContent', html)

    def test_home_page_defines_disaster_marker_style(self):
        response = self.client.get('/')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('.map-disaster-shape', html)

    def test_all_map_templates_include_disaster_inner_icon_markup(self):
        templates = [
            pathlib.Path('bousai_app/templates/index.html').read_text(encoding='utf-8'),
            pathlib.Path('bousai_app/templates/search_results.html').read_text(encoding='utf-8'),
            pathlib.Path('bousai_app/templates/shelter_search.html').read_text(encoding='utf-8'),
            pathlib.Path('bousai_app/templates/board.html').read_text(encoding='utf-8'),
        ]

        self.assertTrue(all('map-disaster-inner' in text for text in templates[:3]))
        self.assertIn('disaster-marker-inner', templates[3])

    def test_shelter_search_page_defines_disaster_marker_css(self):
        html = pathlib.Path('bousai_app/templates/shelter_search.html').read_text(encoding='utf-8')

        self.assertIn('.map-disaster-icon {', html)
        self.assertIn('.map-disaster-shape {', html)
        self.assertIn('.map-disaster-inner {', html)

    def test_all_map_templates_use_disaster_name_color_mapping(self):
        templates = [
            pathlib.Path('bousai_app/templates/index.html').read_text(encoding='utf-8'),
            pathlib.Path('bousai_app/templates/search_results.html').read_text(encoding='utf-8'),
            pathlib.Path('bousai_app/templates/shelter_search.html').read_text(encoding='utf-8'),
        ]

        self.assertTrue(all('function getDisasterColor(disasterName)' in html for html in templates))
        self.assertTrue(all('getDisasterScaleColor' not in html for html in templates))

    def test_api_instructions_creates_active_instruction(self):
        response = self.client.post(
            '/api/instructions',
            json={
                'content': '避難指示を出します',
                'district': '東地区',
                'shelter': '東小学校'
            }
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(shelter_app.instructions[-1]['content'], '避難指示を出します')
        self.assertEqual(shelter_app.instructions[-1]['district'], '東地区')
        self.assertEqual(shelter_app.instructions[-1]['target'], '住民')

    def test_disaster_markers_can_be_saved_publicly_and_loaded_for_other_maps(self):
        response = self.client.put(
            '/api/disaster_markers',
            json=[{
                'id': 1,
                'latitude': 40.8244,
                'longitude': 140.7400,
                'name': '河川洪水',
                'scale': '小規模',
                'datetime': '2026-09-10T12:00',
                'note': 'テスト用災害情報',
                'address': '青森市'
            }]
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(shelter_app.disaster_markers[0]['name'], '河川洪水')

        fetch_response = self.client.get('/api/disaster_markers')
        self.assertEqual(fetch_response.status_code, 200)
        payload = json.loads(fetch_response.get_data(as_text=True))
        self.assertEqual(payload[0]['name'], '河川洪水')

    def test_board_page_is_public(self):
        response = self.client.get('/board')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('発信ボード', html)
        self.assertIn('B避難所へ避難してください', html)


if __name__ == '__main__':
    unittest.main()
