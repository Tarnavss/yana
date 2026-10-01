"""Build standalone destination and collection pages from data files.

Run from any directory: python build_country_pages.py
The generated HTML opens locally, including through Google Drive for desktop.
"""

from __future__ import annotations

import html
import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ASSETS = ROOT / "assets"


def inline_markdown(value: str) -> str:
    escaped = html.escape(value)
    return re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)


def relative_path(start: Path, target: Path) -> str:
    return Path(os.path.relpath(target, start)).as_posix()


def seo_from_markdown(path: Path) -> str:
    """Use H2 for the first heading level in the supplied copy, H3 below it."""
    source = path.read_text(encoding="utf-8").strip()
    headings = re.findall(r"^(#{1,6}) ", source, re.M)
    first_level = min(map(len, headings)) if headings else 1
    blocks = re.split(r"\n\s*\n", source)
    result = []
    for block in blocks:
        block = block.strip()
        heading = re.fullmatch(r"(#{1,6}) (.+)", block)
        if heading:
            level = min(6, 2 + len(heading.group(1)) - first_level)
            result.append(f"<h{level}>{html.escape(heading.group(2))}</h{level}>")
        elif all(line.startswith("- ") for line in block.splitlines()):
            items = "".join(f"<li>{inline_markdown(line[2:])}</li>" for line in block.splitlines())
            result.append(f"<ul>{items}</ul>")
        else:
            result.append(f"<p>{inline_markdown(block)}</p>")
    return "\n".join(result)


def home_parts(brand: str, lang: str) -> tuple[str, str, str]:
    source = ROOT / brand / (lang if lang != "ru" else "") / "index.html"
    home = source.read_text(encoding="utf-8")
    header = re.search(r'<div class="white-label-bar">.*?</header>', home, re.S)
    footer = re.search(r'<footer class="footer".*?</footer>', home, re.S)
    partners = re.search(r'<section class="partners".*?</section>', home, re.S)
    if not header or not footer or not partners:
        raise ValueError(f"Missing shared page components in {source}")
    return header.group(), partners.group(), footer.group()


