"""Build the public site from explicitly curated data; stdlib only, no network."""
import json
import re
from html import escape
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
ALLOWED_HOSTS = {
    'scholar.google.com', 'github.com', 'dblp.org', 'arxiv.org',
    'eprint.iacr.org', 'www.vldb.org', 'doi.org', 'ieeexplore.ieee.org',
    'jianliu.phd',
}


def safe_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise ValueError('URL must be a string without whitespace')
    u = urlsplit(value)
    if u.scheme != 'https' or u.hostname not in ALLOWED_HOSTS or u.username or u.password:
        raise ValueError('Only explicitly allowlisted public HTTPS links are accepted')
    if u.port not in (None, 443):
        raise ValueError('Unexpected port')
    return escape(value, quote=True)


def validate(data):
    for key in ('name', 'name_zh', 'email', 'affiliation', 'role', 'research_tagline', 'description', 'updated'):
        if not isinstance(data.get(key), str) or not data[key].strip():
            raise ValueError(f'Missing text field: {key}')
    if not re.fullmatch(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}', data['email']):
        raise ValueError('Invalid public email')
    advisor = data.get('advisor', {})
    if not isinstance(advisor.get('label'), str) or not advisor['label'].strip():
        raise ValueError('Advisor needs a nonempty name')
    safe_url(advisor.get('url'))
    for key in ('bio', 'links', 'news', 'research', 'publications', 'experience', 'service'):
        if not isinstance(data.get(key), list) or not data[key]:
            raise ValueError(f'Missing collection: {key}')
    if any(not isinstance(p, str) for p in data['bio']):
        raise ValueError('Biography paragraphs must be text')
    ids = set()
    for p in data['publications']:
        if not re.fullmatch('[a-z][a-z0-9-]*', p['id']) or p['id'] in ids:
            raise ValueError('Duplicate or unsafe publication ID')
        ids.add(p['id'])
        if not re.fullmatch(r'20\d{2}', p['year']):
            raise ValueError('Invalid publication year')
        if data['name'] not in p['authors'] or not p['links']:
            raise ValueError('A selected publication needs an author and source link')
        if not set(p['equal'] + p['corresponding']).issubset(p['authors']):
            raise ValueError('Authorship marker does not match an author')
        for link in p['links']:
            safe_url(link['url'])
    for link in data['links']:
        safe_url(link['url'])


def link(item, arrow=False):
    suffix = '<span class="arrow" aria-hidden="true">↗</span>' if arrow else ''
    return f'<a href="{safe_url(item["url"])}" rel="noopener noreferrer">{escape(item["label"])}{suffix}</a>'


def publication(p, name):
    authors = []
    for author in p['authors']:
        text = escape(author)
        if author == name:
            text = f'<strong>{text}</strong>'
        if author in p['equal']:
            text += '<sup aria-label="equal contribution">*</sup>'
        if author in p['corresponding']:
            text += '<sup aria-label="corresponding author">†</sup>'
        authors.append(text)
    note = f'<span class="pub-note">{escape(p["note"])}</span>' if p['note'] else ''
    links = ''.join(link(item, arrow=True) for item in p['links'])
    return f'''<li class="publication" id="pub-{p['id']}">
      <p class="venue">{escape(p['venue'])}<span class="pub-year">{escape(p['year'])}</span>{note}</p>
      <div><h3 class="pub-title"><a href="{safe_url(p['links'][0]['url'])}">{escape(p['title'])}</a></h3>
      <p class="authors">{', '.join(authors)}</p>
      <div class="pub-links" aria-label="Resources for {escape(p['title'], quote=True)}">{links}</div></div>
    </li>'''


def advisor_text(text, advisor):
    """Link the advisor in prose without accepting raw HTML in the content."""
    return link(advisor).join(escape(part) for part in text.split(advisor['label']))


