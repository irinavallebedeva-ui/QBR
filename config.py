"""
config.py — All tunable parameters. Change behaviour here, nowhere else.
"""

# ---------------------------------------------------------------------------
# Action cues — regex patterns that signal a request, question, or task
# ---------------------------------------------------------------------------
ACTION_CUES: list[str] = [
    r"\bplease\b.*[\?!]",
    r"\bcan you\b",
    r"\bcould you\b",
    r"\bwe need\b",
    r"\bwhat.s the status\b",
    r"\bstill pending\b",
    r"\bany progress\b",
    r"\bany feedback\b",
    r"\bplease estimate\b",
    r"\bplease review\b",
    r"\bplease look into\b",
    r"\bplease investigate\b",
    r"\bplease take a look\b",
    r"\bplease help\b",
    r"\bplease create\b",
    r"\bplease ask\b",
    r"\blet me know\b",
    r"\bhas this been confirmed\b",
    r"\bwhat do you think\b",
    r"\bcan we\b.*\?",
    r"\bdo we need\b",
    r"\bhow should we\b",
    r"\bwhat should\b",
    r"\bstill open\b",
]

# ---------------------------------------------------------------------------
# Risk cues — regex patterns that signal blockers, scope changes, risks
# ---------------------------------------------------------------------------
RISK_CUES: list[str] = [
    r"\bnot included in the estimate\b",
    r"\bre-plan\b",
    r"\bextra effort\b",
    r"\bnot in the.*spec",
    r"\bnew requirement\b",
    r"\bscope\b",
    r"\bblocked\b|\bblocker\b",
    r"\bcan.t proceed\b",
    r"\bstuck\b",
    r"\burgent\b",
    r"\bgdpr\b",
    r"\bproduction\b.*\bfix\b",
    r"\bwrong environment variable\b",
    r"\bfaulty\b",
    r"\bplaceholder\b",
    r"\bnice to have\b",
    r"\bextra development\b",
    r"\bsidelined\b",
]

# ---------------------------------------------------------------------------
# Resolution cues — signals that an issue was addressed
# ---------------------------------------------------------------------------
RESOLUTION_CUES: list[str] = [
    r"\bfixed\b",
    r"\bresolved\b",
    r"\bdone\b",
    r"\bcompleted\b",
    r"\bworking (again|now)\b",
    r"\bit works\b",
    r"\bremoved from.*scope\b",
    r"\bwe can remove\b",
    r"\bcan go live\b",
    r"\bi.ll (fix|check|do|handle|implement|update|continue)\b",
    r"\bi.ve (fixed|pushed|enlarged|updated|closed)\b",
    r"\bsure,? i can\b",
    r"\bokay.*i.ll\b",
    r"\bthat.s clear\b",
    r"\bget it done\b",
]

# ---------------------------------------------------------------------------
# Correction cues — signals that a previous reply was wrong / overridden.
# If a later email in the same thread matches one of these, the earlier
# resolution candidate is invalidated (the flag stays OPEN).
# ---------------------------------------------------------------------------
CORRECTION_CUES: list[str] = [
    r"\bstop\b",
    r"\bno,\s",
    r"\bwait\b",
    r"\bnot what\b",
    r"\bthat.s wrong\b",
    r"\bonly modify\b",
    r"\bonly mentioned\b",
    r"\bthat.s not\b",
    r"\bdo not\b",
    r"\bdon.t\b",
]

# ---------------------------------------------------------------------------
# Noise keywords — social / off-topic content to filter
# ---------------------------------------------------------------------------
NOISE_KEYWORDS: list[str] = [
    r"\blunch\b",
    r"\brestaurant\b",
    r"\bpizza\b",
    r"\bmexican\b",
    r"\bfried chicken\b",
    r"\bmarzipan\b",
    r"\bcake\b",
    r"\bbirthday\b",
    r"\bchip in\b",
    r"\bsurprise\b",
    r"\bnot meant for here\b",
    r"\bwasn.t meant for\b",
    r"\bwrong.*thread\b",
]

# ---------------------------------------------------------------------------
# Security — patterns that flag sensitive data before sending to LLM
# ---------------------------------------------------------------------------
SENSITIVE_DATA_PATTERNS: list[str] = [
    r"\bsk-[a-zA-Z0-9]{20,}\b",                       # OpenAI-style API keys
    r"\bpassword\s*[:=]\s*\S+",                        # password assignments
    r"\bsecret\s*[:=]\s*\S+",                          # secret assignments
    r"\btoken\s*[:=]\s*\S+",                           # token assignments
    r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",   # credit card numbers
]

# ---------------------------------------------------------------------------
# Thresholds
# ---------------------------------------------------------------------------
NOISE_MIN_HITS: int = 2                  # min keyword matches to flag as noise
NOISE_MAX_WORDS: int = 80                # noise messages must be shorter than this
EVIDENCE_SNIPPET_LENGTH: int = 150       # chars of evidence snippet per flag
MAX_EMAIL_BODY_LENGTH: int = 5000        # security: max chars per email body

# ---------------------------------------------------------------------------
# LLM settings
# ---------------------------------------------------------------------------
LLM_TIER1_MODEL: str = "gpt-4o-mini"
LLM_TIER2_MODEL: str = "gpt-4o"
LLM_TEMPERATURE: int = 0
LLM_MAX_TOKENS: int = 300
