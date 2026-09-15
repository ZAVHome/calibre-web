#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Batch Library Importer for Calibre-Web.

Recursively scans a directory for books and archives (.zip, .fb2.zip, .fb2, .epub, .mobi, .pdf),
extracts metadata (including Russian genres, series, covers, descriptions),
detects duplicates with detailed file size comparisons,
imports into Calibre library (metadata.db + file storage),
and produces a comprehensive report.
"""

import os
import sys
import argparse
import tempfile
import shutil
import hashlib
import traceback
from datetime import datetime, timezone
from pathlib import Path

# Add project root to sys.path so we can import cps
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

SUPPORTED_ARCHIVES = {'.zip'}
SUPPORTED_DIRECT_BOOKS = {'.fb2', '.epub', '.kepub', '.mobi', '.azw', '.azw3', '.prc', '.pdf'}


def format_size(num_bytes):
    """Formats bytes into human-readable string (e.g. 1.4 MB)."""
    if num_bytes is None:
        return "N/A"
    try:
        num_bytes = float(num_bytes)
    except (ValueError, TypeError):
        return str(num_bytes)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:3.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"


def safe_str(s):
    """Safely converts string to clean display string, fixing any surrogate escapes from non-UTF8 filenames."""
    if not s:
        return ""
    s_val = str(s)
    if any(0xD800 <= ord(ch) <= 0xDFFF for ch in s_val):
        try:
            raw = s_val.encode('utf-8', errors='surrogateescape')
            for enc in ('cp1251', 'cp866', 'iso-8859-5'):
                try:
                    candidate = raw.decode(enc)
                    if not any(0xD800 <= ord(c) <= 0xDFFF for c in candidate):
                        return candidate
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass
        except Exception:
            pass
        return s_val.encode('utf-8', errors='replace').decode('utf-8', errors='replace')
    return s_val


def sanitize_meta(meta):
    """Ensures all string attributes in BookMeta are clean, valid UTF-8 strings without surrogate escapes."""
    if not meta:
        return meta
    clean_title = safe_str(meta.title or "").strip()
    clean_author = safe_str(meta.author or "").strip()
    if not clean_title:
        clean_title = "Unknown"
    if not clean_author:
        clean_author = "Unknown"

    return meta._replace(
        title=clean_title,
        author=clean_author,
        series=safe_str(meta.series or ""),
        series_id=safe_str(meta.series_id or ""),
        description=safe_str(meta.description or ""),
        tags=safe_str(meta.tags or ""),
        publisher=safe_str(meta.publisher or ""),
        languages=safe_str(meta.languages or "")
    )


def is_service_running(service_name="calibre-web"):
    """Checks if a systemd service is currently active."""
    try:
        import subprocess
        res = subprocess.run(
            ["systemctl", "is-active", "--quiet", service_name],
            capture_output=True
        )
        return res.returncode == 0
    except Exception:
        return False


def find_default_settings():
    """Tries to find Calibre-Web app.db in standard locations."""
    from cps.constants import CONFIG_DIR, DEFAULT_SETTINGS_FILE
    candidates = [
        os.path.join(CONFIG_DIR, DEFAULT_SETTINGS_FILE),
        os.path.expanduser("~/.calibre-web/app.db"),
        "/home/bookserver/.calibre-web/app.db",
        os.path.join(BASE_DIR, "app.db"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return None


def init_calibre_web(settings_path=None, calibre_dir=None):
    """Initializes Calibre-Web configuration and database connection."""
    from cps import app, cli_param, ub, config_sql, config, db
    from cps.cw_babel import babel, get_locale

    cli_param.logpath = ""
    cli_param.gd_path = ""
    cli_param.certfilepath = None
    cli_param.keyfilepath = None

    if settings_path:
        cli_param.settings_path = os.path.abspath(settings_path)
    else:
        found_settings = find_default_settings()
        if found_settings:
            cli_param.settings_path = found_settings

    if not cli_param.settings_path or not os.path.isfile(cli_param.settings_path):
        raise FileNotFoundError(
            f"Не найден файл настроек app.db! Укажите путь через параметр -p / --settings-path\n"
            f"Проверенные пути: {settings_path or 'стандартные пути ~/.calibre-web/app.db'}"
        )

    cli_param.gd_path = os.path.join(os.path.dirname(cli_param.settings_path), "gdrive.db")

    print(f"[*] Файл настроек: {cli_param.settings_path}")
    ub.init_db(cli_param.settings_path)
    encrypt_key, error = config_sql.get_encryption_key(os.path.dirname(cli_param.settings_path))
    if error:
        print(f"[!] Предупреждение шифрования: {error}")
    config_sql.load_configuration(ub.session, encrypt_key)
    config.init_config(ub.session, encrypt_key, cli_param)

    # Initialize LoginManager and authentication extensions
    from cps import lm
    import cps.usermanagement
    lm.login_view = 'web.login'
    lm.anonymous_user = ub.Anonymous
    lm.init_app(app)

    # Initialize Flask-Babel extension on app so uploader and gettext _() work
    app.secret_key = os.getenv('SECRET_KEY', config_sql.get_flask_session_key(ub.session))
    if 'babel' not in app.extensions:
        if hasattr(babel, "localeselector"):
            babel.init_app(app)
            babel.localeselector(get_locale)
        else:
            babel.init_app(app, locale_selector=get_locale)

    if calibre_dir:
        config.config_calibre_dir = os.path.abspath(calibre_dir)

    if not config.config_calibre_dir or not os.path.exists(config.config_calibre_dir):
        raise FileNotFoundError(
            f"Каталог библиотеки Calibre не найден: {config.config_calibre_dir}.\n"
            f"Укажите правильный путь через параметр -c / --calibre-dir"
        )

    metadata_path = os.path.join(config.config_calibre_dir, "metadata.db")
    if not os.path.isfile(metadata_path):
        raise FileNotFoundError(
            f"Файл metadata.db не найден в {config.config_calibre_dir}!"
        )

    print(f"[*] Каталог библиотеки Calibre: {config.config_calibre_dir}")
    db.CalibreDB.update_config(config, config.config_calibre_dir, cli_param.settings_path)
    return config


def import_single_book_to_db(meta, config, calibre_db, helper):
    """
    Imports a parsed BookMeta object into Calibre DB and moves file into library storage.
    Returns the created Books object.
    """
    from markupsafe import Markup
    from cps.editbooks import create_book_on_upload, edit_book_comments, move_coverfile

    modify_date = False
    calibre_db.create_functions(config)
    db_book, input_authors, title_dir = create_book_on_upload(modify_date, meta)

    # Save description / annotation
    if meta.description:
        modify_date |= edit_book_comments(Markup(meta.description).unescape(), db_book)

    book_id = db_book.id

    # Move book file into Calibre's folder structure: <Author>/<Title (id)>/<Title> - <Author>.<ext>
    error = helper.update_dir_structure(
        book_id,
        config.get_book_path(),
        input_authors[0],
        meta.file_path,
        title_dir + meta.extension.lower()
    )
    if error:
        raise RuntimeError(f"Не удалось переместить файл книги в библиотеку: {error}")

    # Move cover image if present
    move_coverfile(meta, db_book)

    if modify_date:
        calibre_db.set_metadata_dirty(book_id)

    calibre_db.session.commit()

    try:
        helper.add_book_to_thumbnail_cache(book_id)
    except Exception:
        pass

    return db_book


def generate_report_file(report_path, stats, errors, duplicates, added, args, config):
    """Writes a comprehensive text report of the import run."""
    with open(report_path, "w", encoding="utf-8", errors="replace") as f:
        f.write("=" * 80 + "\n")
        f.write("          ОТЧЁТ О ПАКЕТНОМ ИМПОРТЕ БИБЛИОТЕКИ В CALIBRE-WEB\n")
        f.write("=" * 80 + "\n")
        f.write(f"Дата и время:         {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Каталог импорта:      {safe_str(args.import_dir)}\n")
        f.write(f"Каталог библиотеки:   {safe_str(config.config_calibre_dir)}\n")
        f.write(f"Режим:                {'DRY-RUN (без записи в базу)' if args.dry_run else 'Штатный импорт'}\n")
        f.write(f"Удаление исходников:  {'ВКЛЮЧЕНО (--delete-source)' if args.delete_source else 'ВЫКЛЮЧЕНО'}\n")
        f.write("-" * 80 + "\n\n")

        f.write("СТАТИСТИКА:\n")
        f.write(f"  Всего обнаружено файлов/архивов: {stats['total_source_files']}\n")
        f.write(f"  Всего обработано книг:           {stats['total_books_processed']}\n")
        f.write(f"  Успешно добавлено в библиотеку:  {len(added)}\n")
        f.write(f"  Пропущено дубликатов:            {len(duplicates)}\n")
        f.write(f"  Ошибок при обработке:            {len(errors)}\n\n")

        # ОШИБКИ
        f.write("=" * 80 + "\n")
        f.write(f"СПИСОК ОШИБОК ({len(errors)})\n")
        f.write("=" * 80 + "\n")
        if not errors:
            f.write("Ошибок не обнаружено.\n\n")
        else:
            for idx, err in enumerate(errors, start=1):
                f.write(f"{idx}. Файл: {safe_str(err.get('source_file'))}\n")
                if err.get('book_title'):
                    f.write(f"   Книга: {safe_str(err.get('book_author', 'Неизвестен'))} — {safe_str(err.get('book_title'))}\n")
                f.write(f"   Этап: {err.get('stage')}\n")
                f.write(f"   Причина: {safe_str(err.get('error'))}\n")
                if err.get('traceback'):
                    f.write(f"   Подробности:\n")
                    for line in err['traceback'].strip().splitlines():
                        f.write(f"     {safe_str(line)}\n")
                f.write("\n")

        # ДУБЛИКАТЫ
        f.write("=" * 80 + "\n")
        f.write(f"СПИСОК ДУБЛИКАТОВ ({len(duplicates)})\n")
        f.write("=" * 80 + "\n")
        if not duplicates:
            f.write("Дубликатов не обнаружено.\n\n")
        else:
            for idx, dup in enumerate(duplicates, start=1):
                f.write(f"{idx}. Книга: {safe_str(dup['author'])} — {safe_str(dup['title'])}\n")
                if dup.get('series'):
                    f.write(f"   Серия: {safe_str(dup['series'])}\n")
                f.write(f"   Источник: {safe_str(dup['source_file'])}\n")
                f.write(f"   Новый файл:       Формат {dup['new_format']}, размер {dup['new_size_str']} ({dup['new_size_bytes']} байт)\n")
                
                # Существующие форматы в библиотеке
                existing_fmts = dup.get('existing_formats', [])
                if existing_fmts:
                    for ef in existing_fmts:
                        f.write(f"   В библиотеке #{dup['existing_id']}: Формат {ef['format']}, размер {ef['size_str']} ({ef['size_bytes']} байт)\n")
                        diff_bytes = dup['new_size_bytes'] - ef['size_bytes']
                        if diff_bytes == 0:
                            f.write(f"   Сравнение:        Размеры полностью совпадают\n")
                        elif diff_bytes > 0:
                            f.write(f"   Сравнение:        Новый файл БОЛЬШЕ на {format_size(diff_bytes)} (+{diff_bytes} байт)\n")
                        else:
                            f.write(f"   Сравнение:        Новый файл МЕНЬШЕ на {format_size(abs(diff_bytes))} (-{abs(diff_bytes)} байт)\n")
                else:
                    f.write(f"   В библиотеке: ID #{dup['existing_id']} (форматы не найдены)\n")
                f.write("\n")

        # ДОБАВЛЕННЫЕ КНИГИ
        f.write("=" * 80 + "\n")
        f.write(f"УСПЕШНО ДОБАВЛЕННЫЕ КНИГИ ({len(added)})\n")
        f.write("=" * 80 + "\n")
        if not added:
            f.write("Новых книг не добавлено.\n\n")
        else:
            for idx, item in enumerate(added, start=1):
                f.write(f"{idx}. [ID #{item.get('id', 'NEW')}] {safe_str(item['author'])} — {safe_str(item['title'])}\n")
                if item.get('series'):
                    f.write(f"   Серия: {safe_str(item['series'])}\n")
                if item.get('genres'):
                    f.write(f"   Жанры: {safe_str(item['genres'])}\n")
                f.write(f"   Формат: {item['format']}, Размер: {item['size_str']}\n")
                f.write(f"   Источник: {safe_str(item['source_file'])}\n\n")


def scan_source_directory(import_dir):
    """Scans directory recursively and groups files into archives and direct book files."""
    files_to_process = []
    for root, _, files in os.walk(import_dir):
        for f in files:
            ext = os.path.splitext(f)[1].lower()
            if ext in SUPPORTED_ARCHIVES or ext in SUPPORTED_DIRECT_BOOKS:
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, import_dir)
                files_to_process.append((full_path, rel_path, ext))
    files_to_process.sort(key=lambda x: x[1].lower())
    return files_to_process


def main():
    parser = argparse.ArgumentParser(
        description="Пакетный импорт книг и архивов в Calibre-Web с контролем дубликатов и размеров файлов.",
        prog="import_library.py"
    )
    parser.add_argument("import_dir", help="Каталог с книгами/архивами для импорта (например /home/bookserver/import)")
    parser.add_argument("-p", "--settings-path", help="Путь к app.db Calibre-Web (по умолчанию ищется в ~/.calibre-web/app.db)")
    parser.add_argument("-c", "--calibre-dir", help="Путь к библиотеке Calibre с metadata.db (если отличается от app.db)")
    parser.add_argument("--delete-source", action="store_true", help="Удалять исходный архив/файл после успешного импорта всех книг")
    parser.add_argument("--dry-run", action="store_true", help="Тестовый прогон: сканирование и вывод без записи в базу и перемещения файлов")
    parser.add_argument("--force", action="store_true", help="Продолжить работу даже если служба calibre-web запущена")
    parser.add_argument("--report-file", help="Путь к файлу отчёта (по умолчанию: import_report_<timestamp>.txt)")

    args = parser.parse_args()

    import_dir = os.path.abspath(args.import_dir)
    if not os.path.isdir(import_dir):
        print(f"[!] Ошибка: Каталог импорта не существует: {import_dir}")
        sys.exit(1)

    # Проверка службы calibre-web
    if not args.dry_run and is_service_running("calibre-web"):
        print("\n" + "!" * 70)
        print("ВНИМАНИЕ: Служба 'calibre-web' сейчас ЗАПУЩЕНА!")
        print("Во избежание блокировок SQLite (database is locked) рекомендуется")
        print("остановить службу на время импорта:")
        print("    sudo systemctl stop calibre-web")
        print("!" * 70 + "\n")
        if not args.force:
            try:
                answer = input("Продолжить импорт несмотря на работающую службу? [y/N]: ").strip().lower()
            except EOFError:
                answer = "n"
            if answer not in ["y", "yes", "да"]:
                print("Импорт отменён. Остановите службу и запустите скрипт снова.")
                sys.exit(0)

    # Инициализация Calibre-Web
    try:
        config = init_calibre_web(args.settings_path, args.calibre_dir)
    except Exception as e:
        print(f"[!] Ошибка инициализации: {e}")
        traceback.print_exc()
        sys.exit(1)

    from cps import app, calibre_db, helper, uploader, archive_helper
    from cps.binary_helper import resolve_binary_path, SUPPORTED_UNRAR_BINARIES
    rar_executable = resolve_binary_path(config.config_rarfile_location, SUPPORTED_UNRAR_BINARIES)

    # Поиск файлов
    print(f"[*] Сканирование каталога {import_dir}...")
    source_files = scan_source_directory(import_dir)
    total_files = len(source_files)
    print(f"[*] Найдено подходящих файлов/архивов: {total_files}")

    if total_files == 0:
        print("[!] В указанном каталоге не найдено поддерживаемых книг или архивов (.zip, .fb2, .epub, etc.)")
        sys.exit(0)

    # Подготовка отчёта
    timestamp_str = datetime.now().strftime('%Y%m%d_%H%M%S')
    report_file_path = args.report_file or os.path.join(os.getcwd(), f"import_report_{timestamp_str}.txt")

    stats = {
        'total_source_files': total_files,
        'total_books_processed': 0,
    }
    errors = []
    duplicates = []
    added = []

    print("\n" + "=" * 70)
    print("НАЧАЛО ИМПОРТА" if not args.dry_run else "НАЧАЛО ТЕСТОВОГО ПРОГОНА (DRY-RUN)")
    print("=" * 70 + "\n")

    # Выполняем в контексте Flask приложения
    with app.app_context(), app.test_request_context():
        from flask import g
        from cps import constants, ub
        try:
            admin_user = ub.session.query(ub.User).filter(ub.User.role.op('&')(constants.ROLE_ADMIN) == constants.ROLE_ADMIN).first()
            g._login_user = admin_user if admin_user else ub.Anonymous()
        except Exception:
            try:
                g._login_user = ub.Anonymous()
            except Exception:
                pass
        for file_idx, (full_path, rel_path, ext) in enumerate(source_files, start=1):
            file_error_count = 0
            books_in_file_count = 0

            # ----------------------------------------------------
            # Обработка ZIP архива
            # ----------------------------------------------------
            if ext in SUPPORTED_ARCHIVES:
                temp_extract_dir = tempfile.mkdtemp(prefix="cw_imp_zip_")
                try:
                    try:
                        extracted_books = archive_helper.extract_books_from_zip(full_path, temp_extract_dir)
                    except Exception as e:
                        file_error_count += 1
                        error_entry = {
                            'source_file': safe_str(rel_path),
                            'book_title': None,
                            'book_author': None,
                            'stage': 'zip_extraction',
                            'error': str(e),
                            'traceback': traceback.format_exc()
                        }
                        errors.append(error_entry)
                        print(f"[{file_idx}/{total_files}] [ОШИБКА АРХИВА] {safe_str(rel_path)}: {e}")
                        continue

                    if not extracted_books:
                        print(f"[{file_idx}/{total_files}] [ПРОПУСК] {safe_str(rel_path)}: Нет поддерживаемых книг в архиве")
                        continue

                    for book_item in extracted_books:
                        stats['total_books_processed'] += 1
                        books_in_file_count += 1
                        inner_rel = safe_str(f"{rel_path} -> {book_item.filename}{book_item.extension}")

                        try:
                            meta = uploader.process(
                                book_item.path,
                                safe_str(book_item.filename),
                                safe_str(book_item.extension),
                                rar_executable=rar_executable
                            )
                            meta = sanitize_meta(meta)

                            new_size = os.path.getsize(book_item.path)
                            new_size_str = format_size(new_size)
                            new_format = book_item.extension.upper().lstrip('.')

                            # Проверка дубликата
                            existing_book = None
                            if meta.author and meta.title and meta.title.lower() != 'unknown':
                                existing_book = calibre_db.check_exists_book(meta.author, meta.title)
                            if existing_book:
                                existing_formats = []
                                for d in existing_book.data:
                                    existing_formats.append({
                                        'format': d.format,
                                        'size_bytes': d.uncompressed_size,
                                        'size_str': format_size(d.uncompressed_size),
                                        'name': safe_str(d.name)
                                    })

                                duplicates.append({
                                    'title': safe_str(meta.title),
                                    'author': safe_str(meta.author),
                                    'series': safe_str(f"{meta.series} #{meta.series_id}") if meta.series else "",
                                    'source_file': inner_rel,
                                    'new_format': new_format,
                                    'new_size_bytes': new_size,
                                    'new_size_str': new_size_str,
                                    'existing_id': existing_book.id,
                                    'existing_formats': existing_formats
                                })

                                # Форматируем сравнение размеров для консоли
                                fmts_str = ", ".join(f"{ef['format']}: {ef['size_str']}" for ef in existing_formats)
                                print(f"[{file_idx}/{total_files}] [ДУБЛИКАТ] {safe_str(meta.author)} — {safe_str(meta.title)}")
                                print(f"         В библиотеке #{existing_book.id}: [{fmts_str}]")
                                print(f"         Новый файл:          [{new_format}: {new_size_str}] ({inner_rel})")
                                continue

                            # Импорт книги (или dry-run)
                            series_str = f" ({safe_str(meta.series)} #{meta.series_id})" if meta.series else ""
                            genres_str = f" [{safe_str(meta.tags)}]" if meta.tags else ""
                            if args.dry_run:
                                added.append({
                                    'id': 'DRY-RUN',
                                    'title': safe_str(meta.title),
                                    'author': safe_str(meta.author),
                                    'series': series_str.strip(" ()"),
                                    'genres': safe_str(meta.tags),
                                    'format': new_format,
                                    'size_str': new_size_str,
                                    'source_file': inner_rel
                                })
                                print(f"[{file_idx}/{total_files}] [DRY-RUN] {safe_str(meta.author)} — {safe_str(meta.title)}{series_str}{genres_str} [{new_format}: {new_size_str}]")
                            else:
                                db_book = import_single_book_to_db(meta, config, calibre_db, helper)
                                added.append({
                                    'id': db_book.id,
                                    'title': safe_str(db_book.title),
                                    'author': safe_str(meta.author),
                                    'series': series_str.strip(" ()"),
                                    'genres': safe_str(meta.tags),
                                    'format': new_format,
                                    'size_str': new_size_str,
                                    'source_file': inner_rel
                                })
                                print(f"[{file_idx}/{total_files}] [ДОБАВЛЕНО #{db_book.id}] {safe_str(meta.author)} — {safe_str(meta.title)}{series_str}{genres_str} [{new_format}: {new_size_str}]")
                        except Exception as e:
                            file_error_count += 1
                            calibre_db.session.rollback()
                            errors.append({
                                'source_file': inner_rel,
                                'book_title': safe_str(getattr(meta, 'title', None) if 'meta' in locals() else book_item.filename),
                                'book_author': safe_str(getattr(meta, 'author', None) if 'meta' in locals() else None),
                                'stage': 'book_processing',
                                'error': str(e),
                                'traceback': traceback.format_exc()
                            })
                            print(f"[{file_idx}/{total_files}] [ОШИБКА] {inner_rel}: {e}")

                finally:
                    # Очищаем временную папку распаковки архива
                    shutil.rmtree(temp_extract_dir, ignore_errors=True)

                # Удаление исходного архива, если запрошено и не было ошибок
                if args.delete_source and not args.dry_run:
                    if file_error_count == 0 and books_in_file_count > 0:
                        try:
                            os.unlink(full_path)
                            print(f"         [УДАЛЁН ИСХОДНИК] {safe_str(rel_path)}")
                        except OSError as ex:
                            print(f"         [ПРЕДУПРЕЖДЕНИЕ] Не удалось удалить {safe_str(rel_path)}: {ex}")

            # ----------------------------------------------------
            # Прямой файл книги (.fb2, .epub, .mobi, .pdf и т.д.)
            # ----------------------------------------------------
            else:
                stats['total_books_processed'] += 1
                base_name = os.path.basename(full_path)
                root_name, file_ext = os.path.splitext(base_name)
                safe_file_rel = safe_str(rel_path)

                # Создаем временную копию файла с безопасным именем
                temp_book_dir = tempfile.mkdtemp(prefix="cw_imp_file_")
                temp_book_path = os.path.join(temp_book_dir, f"source_book{file_ext.lower()}")
                try:
                    shutil.copyfile(full_path, temp_book_path)

                    try:
                        meta = uploader.process(
                            temp_book_path,
                            safe_str(root_name),
                            safe_str(file_ext),
                            rar_executable=rar_executable
                        )
                        meta = sanitize_meta(meta)

                        new_size = os.path.getsize(temp_book_path)
                        new_size_str = format_size(new_size)
                        new_format = file_ext.upper().lstrip('.')

                        # Проверка дубликата
                        existing_book = None
                        if meta.author and meta.title and meta.title.lower() != 'unknown':
                            existing_book = calibre_db.check_exists_book(meta.author, meta.title)
                        if existing_book:
                            existing_formats = []
                            for d in existing_book.data:
                                existing_formats.append({
                                    'format': d.format,
                                    'size_bytes': d.uncompressed_size,
                                    'size_str': format_size(d.uncompressed_size),
                                    'name': safe_str(d.name)
                                })

                            duplicates.append({
                                'title': safe_str(meta.title),
                                'author': safe_str(meta.author),
                                'series': safe_str(f"{meta.series} #{meta.series_id}") if meta.series else "",
                                'source_file': safe_file_rel,
                                'new_format': new_format,
                                'new_size_bytes': new_size,
                                'new_size_str': new_size_str,
                                'existing_id': existing_book.id,
                                'existing_formats': existing_formats
                            })

                            fmts_str = ", ".join(f"{ef['format']}: {ef['size_str']}" for ef in existing_formats)
                            print(f"[{file_idx}/{total_files}] [ДУБЛИКАТ] {safe_str(meta.author)} — {safe_str(meta.title)}")
                            print(f"         В библиотеке #{existing_book.id}: [{fmts_str}]")
                            print(f"         Новый файл:          [{new_format}: {new_size_str}] ({safe_file_rel})")
                            continue

                        # Импорт книги (или dry-run)
                        series_str = f" ({safe_str(meta.series)} #{meta.series_id})" if meta.series else ""
                        genres_str = f" [{safe_str(meta.tags)}]" if meta.tags else ""
                        if args.dry_run:
                            added.append({
                                'id': 'DRY-RUN',
                                'title': safe_str(meta.title),
                                'author': safe_str(meta.author),
                                'series': series_str.strip(" ()"),
                                'genres': safe_str(meta.tags),
                                'format': new_format,
                                'size_str': new_size_str,
                                'source_file': safe_file_rel
                            })
                            print(f"[{file_idx}/{total_files}] [DRY-RUN] {safe_str(meta.author)} — {safe_str(meta.title)}{series_str}{genres_str} [{new_format}: {new_size_str}]")
                        else:
                            db_book = import_single_book_to_db(meta, config, calibre_db, helper)
                            added.append({
                                'id': db_book.id,
                                'title': safe_str(db_book.title),
                                'author': safe_str(meta.author),
                                'series': series_str.strip(" ()"),
                                'genres': safe_str(meta.tags),
                                'format': new_format,
                                'size_str': new_size_str,
                                'source_file': safe_file_rel
                            })
                            print(f"[{file_idx}/{total_files}] [ДОБАВЛЕНО #{db_book.id}] {safe_str(meta.author)} — {safe_str(meta.title)}{series_str}{genres_str} [{new_format}: {new_size_str}]")
                    except Exception as e:
                        file_error_count += 1
                        calibre_db.session.rollback()
                        errors.append({
                            'source_file': safe_file_rel,
                            'book_title': safe_str(getattr(meta, 'title', None) if 'meta' in locals() else root_name),
                            'book_author': safe_str(getattr(meta, 'author', None) if 'meta' in locals() else None),
                            'stage': 'book_processing',
                            'error': str(e),
                            'traceback': traceback.format_exc()
                        })
                        print(f"[{file_idx}/{total_files}] [ОШИБКА] {safe_file_rel}: {e}")

                finally:
                    shutil.rmtree(temp_book_dir, ignore_errors=True)

                # Удаление исходного файла
                if args.delete_source and not args.dry_run:
                    if file_error_count == 0:
                        try:
                            os.unlink(full_path)
                            print(f"         [УДАЛЁН ИСХОДНИК] {safe_file_rel}")
                        except OSError as ex:
                            print(f"         [ПРЕДУПРЕЖДЕНИЕ] Не удалось удалить {safe_file_rel}: {ex}")

    # Генерация отчёта
    try:
        generate_report_file(report_file_path, stats, errors, duplicates, added, args, config)
    except Exception as e:
        print(f"\n[!] Не удалось сохранить отчёт в {report_file_path}: {e}")

    # Итоговый вывод
    print("\n" + "=" * 70)
    print("ИТОГИ ИМПОРТА" if not args.dry_run else "ИТОГИ ТЕСТОВОГО ПРОГОНА (DRY-RUN)")
    print("=" * 70)
    print(f"Всего проверено файлов/архивов: {stats['total_source_files']}")
    print(f"Всего обработано книг:          {stats['total_books_processed']}")
    print(f"Успешно добавлено в библиотеку: {len(added)}")
    print(f"Пропущено дубликатов:           {len(duplicates)}")
    print(f"Ошибок при обработке:           {len(errors)}")
    print("-" * 70)
    print(f"Подробный отчёт сохранён в файл:\n{report_file_path}")
    print("=" * 70 + "\n")


if __name__ == "__main__":
    main()
