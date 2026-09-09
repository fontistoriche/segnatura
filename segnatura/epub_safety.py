"""Bounded access to untrusted EPUB ZIP members and XML structures."""
from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET
from xml.parsers import expat


EPUB_ENCRYPTION_PATH = "META-INF/encryption.xml"
FONT_OBFUSCATION_ALGORITHMS = frozenset({
    "http://www.idpf.org/2008/embedding",
    "http://ns.adobe.com/pdf/enc#RC",
})
FONT_EXTENSIONS = frozenset({".otf", ".ttf", ".woff", ".woff2"})


@dataclass(frozen=True)
class EpubSafetyLimits:
    """Resource limits applied while reading an EPUB.

    Images and other unreferenced binary resources are not decompressed by the
    extraction pipeline. ``max_total_read_bytes`` therefore limits the unique
    members Segnatura actually reads, not the advertised size of every asset in
    the archive.
    """

    max_members: int = 20_000
    max_member_bytes: int = 32 * 1024 * 1024
    max_total_read_bytes: int = 256 * 1024 * 1024
    max_xml_elements: int = 250_000
    max_xml_depth: int = 256
    max_path_characters: int = 1_024

    def __post_init__(self) -> None:
        for name, value in self.__dict__.items():
            if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"{name} must be a positive integer")


class EpubSafetyError(ValueError):
    """Raised when an EPUB exceeds a resource or structural safety boundary."""


class SafeEpubArchive:
    """Read ZIP members with path, size, decompression, and XML limits."""

    def __init__(self, archive: zipfile.ZipFile,
                 limits: EpubSafetyLimits | None = None):
        self.archive = archive
        self.limits = limits or EpubSafetyLimits()
        self._members: dict[str, zipfile.ZipInfo] = {}
        self._cache: dict[str, bytes] = {}
        self._validated_xml: set[str] = set()
        self._total_read = 0
        self._validate_directory()

    def _validate_directory(self) -> None:
        infos = self.archive.infolist()
        if len(infos) > self.limits.max_members:
            raise EpubSafetyError(
                f"archive contains {len(infos)} members; limit is "
                f"{self.limits.max_members}")

        for info in infos:
            name = info.filename
            if len(name) > self.limits.max_path_characters:
                raise EpubSafetyError(
                    f"archive member path exceeds "
                    f"{self.limits.max_path_characters} characters")
            if (not name or "\x00" in name or "\\" in name
                    or name.startswith("/") or re.match(r"^[A-Za-z]:", name)):
                raise EpubSafetyError(f"unsafe archive member path: {name!r}")
            parts = PurePosixPath(name).parts
            if ".." in parts:
                raise EpubSafetyError(f"unsafe archive member path: {name!r}")
            if name in self._members:
                raise EpubSafetyError(f"duplicate archive member: {name!r}")
            if info.flag_bits & 0x1:
                raise EpubSafetyError(
                    f"encrypted archive member is not supported: {name!r}")
            self._members[name] = info

    def names(self) -> tuple[str, ...]:
        return tuple(self._members)

    def read(self, name: str, *, xml: bool = False) -> bytes:
        info = self._members.get(name)
        if info is None or info.is_dir():
            raise KeyError(name)
        if info.file_size > self.limits.max_member_bytes:
            raise EpubSafetyError(
                f"archive member {name!r} advertises {info.file_size} bytes; "
                f"limit is {self.limits.max_member_bytes}")

        raw = self._cache.get(name)
        if raw is None:
            try:
                with self.archive.open(info, "r") as stream:
                    raw = stream.read(self.limits.max_member_bytes + 1)
            except (RuntimeError, zipfile.BadZipFile, OSError) as error:
                raise EpubSafetyError(
                    f"cannot safely decompress archive member {name!r}: "
                    f"{error}") from error
            if len(raw) > self.limits.max_member_bytes:
                raise EpubSafetyError(
                    f"archive member {name!r} exceeds "
                    f"{self.limits.max_member_bytes} decompressed bytes")
            if self._total_read + len(raw) > self.limits.max_total_read_bytes:
                raise EpubSafetyError(
                    "total decompressed data read by Segnatura exceeds "
                    f"{self.limits.max_total_read_bytes} bytes")
            self._total_read += len(raw)
            self._cache[name] = raw

        if xml and name not in self._validated_xml:
            self._validate_xml(name, raw)
            self._validated_xml.add(name)
        return raw

    def _validate_xml(self, name: str, raw: bytes) -> None:
        if re.search(rb"<!ENTITY\b", raw, re.IGNORECASE):
            raise EpubSafetyError(
                f"XML entity declarations are not allowed in {name!r}")
        count = 0
        depth = 0
        parser = expat.ParserCreate()

        def start_element(_name, _attributes) -> None:
            nonlocal count, depth
            count += 1
            depth += 1
            if count > self.limits.max_xml_elements:
                raise EpubSafetyError(
                    f"XML document {name!r} exceeds "
                    f"{self.limits.max_xml_elements} elements")
            if depth > self.limits.max_xml_depth:
                raise EpubSafetyError(
                    f"XML document {name!r} exceeds depth "
                    f"{self.limits.max_xml_depth}")

        def end_element(_name) -> None:
            nonlocal depth
            depth -= 1

        parser.StartElementHandler = start_element
        parser.EndElementHandler = end_element
        parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
        try:
            for offset in range(0, len(raw), 64 * 1024):
                parser.Parse(raw[offset:offset + 64 * 1024], False)
            parser.Parse(b"", True)
        except EpubSafetyError:
            raise
        except expat.ExpatError:
            # Existing lexical fallbacks remain available for malformed XHTML.
            # Container, OPF, and NCX parsing still fail explicitly at their
            # call sites because those documents have no safe lexical fallback.
            return


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in element.iter()
                 if _local_name(child.tag) == name), None)


def _short(value: str, limit: int = 200) -> str:
    return value if len(value) <= limit else value[:limit] + "..."


def _is_standard_font_obfuscation(algorithm: str, uri: str) -> bool:
    if algorithm not in FONT_OBFUSCATION_ALGORITHMS or not uri:
        return False
    path = unquote(urlsplit(uri).path)
    return PurePosixPath(path).suffix.casefold() in FONT_EXTENSIONS


def validate_publication_encryption(archive: SafeEpubArchive) -> None:
    """Reject encrypted publication resources but allow obfuscated fonts."""
    if EPUB_ENCRYPTION_PATH not in archive.names():
        return
    try:
        root = ET.fromstring(archive.read(EPUB_ENCRYPTION_PATH, xml=True))
    except ET.ParseError as error:
        raise EpubSafetyError(
            f"invalid {EPUB_ENCRYPTION_PATH}: {error}") from error

    for encrypted_data in root.iter():
        if _local_name(encrypted_data.tag) != "EncryptedData":
            continue
        method = _child(encrypted_data, "EncryptionMethod")
        reference = _child(encrypted_data, "CipherReference")
        algorithm = "" if method is None else method.get("Algorithm", "")
        uri = "" if reference is None else reference.get("URI", "")
        if _is_standard_font_obfuscation(algorithm, uri):
            continue
        resource = _short(uri) if uri else "unknown resource"
        method_name = _short(algorithm) if algorithm else "unknown algorithm"
        raise EpubSafetyError(
            "EPUB contains encrypted publication content that Segnatura "
            f"cannot extract: {resource!r} ({method_name})")
