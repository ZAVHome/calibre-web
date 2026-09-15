# -*- coding: utf-8 -*-

# Comprehensive mapping of FictionBook (FB2) genre codes to human-readable Russian names
FB2_GENRES = {
    # Фантастика
    'sf': 'Научная фантастика',
    'sci_sf': 'Научная фантастика',
    'sf_action': 'Боевая фантастика',
    'sf_cyberpunk': 'Киберпанк',
    'sf_detective': 'Детективная фантастика',
    'sf_epic': 'Эпическая фантастика',
    'sf_heroic': 'Героическая фантастика',
    'sf_history': 'Альтернативная история',
    'sci_history': 'Историческая фантастика',
    'sf_horror': 'Ужасы и мистика',
    'sf_humor': 'Юмористическая фантастика',
    'sf_postapocalyptic': 'Постапокалипсис',
    'sf_apocalyptic': 'Постапокалипсис',
    'sf_social': 'Социальная фантастика',
    'sf_space': 'Космическая фантастика',
    'sf_fantasy': 'Фэнтези',
    'sf_fantasy_city': 'Городское фэнтези',
    'sf_etc': 'Прочая фантастика',
    'sf_litrpg': 'ЛитРПГ',
    'fantasy': 'Фэнтези',
    'great_story': 'Эпическая фантастика',
    'popadanec': 'Попаданцы',
    'popadancy': 'Попаданцы',
    'popadantsy': 'Попаданцы',
    'litrpg': 'ЛитРПГ',
    'realrpg': 'РеалРПГ',
    'wuxia': 'Уся',
    'xianxia': 'Сянься',
    'steampunk': 'Стимпанк',
    'dystopia': 'Антиутопия',
    'dystopian': 'Антиутопия',
    'utopia': 'Утопия',
    'horror': 'Ужасы',
    'mystery': 'Мистика',
    'fairytale': 'Сказка',

    # Детективы и боевики
    'detective': 'Детектив',
    'det_action': 'Боевик',
    'action': 'Боевик',
    'det_classic': 'Классический детектив',
    'det_crime': 'Криминальный детектив',
    'det_hard': 'Крутой детектив',
    'det_history': 'Исторический детектив',
    'det_ironic': 'Иронический детектив',
    'det_police': 'Полицейский детектив',
    'det_political': 'Политический детектив',
    'det_maniac': 'Маньяки и триллер',
    'det_cozy': 'Уютный детектив',
    'det_su': 'Советский детектив',
    'thriller': 'Триллер',
    'thriller_legal': 'Юридический триллер',
    'thriller_medical': 'Медицинский триллер',
    'thriller_techno': 'Технотриллер',

    # Проза
    'prose': 'Проза',
    'prose_classic': 'Классическая проза',
    'prose_history': 'Историческая проза',
    'prose_contemporary': 'Современная проза',
    'prose_counter': 'Контркультура',
    'prose_rus_classic': 'Русская классика',
    'prose_su_classics': 'Советская классика',
    'prose_military': 'Военная проза',
    'prose_magic': 'Магический реализм',

    # Любовные романы
    'love': 'Любовные романы',
    'love_contemporary': 'Современные любовные романы',
    'love_history': 'Исторические любовные романы',
    'love_detective': 'Остросюжетные любовные романы',
    'love_short': 'Короткие любовные романы',
    'love_erotica': 'Эротика',
    'love_hard': 'Порнография',
    'love_sf': 'Любовно-фантастический роман',
    'erotica': 'Эротика',
    'ya': 'Подростковая литература',

    # Приключения
    'adventure': 'Приключения',
    'adv_western': 'Вестерн',
    'adv_history': 'Исторические приключения',
    'adv_indian': 'Приключения про индейцев',
    'adv_maritime': 'Морские приключения',
    'adv_geo': 'Географические приключения',
    'adv_animal': 'Природа и животные',

    # Детская литература
    'children': 'Детская литература',
    'child_tale': 'Сказки',
    'child_verse': 'Детские стихи',
    'child_prose': 'Детская проза',
    'child_sf': 'Детская фантастика',
    'child_det': 'Детские детективы',
    'child_adv': 'Детские приключения',
    'child_education': 'Детская образовательная литература',

    # Поэзия и драматургия
    'poetry': 'Поэзия',
    'dramaturgy': 'Драматургия',
    'humor': 'Юмор',
    'humor_prose': 'Юмористическая проза',
    'humor_verse': 'Юмористические стихи',
    'humor_satire': 'Сатира',

    # Наука и образование
    'science': 'Наука и образование',
    'sci_biology': 'Биология',
    'sci_juris': 'Юриспруденция',
    'sci_linguistic': 'Языкознание',
    'sci_math': 'Математика',
    'sci_medicine': 'Медицина',
    'sci_philosophy': 'Философия',
    'sci_politics': 'Политика',
    'sci_psychology': 'Психология',
    'sci_religion': 'Религиоведение',
    'sci_social': 'Обществознание',
    'sci_phys': 'Физика',
    'sci_chem': 'Химия',
    'sci_culture': 'Культурология',
    'sci_economy': 'Экономика',
    'sci_pedagogy': 'Педагогика',
    'computers': 'Компьютеры и интернет',
    'comp_programming': 'Программирование',
    'comp_hard': 'Компьютерное железо',
    'comp_soft': 'Программы',
    'comp_www': 'Интернет',
    'comp_db': 'Базы данных',
    'comp_osnet': 'Операционные системы и сети',

    # Справочники и нехудожественная литература
    'reference': 'Справочники',
    'ref_dict': 'Словари',
    'ref_encyc': 'Энциклопедии',
    'ref_ref': 'Справочники',
    'ref_guide': 'Руководства и путеводители',
    'nonfiction': 'Документальная литература',
    'nonf_biography': 'Биографии и мемуары',
    'nonf_publicism': 'Публицистика',
    'nonf_criticism': 'Критика',
    'nonf_military': 'Военная документалистика',
    'religion': 'Религия',
    'religion_rel': 'Религия',
    'religion_esoterics': 'Эзотерика',
    'religion_self': 'Самосовершенствование',

    # Домоводство и увлечения
    'home': 'Домоводство',
    'home_cooking': 'Кулинария',
    'home_pets': 'Домашние животные',
    'home_crafts': 'Хобби и ремёсла',
    'home_entertain': 'Развлечения',
    'home_health': 'Здоровье',
    'home_garden': 'Сад и огород',
    'home_diy': 'Сделай сам',
    'home_sport': 'Спорт',
    'home_sex': 'Семья и отношения',
}


def get_genre_name(code):
    """
    Translates an FB2 genre code to human-readable Russian genre name.
    If the code is already a human-readable name or unknown, returns it cleaned.
    """
    if not code:
        return ""
    code_str = str(code).strip()
    key = code_str.lower().replace('-', '_')
    if key in FB2_GENRES:
        return FB2_GENRES[key]
    return code_str
