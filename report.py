"""
report.py — Markdown Portfolio Health Report generator.

Builds the final output grouped by project.
Rule: no statement appears without a direct email quote behind it.
Header clearly states whether AI enrichment was used.
"""

from datetime import datetime

from email_parser import Flag


def _render_flag(flag: Flag, show_resolution: bool = False) -> str:
    """Render a single flag as a Markdown block with evidence."""
    lines: list[str] = []
    lines.append(f"**[{flag.flag_type}]** — `{flag.source_file}`")

    if flag.owner:
        lines.append(f"  - 👤 Owner: {flag.owner}")
    if flag.priority:
        lines.append(f"  - 🎯 Priority: {flag.priority}")
    if flag.llm_summary:
        lines.append(f"  - 📝 {flag.llm_summary}")

    lines.append(f'  - 📌 Evidence: *"{flag.trigger_snippet.replace(chr(34), chr(39))}"*')

    if show_resolution and flag.resolution_snippet:
        lines.append(f'  - ✅ Resolution: *"{flag.resolution_snippet.replace(chr(34), chr(39))}"*')

    return "\n".join(lines)


def _render_project_section(
    project: str,
    open_flags: list[Flag],
    resolved_flags: list[Flag],
    email_count: int,
) -> list[str]:
    """Render one project's full section. Returns list of Markdown lines."""
    lines: list[str] = []

    lines.append(f"## 📁 {project}")
    lines.append("")
    lines.append(f"*Emails analysed: {email_count}*")
    lines.append("")

    # summary table
    open_actions = sum(1 for f in open_flags if f.flag_type == "UNRESOLVED_ACTION")
    open_risks = sum(1 for f in open_flags if f.flag_type == "RISK_BLOCKER")
    res_actions = sum(1 for f in resolved_flags if f.flag_type == "UNRESOLVED_ACTION")
    res_risks = sum(1 for f in resolved_flags if f.flag_type == "RISK_BLOCKER")

    lines.append("| Status | Action Items | Risks/Blockers |")
    lines.append("|---|---|---|")
    lines.append(f"| 🔴 Open | {open_actions} | {open_risks} |")
    lines.append(f"| 🟢 Resolved | {res_actions} | {res_risks} |")
    lines.append("")

    # open flags
    if open_flags:
        lines.append("### 🔴 Requires Attention")
        lines.append("")
        for flag in open_flags:
            lines.append(_render_flag(flag))
            lines.append("")

    # resolved flags
    if resolved_flags:
        lines.append("### 🟢 Recently Resolved")
        lines.append("")
        for flag in resolved_flags:
            lines.append(_render_flag(flag, show_resolution=True))
            lines.append("")

    # suggested next steps (deduplicated: one line per file + type)
    if open_flags:
        lines.append("### 💡 Suggested Next Steps")
        lines.append("")
        seen: set[tuple[str, str]] = set()
        for flag in open_flags:
            key = (flag.source_file, flag.flag_type)
            if key in seen:
                continue
            seen.add(key)
            if flag.flag_type == "UNRESOLVED_ACTION":
                lines.append(
                    f"- Follow up on unanswered action item in `{flag.source_file}`."
                )
            else:
                lines.append(
                    f"- Investigate risk/blocker in `{flag.source_file}` "
                    f"— assign owner and resolution path."
                )
        lines.append("")

    lines.append("---")
    lines.append("")
    return lines


def generate_report(
    project_flags: dict[str, list[Flag]],
    project_email_counts: dict[str, int],
    ai_used: bool,
) -> str:
    """
    Build the full Markdown report.

    Args:
        project_flags:        project_name → list of flags
        project_email_counts: project_name → number of emails analysed
        ai_used:              whether LLM enrichment ran
    """
    lines: list[str] = []

    # --- Header ---
    lines.append("# 📊 Portfolio Health Report — QBR")
    lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append(f"*AI enrichment: {'enabled' if ai_used else 'disabled (no API key)'}*")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Executive Summary ---
    total_open = 0
    total_resolved = 0
    total_filtered = 0

    project_open: dict[str, list[Flag]] = {}
    project_resolved: dict[str, list[Flag]] = {}

    for project, flags in project_flags.items():
        open_flags = [f for f in flags if f.status == "OPEN"]
        resolved_flags = [f for f in flags if f.status == "RESOLVED"]

        project_open[project] = open_flags
        project_resolved[project] = resolved_flags

        total_open += len(open_flags)
        total_resolved += len(resolved_flags)
        total_filtered += sum(1 for f in flags if f.status == "FALSE_POSITIVE")

    lines.append("## Executive Summary")
    lines.append("")
    lines.append("| Metric | Count |")
    lines.append("|---|---|")
    lines.append(f"| 🔴 Open Flags | {total_open} |")
    lines.append(f"| 🟢 Resolved Flags | {total_resolved} |")
    lines.append(f"| ⚪ False Positives (filtered) | {total_filtered} |")
    lines.append(f"| 📁 Projects Analysed | {len(project_email_counts)} |")
    lines.append("")
    lines.append("---")
    lines.append("")

    # --- Per-Project Sections ---
    for project in sorted(project_flags.keys()):
        lines.extend(_render_project_section(
            project=project,
            open_flags=project_open[project],
            resolved_flags=project_resolved[project],
            email_count=project_email_counts.get(project, 0),
        ))

    return "\n".join(lines)
