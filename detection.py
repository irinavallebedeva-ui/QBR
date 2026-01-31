"""
detection.py — The analytical core. Three stages in one module:

    1. Noise filtering    — removes social/off-topic messages
    2. Signal extraction  — deterministic regex scan for action items and risks
    3. Resolution detection — cross-thread check for acknowledgements/completions

All cue lists and thresholds are configurable via config.py.
Zero LLM cost. Every flag carries a direct evidence snippet.
"""

import re

from email_parser import Email, Flag
import config


# ---------------------------------------------------------------------------
# 1. Noise filtering
# ---------------------------------------------------------------------------

def _is_noise(email: Email) -> bool:
    """
    Returns True if the email is social chatter / off-topic.
    Requires minimum keyword hits AND short message length —
    avoids false positives on work emails that mention 'lunch' in passing.
    """
    body_lower = email.body.lower()
    hits = sum(1 for pattern in config.NOISE_KEYWORDS if re.search(pattern, body_lower))
    word_count = len(email.body.split())
    return hits >= config.NOISE_MIN_HITS and word_count < config.NOISE_MAX_WORDS


def filter_noise(emails: list[Email]) -> tuple[list[Email], int]:
    """Filter noise from a list of emails. Returns (clean_emails, noise_count)."""
    clean: list[Email] = []
    noise_count = 0

    for email in emails:
        if _is_noise(email):
            noise_count += 1
        else:
            clean.append(email)

    return clean, noise_count


# ---------------------------------------------------------------------------
# 2. Signal extraction
# ---------------------------------------------------------------------------

def _get_snippet(body: str, match: re.Match) -> str:  # type: ignore[type-arg]
    """Extract a snippet around the matched pattern for evidence."""
    start = max(0, match.start() - 40)
    end = min(len(body), match.end() + 80)
    snippet = body[start:end].replace("\n", " ").strip()
    if len(snippet) > config.EVIDENCE_SNIPPET_LENGTH:
        snippet = snippet[:config.EVIDENCE_SNIPPET_LENGTH]
    return snippet


def _is_conditional(body_lower: str, match: re.Match) -> bool:
    """
    True if the cue match is neutralised by conditional framing.

    Examples that should NOT flag:
      "If there's any blocker, let me know."   ← open door, not a stated blocker
      "if there are any blockers, tell me"     ← same pattern

    The check: look backwards from the match for "if there" within 40 chars.
    This covers "if there's any blocker", "if there are any blockers", etc.
    """
    look_back = max(0, match.start() - 40)
    context = body_lower[look_back:match.start()]
    return bool(re.search(r"\bif there\b", context))


def extract_signals(emails: list[Email], project: str) -> list[Flag]:
    """
    Scan emails for action and risk candidates.
    One action flag and one risk flag per email maximum.
    Each flag carries a direct evidence snippet.
    """
    flags: list[Flag] = []

    for email in emails:
        body_lower = email.body.lower()

        # --- Action cues ---
        for pattern in config.ACTION_CUES:
            match = re.search(pattern, body_lower)
            if match:
                if _is_conditional(body_lower, match):
                    continue  # "if there's any blocker, let me know" — not a real request
                flags.append(Flag(
                    flag_type="UNRESOLVED_ACTION",
                    status="OPEN",
                    project=project,
                    source_file=email.source_file,
                    trigger_email_index=email.index_in_thread,
                    trigger_snippet=_get_snippet(email.body, match),
                    trigger_date=email.date,
                    matched_cues=[pattern],
                ))
                break  # one action flag per email

        # --- Risk cues ---
        for pattern in config.RISK_CUES:
            match = re.search(pattern, body_lower)
            if match:
                if _is_conditional(body_lower, match):
                    continue  # "if there's any blocker" — conditional, not a stated blocker
                flags.append(Flag(
                    flag_type="RISK_BLOCKER",
                    status="OPEN",
                    project=project,
                    source_file=email.source_file,
                    trigger_email_index=email.index_in_thread,
                    trigger_snippet=_get_snippet(email.body, match),
                    trigger_date=email.date,
                    matched_cues=[pattern],
                ))
                break  # one risk flag per email

    return flags


# ---------------------------------------------------------------------------
# 3. Resolution detection (cross-thread, project-level)
# ---------------------------------------------------------------------------

def _is_later(candidate: Email, flag: Flag) -> bool:
    """
    True if candidate email is strictly later than the flag's trigger email.

    Primary: compare by date (the only reliable cross-thread signal).
    Fallback: if both dates are None AND same file, fall back to index comparison.
    If dates are missing across different files, we cannot determine ordering —
    return True (conservative: let the resolution cue check run rather than silently skip).
    """
    if flag.trigger_date and candidate.date:
        return candidate.date > flag.trigger_date

    # both dates missing, same file → index is valid within one thread
    if flag.trigger_date is None and candidate.date is None:
        if candidate.source_file == flag.source_file:
            return candidate.index_in_thread > flag.trigger_email_index
        # different files, no dates → can't determine order, don't skip
        return True

    # one date present, one missing → can't compare reliably, don't skip
    return True


