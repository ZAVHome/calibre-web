# -*- coding: utf-8 -*-

#  This file is part of the Calibre-Web (https://github.com/janeczku/calibre-web)
#    Copyright (C) 2018 lemmsh, cervinko, OzzieIsaacs
#
#  This program is free software: you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation, either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program. If not, see <http://www.gnu.org/licenses/>.

import os
import base64
import zipfile
from lxml import etree

from .constants import BookMeta
from . import isoLanguages, cover, logger

log = logger.create()

# Safe parser: disable entity resolution and network access to prevent XXE attacks
_safe_parser = etree.XMLParser(resolve_entities=False, no_network=True, recover=True)


def get_fb2_info(tmp_file_path, original_file_extension, no_cover=False):
    ns = {
        'fb': 'http://www.gribuser.ru/xml/fictionbook/2.0',
        'l': 'http://www.w3.org/1999/xlink',
    }

    content = None
    if zipfile.is_zipfile(tmp_file_path):
        try:
            with zipfile.ZipFile(tmp_file_path, 'r') as z:
                for name in z.namelist():
                    if name.lower().endswith('.fb2'):
                        content = z.read(name)
                        break
        except Exception as e:
            log.warning('Could not read zip container for FB2: %s', e)

    if content is None:
        with open(tmp_file_path, 'rb') as f:
            content = f.read()

    try:
        tree = etree.fromstring(content, parser=_safe_parser)
    except Exception as e:
        log.warning('Failed to parse FB2 XML: %s', e)
        return BookMeta(
            file_path=tmp_file_path,
            extension=original_file_extension,
            title=os.path.splitext(os.path.basename(tmp_file_path))[0],
            author='Unknown',
            cover=None,
            description='',
            tags='',
            series='',
            series_id='',
            languages='',
            publisher='',
            pubdate='',
            identifiers=[]
        )

    # 1. Authors
    authors = tree.xpath('//fb:description/fb:title-info/fb:author', namespaces=ns)
    if not authors:
        authors = tree.xpath('//*[local-name()="description"]/*[local-name()="title-info"]/*[local-name()="author"]')

    def get_author(element):
        def _get_txt(path):
            res = element.xpath(path, namespaces=ns)
            if not res:
                res = element.xpath(f'*[local-name()="{path.split(":")[-1]}"]')
            return res[0].text.strip() if (res and res[0].text) else ''

        last_name = _get_txt('fb:last-name')
        first_name = _get_txt('fb:first-name')
        middle_name = _get_txt('fb:middle-name')
        nickname = _get_txt('fb:nickname')

        parts = [p for p in (first_name, middle_name, last_name) if p]
        if parts:
            return ' '.join(parts)
        return nickname or ''

    author_list = [get_author(a) for a in authors if get_author(a)]
    author = ' & '.join(author_list) if author_list else 'Unknown'

    # 2. Title
    title_nodes = tree.xpath('//fb:description/fb:title-info/fb:book-title/text()', namespaces=ns)
    if not title_nodes:
        title_nodes = tree.xpath('//*[local-name()="book-title"]/text()')
    title = str(title_nodes[0]).strip() if title_nodes else os.path.splitext(os.path.basename(tmp_file_path))[0]

    # 3. Description (Annotation)
    desc_nodes = tree.xpath('//fb:description/fb:title-info/fb:annotation', namespaces=ns)
    if not desc_nodes:
        desc_nodes = tree.xpath('//*[local-name()="title-info"]/*[local-name()="annotation"]')
    description = ''
    if desc_nodes:
        desc_parts = []
        for child in desc_nodes[0]:
            try:
                desc_parts.append(etree.tostring(child, encoding='unicode', method='html').strip())
            except Exception:
                if child.text:
                    desc_parts.append(f'<p>{child.text.strip()}</p>')
        description = ''.join(desc_parts) if desc_parts else (desc_nodes[0].text or '').strip()

    # 4. Series & Series Index
    seq_nodes = tree.xpath('//fb:description/fb:title-info/fb:sequence', namespaces=ns)
    if not seq_nodes:
        seq_nodes = tree.xpath('//*[local-name()="title-info"]/*[local-name()="sequence"]')
    series = ''
    series_id = '1'
    if seq_nodes:
        series = seq_nodes[0].get('name', '').strip()
        series_id = seq_nodes[0].get('number', '1').strip() or '1'

    # 5. Language
    lang_nodes = tree.xpath('//fb:description/fb:title-info/fb:lang/text()', namespaces=ns)
    if not lang_nodes:
        lang_nodes = tree.xpath('//*[local-name()="title-info"]/*[local-name()="lang"]/text()')
    languages = ''
    if lang_nodes:
        raw_lang = lang_nodes[0].strip().split('-')[0].lower()
        try:
            languages = isoLanguages.get_lang3(raw_lang)
        except Exception:
            languages = raw_lang

    # 6. Tags / Genres
    genre_nodes = tree.xpath('//fb:description/fb:title-info/fb:genre/text()', namespaces=ns)
    if not genre_nodes:
        genre_nodes = tree.xpath('//*[local-name()="title-info"]/*[local-name()="genre"]/text()')
    tags = ', '.join([g.strip() for g in genre_nodes if g.strip()])

    # 7. Publisher and Date
    publisher_nodes = tree.xpath('//fb:description/fb:publish-info/fb:publisher/text()', namespaces=ns)
    publisher = publisher_nodes[0].strip() if publisher_nodes else ''

    date_nodes = tree.xpath('//fb:description/fb:title-info/fb:date/@value', namespaces=ns)
    if not date_nodes:
        date_nodes = tree.xpath('//fb:description/fb:title-info/fb:date/text()', namespaces=ns)
    pubdate = date_nodes[0].strip() if date_nodes else ''

    # 8. Cover extraction
    cover_file = None
    if not no_cover:
        cover_href_nodes = tree.xpath('//fb:description/fb:title-info/fb:coverpage/fb:image/@l:href', namespaces=ns)
        if not cover_href_nodes:
            cover_href_nodes = tree.xpath('//*[local-name()="coverpage"]/*[local-name()="image"]/@*[local-name()="href"]')

        if cover_href_nodes:
            cover_id = cover_href_nodes[0].lstrip('#')
            binary_nodes = tree.xpath(f'//fb:binary[@id="{cover_id}"]', namespaces=ns)
            if not binary_nodes:
                binary_nodes = tree.xpath(f'//*[local-name()="binary"][@id="{cover_id}"]')

            if binary_nodes and binary_nodes[0].text:
                try:
                    raw_b64 = binary_nodes[0].text.strip().encode('ascii')
                    img_data = base64.b64decode(raw_b64)
                    content_type = binary_nodes[0].get('content-type', '').lower()

                    ext = '.jpg'
                    if 'png' in content_type:
                        ext = '.png'
                    elif 'webp' in content_type:
                        ext = '.webp'

                    cover_file = cover.cover_processing(tmp_file_path, img_data, ext)
                except Exception as e:
                    log.warning('Failed to extract FB2 cover: %s', e)
                    cover_file = None

    return BookMeta(
        file_path=tmp_file_path,
        extension=original_file_extension,
        title=title,
        author=author,
        cover=cover_file,
        description=description,
        tags=tags,
        series=series,
        series_id=series_id,
        languages=languages,
        publisher=publisher,
        pubdate=pubdate,
        identifiers=[]
    )
