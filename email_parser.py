"""
parser.py — Raw .txt email files → structured Email objects.

Responsibilities:
    - Read .txt files from an input directory (with path traversal guard)
    - Split multi-email threads into individual messages
    - Parse headers (From, To, Cc, Date, Subject)
    - Normalize timestamps and sender identity
    - Enforce input size limits (security)
    - Sort chronologically within each thread
    - Optionally load Colleagues.txt for role enrichment
"""

import hashlib
import os
import re
from dataclasses import dataclass, field
from datetime import datetime


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass
class Email:
    """Single parsed email message."""
    sender_name: str
    sender_email: str
    to: list[str]
    cc: list[str]
    date: datetime | None
    subject: str
    body: str
    source_file: str
    message_id: str = ""
    index_in_thread: int = 0


@dataclass
class Flag:
    """A detected issue — action item or risk/blocker."""
    flag_type: str                  # "UNRESOLVED_ACTION" | "RISK_BLOCKER"
    status: str                     # "OPEN" | "RESOLVED" | "FALSE_POSITIVE"
    project: str
    source_file: str
    trigger_email_index: int
    trigger_snippet: str            # evidence quote — never empty
    trigger_date: datetime | None = None  # timestamp of the triggering email
    resolution_snippet: str = ""
    matched_cues: list[str] = field(default_factory=list)
    # LLM-enriched fields (only populated when API key is provided)
    owner: str = ""
    priority: str = ""              # "HIGH" | "MEDIUM" | "LOW"
    llm_summary: str = ""
    confidence: str = ""


# ---------------------------------------------------------------------------
# Date parsing
# ---------------------------------------------------------------------------

DATE_FORMATS: list[str] = [
    "%a, %d %b %Y %H:%M:%S %z",   # Mon, 02 Jun 2025 10:00:00 +0200
    "%Y.%m.%d %H:%M",             # 2025.06.09 10:15
    "%Y-%m-%d %H:%M:%S",          # 2025-06-09 10:15:00
    "%Y-%m-%d %H:%M",             # 2025-06-09 10:15
    "%d %b %Y %H:%M:%S %z",       # 02 Jun 2025 10:00:00 +0200
    "%d/%m/%Y %H:%M",             # 02/06/2025 10:15
    "%m/%d/%Y %H:%M",             # 06/02/2025 10:15
    "%b %d, %Y %H:%M:%S",         # Jun 02, 2025 10:00:00
]


def _parse_date(raw: str) -> datetime | None:
    """Try known date formats. Returns None if unparseable."""
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(raw.strip(), fmt)
        except ValueError:
            continue
    return None


# ---------------------------------------------------------------------------
# Single email block parsing
# ---------------------------------------------------------------------------

def _make_message_id(sender: str, date_str: str, subject: str) -> str:
    """Hash-based message ID for deduplication."""
    raw = f"{sender}|{date_str}|{subject}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _extract_sender(raw_from: str) -> tuple[str, str]:
    """Extract (name, email) from a From: header value."""
    match = re.match(r"(.+?)\s*[<(]([^>)]+)[>)]", raw_from)
    if match:
        return match.group(1).strip(), match.group(2).strip()

    # fallback: try to find just an email address
    email_match = re.search(r"[\w.À-ž]+@[\w.]+", raw_from)
    email = email_match.group() if email_match else ""
    name = raw_from.split("<")[0].strip()
    return name, email


def _parse_single_block(block: str, source_file: str, index: int) -> Email | None:
    """Parse one email block into an Email object. Returns None if unparseable."""
    import config  # pylint: disable=import-outside-toplevel

    lines = block.strip().split("\n")
    headers: dict[str, str] = {}
    body_lines: list[str] = []
    in_body = False

    for line in lines:
        if in_body:
            body_lines.append(line)
            continue

        header_match = re.match(r"^(From|To|Cc|Date|Subject)\s*[:(]\s*(.*)", line, re.IGNORECASE)
        if header_match:
            headers[header_match.group(1).lower()] = header_match.group(2).strip()
        elif headers and not line.strip():
            in_body = True
        else:
            body_lines.append(line)

    if not headers:
        return None

    sender_name, sender_email = _extract_sender(headers.get("from", ""))

    # security: cap body length
    body = "\n".join(body_lines).strip()
    if len(body) > config.MAX_EMAIL_BODY_LENGTH:
        body = body[:config.MAX_EMAIL_BODY_LENGTH]

    date_raw = headers.get("date", "")

    return Email(
        sender_name=sender_name,
        sender_email=sender_email,
        to=[t.strip() for t in re.split(r"[,;]", headers.get("to", "")) if t.strip()],
        cc=[c.strip() for c in re.split(r"[,;]", headers.get("cc", "")) if c.strip()],
        date=_parse_date(date_raw),
        subject=headers.get("subject", ""),
        body=body,
        source_file=source_file,
        message_id=_make_message_id(sender_email, date_raw, headers.get("subject", "")),
        index_in_thread=index,
    )


# ---------------------------------------------------------------------------
# Thread parsing
# ---------------------------------------------------------------------------