def render(data):
    validate(data)
    name = escape(data['name'])
    email = escape(data['email'], quote=True)
    biography = '\n'.join(f'<p class="bio">{advisor_text(p, data["advisor"])}</p>' for p in data['bio'])
    links = ''.join(link(item) for item in data['links'])
    news = '\n'.join(f'<div class="news-row"><time>{escape(n["date"])}</time><p>{escape(n["text"])}</p></div>' for n in data['news'])
    research = '\n'.join(f'<article><h3>{escape(r["title"])}</h3><p>{escape(r["text"])}</p></article>' for r in data['research'])
    publications = '\n'.join(publication(p, data['name']) for p in data['publications'])
    experience = '\n'.join(f'<article class="experience-item"><time>{escape(e["period"])}</time><h3>{escape(e["institution"])}</h3><p>{advisor_text(e["detail"], data["advisor"])}</p></article>' for e in data['experience'])
    service = '\n'.join(f'<article class="service-item"><h3>{escape(s["title"])}</h3><p>{escape(s["text"])}</p></article>' for s in data['service'])
    return f'''<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="{escape(data['description'], quote=True)}">
  <meta name="theme-color" content="#ffffff">
  <title>{name} | Data Security &amp; Privacy</title>
  <link rel="stylesheet" href="assets/style.css">
  <link rel="icon" href="assets/favicon.svg" type="image/svg+xml">
  <script defer src="https://cloud.umami.is/script.js" data-website-id="553f7ed7-708c-45b0-8aff-ea6aa9646c4f" data-domains="xinlecao.github.io" data-exclude-search="true" data-exclude-hash="true" data-do-not-track="true"></script>
</head>
<body>
  <a class="skip" href="#main">Skip to content</a>
  <header class="site-header">
    <div class="wrap header-inner">
      <a class="wordmark" href="#about">{name}</a>
      <nav aria-label="Main navigation">
        <a href="#about">About</a><a href="#research">Research</a>
        <a href="#publications">Publications</a><a href="#experience">Experience</a>
        <a href="#service">Service</a>
      </nav>
    </div>
  </header>
  <main class="wrap" id="main">
    <section class="profile" id="about" aria-labelledby="profile-title">
      <div class="profile-text">
        <p class="eyebrow">{escape(data['research_tagline'])}</p>
        <h1 id="profile-title">{name}<span class="name-zh" lang="zh-Hans">{escape(data['name_zh'])}</span></h1>
        <p class="position">{escape(data['role'])}</p>
        <p class="affiliation">{escape(data['affiliation'])}</p>
        {biography}
      </div>
      <aside class="profile-aside" aria-label="Profile photograph and academic links">
        <img class="portrait" src="assets/portrait.png" width="190" height="190" alt="Xinle Cao’s original profile photograph" fetchpriority="high">
        <div class="profile-links"><a class="email" href="mailto:{email}">{email}</a>{links}</div>
      </aside>
    </section>
    <section class="news" aria-labelledby="news-title">
      <h2 id="news-title">Recent updates</h2>
      {news}
    </section>
    <section class="section" id="research" aria-labelledby="research-title">
      <div class="section-heading"><h2 id="research-title">Research interests</h2></div>
      <div class="research-grid">{research}</div>
    </section>
    <section class="section" id="publications" aria-labelledby="publications-title">
      <div class="section-heading"><h2 id="publications-title">Selected publications</h2><p>* Equal contribution · † Corresponding author</p></div>
      <ol class="publications">{publications}</ol>
    </section>
    <div class="lower-grid">
      <section class="section" id="experience" aria-labelledby="experience-title">
        <div class="section-heading"><h2 id="experience-title">Experience &amp; education</h2></div>
        {experience}
      </section>
      <section class="section" id="service" aria-labelledby="service-title">
        <div class="section-heading"><h2 id="service-title">Academic service</h2></div>
        {service}
        <div class="service-item contact-note"><h3>Contact</h3><p>For research discussions and potential collaborations,<br><a href="mailto:{email}">{email}</a>.</p></div>
      </section>
    </div>
  </main>
  <footer class="site-footer"><div class="wrap footer-inner"><p>{name} · {escape(data['name_zh'])}</p><p>Last updated {escape(data['updated'])}</p></div></footer>
</body>
</html>
'''


def main():
    data = json.loads((ROOT / 'content/profile.json').read_text(encoding='utf-8'))
    html = render(data)
    for asset in ('portrait.png', 'style.css', 'favicon.svg'):
        if not (ROOT / 'site/assets' / asset).is_file():
            raise FileNotFoundError(f'Missing public asset: {asset}')
    (ROOT / 'site/index.html').write_text(html, encoding='utf-8')
    print(f'Built site/index.html with {len(data["publications"])} selected publications.')


if __name__ == '__main__':
    main()