def build(data_file: Path, lang: str, brand: str, data_override: dict | None = None) -> Path:
    data = data_override or json.loads(data_file.read_text(encoding="utf-8"))
    content = data[lang]
    if data.get("parent_collection"):
        collection = json.loads((ROOT / "collection-data" / f'{data["parent_collection"]}.json').read_text(encoding="utf-8"))
        content = {**collection[lang], **content}
        content["title"] = f'{content["h1"]} | Yana Luxury Travel'
        content["description"] = f'{content["h1"]}. {content["subtitle"]}'
    brand_root = ROOT / brand
    folder = brand_root / (lang if lang != "ru" else "") / data["slug"]
    folder.mkdir(parents=True, exist_ok=True)
    asset_url = relative_path(folder, ASSETS)
    home_url = relative_path(folder, brand_root / (lang if lang != "ru" else "") / "index.html")
    header, partners, footer = home_parts(brand, lang)

    # Reuse existing header/footer markup; only update URLs for the deeper page.
    old_asset = "../assets" if lang == "ru" else "../../assets"
    partners = partners.replace(old_asset, asset_url)
    header = header.replace(old_asset, asset_url)
    footer = footer.replace(old_asset, asset_url)
    header = re.sub(r'href="(?:\.\./)*(?:en/|ua/)?index\.html"', 'href="__LANG_HOME__"', header)
    header = header.replace('href="__LANG_HOME__"', f'href="{home_url}"')
    header = re.sub(r'(<a class="brand" )href="#top"', rf'\1href="{home_url}"', header)
    header = re.sub(r'href="#(destinations|ideas|about)"', lambda m: f'href="{home_url}#{m.group(1)}"', header)
    # The language switcher stays on the same destination.
    language_links = {
        "ru": relative_path(folder, brand_root / data["slug"] / "index.html"),
        "ua": relative_path(folder, brand_root / "ua" / data["slug"] / "index.html"),
        "en": relative_path(folder, brand_root / "en" / data["slug"] / "index.html"),
    }
    header = re.sub(
        r'(<nav class="languages".*?</nav>)',
        lambda m: re.sub(
            r'(<a )href="[^"]+"( lang="(ru|uk|en)")',
            lambda a: f'{a.group(1)}href="{language_links[{"uk": "ua"}.get(a.group(3), a.group(3))]}"{a.group(2)}',
            m.group(1),
        ),
        header,
        flags=re.S,
    )
    header = re.sub(r' aria-current="page"', '', header)
    # Restore the active marker on the correct language link.
    html_lang = "uk" if lang == "ua" else lang
    header = header.replace(f'lang="{html_lang}">{lang.upper()}</a>', f'lang="{html_lang}" aria-current="page">{lang.upper()}</a>')
    footer = re.sub(r'(<a class="brand" )href="#top"', rf'\1href="{home_url}"', footer)

    e = html.escape
    seo_file = data_file.parent / f"{data['slug']}-{lang}.md"
    pending = not seo_file.exists()
    seo = seo_from_markdown(seo_file) if not pending else ("" if data.get("parent_collection") else '<p class="country-seo-pending">SEO text pending.</p>')
    ui = {
        "ru": ("Ваше имя", "Как к вам обращаться", "Телефон", "Макет формы: отправку заявки нужно подключить к сайту.", "Это предварительный макет. Для приёма заявок форму нужно подключить к сайту."),
        "ua": ("Ваше ім’я", "Як до вас звертатися", "Телефон", "Макет форми: надсилання заявки потрібно підключити до сайту.", "Це попередній макет. Для приймання заявок форму потрібно підключити до сайту."),
        "en": ("Your name", "How should we address you?", "Phone", "Form preview: submission must be connected to the site.", "This is a preview. The form must be connected before it can receive enquiries."),
    }[lang]
    back_label = {
        "ru": "На главную",
        "ua": "На головну",
        "en": "Back to home",
    }[lang]
    back_url = home_url
    if data.get("parent_collection"):
        parent = brand_root / (lang if lang != "ru" else "") / data["parent_collection"] / "index.html"
        back_url = relative_path(folder, parent)
        back_label = {"ru": "К Альпам", "ua": "До Альп", "en": "Back to the Alps"}[lang]
    title = content["title"].replace("Yana Luxury Travel", "Arway Travel") if brand == "arway" else content["title"]
    cards_html = ""
    if "images" in data:
        if len(data["images"]) != len(content["cards"]):
            raise ValueError(f"Card/image count mismatch in {data_file} ({lang})")
        slugs = data.get("card_slugs", [None] * len(data["images"]))
        if len(slugs) != len(data["images"]):
            raise ValueError(f"Card/slug count mismatch in {data_file}")
        cards = "\n".join(
            f'<a class="destination" href="{relative_path(folder, brand_root / (lang if lang != "ru" else "") / data["slug"] / slug / "index.html")}">'
            f'<img loading="lazy" src="{asset_url}/images/{e(image)}" alt="">'
            f'<div class="text"><h3>{e(name)}</h3></div></a>' if slug else
            f'<article class="destination"><img loading="lazy" src="{asset_url}/images/{e(image)}" alt="{e(name)}">'
            f'<div class="text"><h3>{e(name)}</h3></div></article>'
            for image, name, slug in zip(data["images"], content["cards"], slugs)
        )
        cards_html = (
            '<section class="section collection-destinations" aria-labelledby="collection-title"><div class="container">\n'
            f'<div class="section-head"><h2 id="collection-title">{e(content["collection_heading"])}</h2></div>\n'
            f'<div class="dest-grid">{cards}</div>\n'
            '</div></section>'
        )
    page = f'''<!doctype html>
<html lang="{html_lang}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{e(title)}</title>
  <meta name="description" content="{e(content['description'], quote=True)}">
  {('<meta name="robots" content="noindex">' if pending else '')}
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Cormorant+Garamond:wght@400&family=Roboto:wght@300;400;500&display=swap" rel="stylesheet">
  <link rel="stylesheet" href="{asset_url}/site.css">
  <link rel="stylesheet" href="{asset_url}/{brand}.css">
  <link rel="stylesheet" href="{asset_url}/country.css">
</head>
<body>
{header}
<main id="top">
  <section class="country-hero" aria-labelledby="country-title">
    <div class="country-hero-picture"><img src="{asset_url}/images/{e(data['image'])}" alt="" fetchpriority="high"></div>
    <div class="country-hero-shade"></div>
    <div class="container"><h1 id="country-title">{e(content['h1'])}</h1></div>
  </section>
  <section class="country-intro"><div class="container">
    <h2>{e(content['subtitle'])}</h2>
  </div></section>
  <section class="section contact country-contact" id="contact" aria-labelledby="contact-title"><div class="container">
    <div class="section-head"><h2 id="contact-title">{e(content['form_heading'])}</h2><p>{e(content['form_intro'])}</p></div>
    <form class="lead-form" id="lead-form"><label>{e(ui[0])}<input name="name" autocomplete="name" required placeholder="{e(ui[1])}"></label><label>{e(ui[2])}<input name="tel" type="tel" autocomplete="tel" required placeholder="+"></label><button class="button dark" type="submit">{e(content['form_button'])}</button></form>
    <p class="form-note" id="form-note">{e(ui[3])}</p>
  </div></section>
  {cards_html}
  <section class="country-seo" aria-label="SEO content"><div class="container country-seo-content">
    {seo}
    <div class="country-back"><a class="button dark" href="{back_url}">{e(back_label)}</a></div>
  </div></section>
  {partners}
</main>
{footer}
<script>
  const toggle=document.querySelector('.mobile-toggle'), menu=document.querySelector('.menu-wrap');
  toggle.addEventListener('click',()=>{{const open=menu.classList.toggle('open');toggle.setAttribute('aria-expanded',String(open));}});
  menu.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{{menu.classList.remove('open');toggle.setAttribute('aria-expanded','false');}}));
  document.querySelector('#lead-form').addEventListener('submit',e=>{{e.preventDefault();document.querySelector('#form-note').textContent={json.dumps(ui[4], ensure_ascii=False)};}});
</script>
</body>
</html>
'''
    target = folder / "index.html"
    target.write_text(page, encoding="utf-8")
    return target


if __name__ == "__main__":
    for data_file in sorted((*((ROOT / "country-data").glob("*.json")), *((ROOT / "collection-data").glob("*.json")))):
        for brand, languages in (("yana", ("ru", "ua", "en")), ("arway", ("ru", "en"))):
            for language in languages:
                print(build(data_file, language, brand))
    resort_file = ROOT / "resort-data" / "alps.json"
    for resort in json.loads(resort_file.read_text(encoding="utf-8"))["resorts"]:
        for brand, languages in (("yana", ("ru", "ua", "en")), ("arway", ("ru", "en"))):
            for language in languages:
                print(build(resort_file, language, brand, resort))