def _parse_thread(raw_text: str, source_file: str) -> list[Email]:
    """Split a raw .txt file into individual emails, parse, sort chronologically."""
    # split on blank line followed by a header keyword
    blocks = re.split(r"\n\s*\n(?=(?:From|Subject|Date)\s*[:(])", raw_text)

    emails: list[Email] = []
    for i, block in enumerate(blocks):
        parsed = _parse_single_block(block, source_file, i)
        if parsed:
            emails.append(parsed)

    # sort chronologically; unparseable dates go to the end
    emails.sort(key=lambda e: e.date or datetime.max)
    for i, email in enumerate(emails):
        email.index_in_thread = i

    return emails


# ---------------------------------------------------------------------------
# Directory loading (with path traversal guard)
# ---------------------------------------------------------------------------

def load_emails(folder_path: str) -> list[Email]:
    """
    Read all .txt email files from a directory.
    Security: validates every path stays inside the input folder.
    """
    folder_path = os.path.realpath(folder_path)

    if not os.path.isdir(folder_path):
        print(f"[Parser] Warning: folder '{folder_path}' not found.")
        return []

    all_emails: list[Email] = []

    for fname in sorted(os.listdir(folder_path)):
        if not fname.endswith(".txt") or fname.lower() == "colleagues.txt":
            continue

        # security: path traversal guard
        full_path = os.path.realpath(os.path.join(folder_path, fname))
        if not full_path.startswith(folder_path):
            print(f"[Parser] BLOCKED: '{fname}' resolves outside input folder.")
            continue

        with open(full_path, "r", encoding="utf-8") as file:
            raw = file.read()

        all_emails.extend(_parse_thread(raw, fname))

    print(f"[Parser] Loaded {len(all_emails)} emails.")
    return all_emails


# ---------------------------------------------------------------------------
# Project grouping
# ---------------------------------------------------------------------------

def _normalize_subject(subject: str) -> str:
    """
    Stable fallback key from a subject line.
    Strips Re:/Fwd:, ticket IDs, dates → lowercase + collapse whitespace.
    Prevents accidental project fragmentation.
    """
    text = subject.strip()
    # strip Re: / Fwd: prefixes (handles nested)
    text = re.sub(r"^(?:Re|Fwd|FW|RE|FWD)\s*:\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^(?:Re|Fwd|FW|RE|FWD)\s*:\s*", "", text, flags=re.IGNORECASE)
    # strip ticket IDs (e.g. PROJ-42)
    text = re.sub(r"\b[A-Z]+-\d+\b", "", text)
    # strip dates
    text = re.sub(r"\b\d{4}[.\-/]\d{2}[.\-/]\d{2}\b", "", text)
    text = re.sub(
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\b",
        "", text
    )
    return " ".join(text.lower().split()).strip()


def _extract_project_name(subject: str) -> str | None:
    """Extract project name from 'ProjectName –' or 'ProjectName -' pattern."""
    match = re.match(
        r"^(?:Re\s*:\s*|Fwd\s*:\s*)*(.+?)\s*[-–]\s",
        subject.strip(),
        re.IGNORECASE
    )
    if match:
        candidate = match.group(1).strip()
        skip_words = {"re", "fwd", "fw", "subject", "urgent", "small"}
        if candidate.lower() not in skip_words and len(candidate) > 2:
            return candidate
    return None


def group_by_project(emails: list[Email]) -> dict[str, list[Email]]:
    """
    Group emails by project dynamically.
    Priority: 1) explicit name from subject  2) stable normalized subject fallback.
    """
    projects: dict[str, list[Email]] = {}

    for email in emails:
        project = _extract_project_name(email.subject)
        if not project:
            project = _normalize_subject(email.subject)
        if not project:
            project = "Unclassified"

        projects.setdefault(project, []).append(email)

    # sort within each project chronologically
    for project_name, project_list in projects.items():
        projects[project_name] = sorted(project_list, key=lambda e: e.date or datetime.max)

    print(f"[Parser] Grouped into {len(projects)} projects: {list(projects.keys())}")
    return projects


# ---------------------------------------------------------------------------
# Colleagues file (optional)
# ---------------------------------------------------------------------------

def load_colleagues(folder_path: str) -> dict[str, dict[str, str]]:
    """
    Load Colleagues.txt if it exists. Returns email → {name, role} map.
    Returns empty dict if file is missing or unparseable — graceful degradation.
    """
    filepath = os.path.join(folder_path, "Colleagues.txt")

    if not os.path.isfile(filepath):
        print("[Parser] No Colleagues.txt found — skipping role enrichment.")
        return {}

    role_map: dict[str, dict[str, str]] = {}
    try:
        with open(filepath, "r", encoding="utf-8") as file:
            for line in file:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue

                match = re.match(
                    r"^(.+?)\s*:\s*(.+?)\s*[<(]([\w.À-ž]+@[\w.]+)[>)]",
                    line
                )
                if match:
                    role = match.group(1).strip()
                    name = match.group(2).strip()
                    email = match.group(3).strip().lower()
                    role_map[email] = {"name": name, "role": role}

    except OSError as err:
        print(f"[Parser] Error reading Colleagues.txt: {err}")
        return {}

    print(f"[Parser] Loaded {len(role_map)} colleagues.")
    return role_map
