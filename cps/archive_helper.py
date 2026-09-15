# -*- coding: utf-8 -*-

import os
import zipfile
import shutil
from collections import namedtuple
from . import logger

log = logger.create()

PRIMARY_BOOK_EXTENSIONS = {
    '.fb2', '.epub', '.kepub', '.mobi', '.azw', '.azw3', '.pdf',
    '.djvu', '.djv', '.cbr', '.cbz', '.cbt', '.cb7', '.prc',
    '.doc', '.docx', '.rtf', '.odt'
}

IGNORED_TEXT_BASENAMES = {
    'readme', 'read_me', 'info', 'about', 'url', 'links', 'link',
    'desc', 'description', 'license', 'copyright', 'file_id', 'contents'
}

SUPPORTED_BOOK_EXTENSIONS = PRIMARY_BOOK_EXTENSIONS | {'.txt'}

ExtractedBook = namedtuple('ExtractedBook', ['path', 'filename', 'extension'])


class ArchiveError(Exception):
    """Exception raised for errors during archive extraction."""
    pass


def is_zip_file(file_path):
    """Check if the given path is a valid zip file."""
    return zipfile.is_zipfile(file_path)


def decode_zip_filename(zip_info):
    """
    Decodes the filename in ZipInfo, taking into account UTF-8 flags,
    as well as Russian DOS (CP866) and Windows (CP1251) encodings,
    and removes any surrogate characters.
    """
    filename = zip_info.filename
    if not (zip_info.flag_bits & 0x800):
        try:
            raw_bytes = filename.encode('cp437')
            # Try UTF-8 first
            try:
                filename = raw_bytes.decode('utf-8')
            except UnicodeDecodeError:
                # Try CP866 (classic Russian ZIP encoding)
                try:
                    filename = raw_bytes.decode('cp866')
                except UnicodeDecodeError:
                    # Try CP1251
                    try:
                        filename = raw_bytes.decode('cp1251')
                    except UnicodeDecodeError:
                        pass
        except (UnicodeEncodeError, UnicodeDecodeError):
            pass

    # Heal or replace any lone surrogates in filename
    if any(0xD800 <= ord(c) <= 0xDFFF for c in filename):
        try:
            raw = filename.encode('utf-8', errors='surrogateescape')
            for enc in ('cp1251', 'cp866', 'iso-8859-5'):
                try:
                    candidate = raw.decode(enc)
                    if not any(0xD800 <= ord(c) <= 0xDFFF for c in candidate):
                        return candidate
                except (UnicodeDecodeError, UnicodeEncodeError):
                    pass
        except Exception:
            pass
        return filename.encode('utf-8', errors='replace').decode('utf-8', errors='replace')

    return filename


def is_junk_entry(filename):
    """Check if entry is OS-specific or junk file."""
    base = os.path.basename(filename)
    if base.startswith('.') or base.startswith('._'):
        return True
    if '__MACOSX' in filename:
        return True
    return False


def is_book_file(filename, has_primary_books=False):
    """Check if a filename has a supported ebook extension and is not junk/readme."""
    if is_junk_entry(filename):
        return False
    base = os.path.basename(filename)
    root, ext = os.path.splitext(base)
    ext_lower = ext.lower()

    if ext_lower in PRIMARY_BOOK_EXTENSIONS:
        return True

    if ext_lower == '.txt':
        # If real books exist in archive, or name is like readme/info, skip it
        if has_primary_books or root.lower() in IGNORED_TEXT_BASENAMES:
            return False
        return True

    return False


def extract_books_from_zip(zip_path, target_dir):
    """
    Scans a zip file and extracts all contained book files into target_dir.
    Returns a list of ExtractedBook namedtuples.
    Raises ArchiveError if archive is invalid or extraction fails.
    """
    if not zipfile.is_zipfile(zip_path):
        raise ArchiveError("File is not a valid zip archive")

    books = []
    real_target_dir = os.path.abspath(target_dir)

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            decoded_entries = []
            for info in zf.infolist():
                if info.is_dir():
                    continue
                dname = decode_zip_filename(info)
                if not is_junk_entry(dname):
                    decoded_entries.append((info, dname))

            has_primary_books = any(
                os.path.splitext(dname)[1].lower() in PRIMARY_BOOK_EXTENSIONS
                for _, dname in decoded_entries
            )

            for info, decoded_name in decoded_entries:
                if not is_book_file(decoded_name, has_primary_books=has_primary_books):
                    continue

                base_name = os.path.basename(decoded_name)
                root_name, ext = os.path.splitext(base_name)

                # Ensure safe destination path inside target_dir (clean ASCII, no Zip Slip or encoding issues)
                dest_path = os.path.join(real_target_dir, f"extracted_{len(books) + 1}{ext.lower()}")

                with zf.open(info) as src, open(dest_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)

                books.append(ExtractedBook(
                    path=dest_path,
                    filename=root_name,
                    extension=ext.lower()
                ))

    except zipfile.BadZipFile as e:
        raise ArchiveError(f"Bad zip file: {e}")
    except RuntimeError as e:
        if 'password' in str(e).lower():
            raise ArchiveError("Encrypted or password-protected zip archives are not supported")
        raise ArchiveError(f"Archive error: {e}")
    except Exception as e:
        raise ArchiveError(f"Failed to extract zip file: {e}")

    return books
