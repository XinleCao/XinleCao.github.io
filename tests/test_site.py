import copy
import importlib.util
import json
import re
import subprocess
import unittest
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_site', ROOT / 'scripts/build_site.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class Elements(HTMLParser):
    def __init__(self):
        super().__init__()
        self.elements = []
    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class SiteTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / 'content/profile.json').read_text())
        self.html = builder.render(self.data)
        parser = Elements()
        parser.feed(self.html)
        self.elements = parser.elements

    def test_generated_page_is_current(self):
        self.assertEqual((ROOT / 'site/index.html').read_text(), self.html)

    def test_all_selected_work_is_server_rendered(self):
        self.assertEqual(len(self.data['publications']), 8)
        self.assertEqual(sum(t == 'li' and a.get('class') == 'publication' for t, a in self.elements), 8)
        self.assertIn('Accepted', self.html)
        self.assertIn('Database Technical Committee recommendation', self.html)
        self.assertNotIn('Under Submission', self.html)
        self.assertEqual(sum(t == 'h1' for t, a in self.elements), 1)

    def test_links_and_local_assets(self):
        ids = [a['id'] for t, a in self.elements if 'id' in a]
        self.assertEqual(len(ids), len(set(ids)))
        for tag, attrs in self.elements:
            for key in ('href', 'src'):
                if key not in attrs:
                    continue
                value = attrs[key]
                if value.startswith('#'):
                    self.assertIn(value[1:], ids)
                elif value.startswith(('https://', 'mailto:')):
                    continue
                else:
                    self.assertFalse(value.startswith('/'), 'Must work at a project URL prefix')
                    self.assertTrue((ROOT / 'site' / value).is_file(), value)

    def test_accessible_and_no_embedded_forms_or_dashboards(self):
        self.assertIn(('html', {'lang': 'en'}), self.elements)
        self.assertIn('width=device-width', self.html)
        for tag, attrs in self.elements:
            self.assertNotIn(tag, ('iframe', 'form'))
            if tag == 'img':
                self.assertTrue(attrs.get('alt'))
                self.assertTrue(attrs.get('width'))
                self.assertTrue(attrs.get('height'))
        self.assertIn('Skip to content', self.html)
        self.assertIn('prefers-reduced-motion', (ROOT / 'site/assets/style.css').read_text())

    def test_only_authorized_analytics_with_privacy_options(self):
        scripts = [a for tag, a in self.elements if tag == 'script']
        self.assertEqual(scripts, [{
            'defer': None,
            'src': 'https://cloud.umami.is/script.js',
            'data-website-id': '553f7ed7-708c-45b0-8aff-ea6aa9646c4f',
            'data-domains': 'xinlecao.github.io',
            'data-exclude-search': 'true',
            'data-exclude-hash': 'true',
            'data-do-not-track': 'true',
        }])
        self.assertNotIn('data-distinct-id', self.html)
        self.assertNotIn('umami.identify', self.html)
        self.assertNotIn('cloud.umami.is/share/', self.html)

    def test_public_file_allowlist(self):
        actual = {str(p.relative_to(ROOT / 'site')) for p in (ROOT / 'site').rglob('*') if p.is_file()}
        self.assertEqual(actual, {'index.html', '.nojekyll', 'assets/style.css', 'assets/portrait.png', 'assets/favicon.svg'})

    def test_public_repository_file_allowlist(self):
        if not (ROOT / '.git').exists():
            self.skipTest('Repository has not been initialized')
        paths = subprocess.check_output(['git', '-C', str(ROOT), 'ls-files', '-z']).decode().split('\0')
        self.assertEqual(set(filter(None, paths)), {
            '.gitignore', '.github/workflows/pages.yml', 'README.md',
            'content/profile.json', 'scripts/build_site.py', 'tests/test_site.py',
            'site/index.html', 'site/.nojekyll', 'site/assets/style.css',
            'site/assets/portrait.png', 'site/assets/favicon.svg',
        })

    def test_public_readme_is_minimal(self):
        self.assertEqual((ROOT / 'README.md').read_text(),
                         '# Xinle Cao\n\n[Homepage](https://xinlecao.github.io/)\n')

    def test_no_private_material_or_previous_personal_sections(self):
        for pattern in (r'/Users/', r'file://', r'tel:', r'WeChat', r'Recommended Videos', r'Friends', r'ghp_[A-Za-z0-9]+', r'github_pat_', r'Under Submission'):
            self.assertIsNone(re.search(pattern, self.html, re.IGNORECASE), pattern)

    def test_injection_is_escaped(self):
        data = copy.deepcopy(self.data)
        data['bio'][0] = '<img src=x onerror=alert(1)>'
        result = builder.render(data)
        self.assertIn('&lt;img src=x onerror=alert(1)&gt;', result)
        self.assertNotIn('<img src=x', result)

    def test_unsafe_links_rejected(self):
        for value in ('javascript:alert(1)', 'file:///private/document', 'https://github.com@evil.invalid/x', 'https://localhost/x', 'https://github.com/x\ny', 'https://github.com:8080/x'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                builder.safe_url(value)

    def test_bad_authorship_and_duplicate_ids_rejected(self):
        data = copy.deepcopy(self.data)
        data['publications'][0]['corresponding'] = ['Unknown author']
        with self.assertRaises(ValueError):
            builder.render(data)
        data = copy.deepcopy(self.data)
        data['publications'][1]['id'] = data['publications'][0]['id']
        with self.assertRaises(ValueError):
            builder.render(data)

    def test_empty_email_rejected(self):
        data = copy.deepcopy(self.data)
        data['email'] = ''
        with self.assertRaises(ValueError):
            builder.render(data)

    def test_advisor_links_and_email_unchanged(self):
        advisor_links = [a for t, a in self.elements if t == 'a' and a.get('href') == 'https://jianliu.phd/']
        self.assertEqual(len(advisor_links), 2)
        self.assertIn('advised by <a href="https://jianliu.phd/"', self.html)
        email_links = [a for t, a in self.elements if t == 'a' and a.get('href', '').startswith('mailto:')]
        self.assertEqual([a['href'] for a in email_links], ['mailto:xinle@zju.edu.cn'] * 2)

    def test_advisor_content_is_validated_and_escaped(self):
        data = copy.deepcopy(self.data)
        data['advisor']['url'] = 'javascript:alert(1)'
        with self.assertRaises(ValueError):
            builder.render(data)
        data['advisor'] = {'label': '', 'url': 'https://jianliu.phd/'}
        with self.assertRaises(ValueError):
            builder.render(data)
        result = builder.advisor_text('<b>Jian Liu</b>', self.data['advisor'])
        self.assertTrue(result.startswith('&lt;b&gt;<a '))
        self.assertTrue(result.endswith('</a>&lt;/b&gt;'))


if __name__ == '__main__':
    unittest.main()
