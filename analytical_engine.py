"""
analytical_engine.py — Pipeline orchestrator. No logic lives here.
Connects modules in order, collects metrics, writes output files.

Usage:
    python analytical_engine.py --email-dir ./emails --output report.md

    # With LLM enrichment:
    export OPENAI_API_KEY=sk-...
    python analytical_engine.py --email-dir ./emails --output report.md
"""

import argparse
import json
import time

from email_parser import load_emails, group_by_project, load_colleagues, Email, Flag
from detection import filter_noise, extract_signals, detect_resolutions
from enrichment import enrich_flags, _api_key_available
from report import generate_report


def _process_projects(
    projects: dict[str, list[Email]]
) -> tuple[list[Flag], dict[str, int], dict[str, list[Email]], int]:
    """
    Per-project: noise filter + signal extraction.
    Returns (all_flags, email_counts, clean_project_emails, total_noise).
    """
    all_flags: list[Flag] = []
    email_counts: dict[str, int] = {}
    clean_emails: dict[str, list[Email]] = {}
    total_noise = 0

    for project, emails in projects.items():
        clean, noise_count = filter_noise(emails)
        total_noise += noise_count
        email_counts[project] = len(clean)
        clean_emails[project] = clean
        all_flags.extend(extract_signals(clean, project))

    return all_flags, email_counts, clean_emails, total_noise


def run_pipeline(email_dir: str, output_path: str = "report.md", debug_path: str = "debug.json"):
    """Run the full pipeline. Returns nothing — writes report.md and debug.json."""
    start_time = time.time()
    metrics: dict = {}

    # --- 1. Ingest ---
    print("\n[Pipeline] Step 1: Ingesting emails...")
    all_emails = load_emails(email_dir)
    metrics["emails_loaded"] = len(all_emails)

    if not all_emails:
        print("[Pipeline] No emails found. Nothing to report.")
        return

    # --- 2. Group by project ---
    print("[Pipeline] Step 2: Grouping by project...")
    projects = group_by_project(all_emails)
    metrics["projects_detected"] = len(projects)

    # --- 3. Per-project: noise filter + signal extraction ---
    print("[Pipeline] Step 3: Filtering noise + extracting signals...")
    all_flags, project_email_counts, clean_project_emails, total_noise = _process_projects(projects)
    metrics["noise_filtered"] = total_noise
    metrics["candidate_flags"] = len(all_flags)

    # --- 4. Resolution detection ---
    print("[Pipeline] Step 4: Detecting resolutions...")
    all_flags = detect_resolutions(all_flags, clean_project_emails)
    metrics["open_flags"] = sum(1 for f in all_flags if f.status == "OPEN")
    metrics["resolved_flags"] = sum(1 for f in all_flags if f.status == "RESOLVED")

    # --- 5. LLM enrichment (optional) ---
    print("[Pipeline] Step 5: LLM enrichment...")
    ai_used = _api_key_available()
    if ai_used:
        role_map = load_colleagues(email_dir)
        metrics["colleagues_loaded"] = len(role_map)
        all_flags = enrich_flags(all_flags, role_map)
        metrics["llm_enrichment"] = "enabled"
        metrics["false_positives"] = sum(1 for f in all_flags if f.status == "FALSE_POSITIVE")
    else:
        metrics["llm_enrichment"] = "disabled"

    # --- 6. Report ---
    print("[Pipeline] Step 6: Generating report...")
    project_flags: dict = {}
    for flag in all_flags:
        project_flags.setdefault(flag.project, []).append(flag)

    report_md = generate_report(
        project_flags=project_flags,
        project_email_counts=project_email_counts,
        ai_used=ai_used,
    )

    # --- Write outputs ---
    metrics["runtime_seconds"] = round(time.time() - start_time, 2)

    with open(output_path, "w", encoding="utf-8") as file:
        file.write(report_md)
    print(f"\n✅ Report written to {output_path}")

    with open(debug_path, "w", encoding="utf-8") as file:
        json.dump(metrics, file, indent=2)
    print(f"✅ Debug metrics written to {debug_path}")


if __name__ == "__main__":
    arg_parser = argparse.ArgumentParser(description="QBR Portfolio Health Report Generator")
    arg_parser.add_argument("--email-dir", default="./emails",
                            help="Path to email .txt files folder")
    arg_parser.add_argument("--output", default="report.md", help="Output report file")
    arg_parser.add_argument("--debug", default="debug.json", help="Output debug metrics file")
    args = arg_parser.parse_args()

    run_pipeline(args.email_dir, args.output, args.debug)