def _extract_keywords(text: str) -> set[str]:
    """
    Pull meaningful words from a snippet for overlap checking.
    Strips common short/stop words so that shared fluff like 'the', 'it',
    'please' doesn't count as a topical match.
    """
    stop = {
        "the", "a", "an", "is", "it", "to", "in", "on", "for", "and", "or",
        "but", "of", "with", "this", "that", "we", "i", "you", "he", "she",
        "hi", "thanks", "please", "thank", "ok", "okay", "yes", "no",
        "regards", "best", "sorry", "sure", "also", "as", "at", "by", "do",
        "if", "my", "not", "so", "up", "can", "will", "would", "could",
        "should", "have", "has", "had", "been", "be", "are", "was", "were",
        "get", "got", "just", "now", "then", "there", "here", "what", "how",
        "when", "which", "who", "its", "our", "your", "their", "me", "him",
        "her", "them", "us",
    }
    words = re.findall(r"[a-záéíóöőúüű]+", text.lower())
    return {w for w in words if len(w) > 2 and w not in stop}


def _has_topic_overlap(flag: Flag, email: Email, min_shared: int = 2) -> bool:
    """
    True if the flag's trigger snippet and the candidate email share enough
    meaningful keywords to plausibly be about the same topic.
    Used only for cross-file resolution candidates — same-file matches skip this.
    """
    trigger_kw = _extract_keywords(flag.trigger_snippet)
    email_kw = _extract_keywords(email.body)
    shared = trigger_kw & email_kw
    return len(shared) >= min_shared


def _is_corrected(resolution_email: Email, project_emails: list[Email]) -> bool:
    """
    True if a later email in the same thread contains a correction cue,
    meaning the resolution_email's intent was overridden.
    Example: Zsófia says "I'll uncheck it" but Anna replies "STOP, only
    modify the newsletter checkbox!" — the resolution is invalidated.
    """
    for email in project_emails:
        if email.source_file != resolution_email.source_file:
            continue
        if email.index_in_thread <= resolution_email.index_in_thread:
            continue
        body_lower = email.body.lower()
        for pattern in config.CORRECTION_CUES:
            if re.search(pattern, body_lower):
                return True
    return False


def _find_resolution(flag: Flag, project_emails: list[Email]) -> str | None:
    """
    Scan later emails in the same project for resolution signals.

    Two tiers of matching:
      • Same file: any resolution cue after the trigger index is valid.
        The email thread is one conversation — temporal ordering is sufficient.
      • Cross file: resolution cue must also share meaningful keyword overlap
        with the trigger snippet.  Prevents a generic "I'll do it" in an
        unrelated thread from resolving an unrelated flag.

    A flag can never resolve to the email that triggered it.
    """
    for email in project_emails:
        # never let a flag resolve to its own trigger email
        if (email.source_file == flag.source_file
                and email.index_in_thread == flag.trigger_email_index):
            continue

        if not _is_later(email, flag):
            continue

        # cross-file candidate: require topical overlap
        if email.source_file != flag.source_file:
            if not _has_topic_overlap(flag, email):
                continue

        body_lower = email.body.lower()
        for pattern in config.RESOLUTION_CUES:
            match = re.search(pattern, body_lower)
            if match:
                # before accepting: check if a later email in the same file
                # overrides/corrects this one (e.g. "STOP, that's wrong")
                if _is_corrected(email, project_emails):
                    break  # this candidate is invalidated, keep scanning
                start = max(0, match.start() - 40)
                end = min(len(email.body), match.end() + 80)
                snippet = email.body[start:end].replace("\n", " ").strip()
                return snippet

    return None


def detect_resolutions(
    flags: list[Flag],
    project_emails: dict[str, list[Email]]
) -> list[Flag]:
    """
    Run resolution detection on all flags.
    project_emails: project_name → list of all emails in that project.
    """
    for flag in flags:
        emails_in_project = project_emails.get(flag.project, [])
        resolution = _find_resolution(flag, emails_in_project)

        if resolution:
            flag.status = "RESOLVED"
            flag.resolution_snippet = resolution

    open_count = sum(1 for f in flags if f.status == "OPEN")
    resolved_count = sum(1 for f in flags if f.status == "RESOLVED")
    print(f"[Detection] {open_count} open, {resolved_count} resolved.")
    return flags
