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
    as well as Russian DOS (CP866) and Windows (CP1251) encodings.
    """
    filename = zip_info.filename
    if zip_info.flag_bits & 0x800:
        return filename

    try:
        raw_bytes = filename.encode('cp437')
        # Try UTF-8 first
        try:
            return raw_bytes.decode('utf-8')
        except UnicodeDecodeError:
            pass
        # Try CP866 (classic Russian ZIP encoding)
        try:
            return raw_bytes.decode('cp866')
        except UnicodeDecodeError:
            pass
        # Try CP1251
        try:
            return raw_bytes.decode('cp1251')
        except UnicodeDecodeError:
            pass
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass

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

                # Ensure safe destination path inside target_dir (prevent Zip Slip)
                safe_name = "".join(c for c in base_name if c not in '<>:"/\\|?*')
                if not safe_name:
                    safe_name = f"book_{len(books) + 1}{ext.lower()}"

                dest_path = os.path.join(real_target_dir, safe_name)
                # Avoid filename collisions in multi-book archives
                counter = 1
                while os.path.exists(dest_path):
                    dest_path = os.path.join(real_target_dir, f"{root_name}_{counter}{ext.lower()}")
                    counter += 1

                # Safety check against path traversal
                if not os.path.abspath(dest_path).startswith(real_target_dir):
                    log.warning("Skipping malicious zip entry: %s", decoded_name)
                    continue

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
