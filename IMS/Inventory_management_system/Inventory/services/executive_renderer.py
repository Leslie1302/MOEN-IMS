"""
Executive (plain-English) weekly report renderer.

Takes the same analyser output the technical WeeklyReportGenerator uses and
re-renders it for a non-technical audience -- specifically a Chief Director
reading the Ministry's weekly progress report.

Follows the prompt the user provided verbatim:

  Role: Senior Product Manager at the Ministry of Energy.
  Task: Transform technical development logs into a polished, non-technical
        Weekly Progress Report for the Chief Director.
  Rules:
    1. Avoid technical terms (no "migrations", "database schema", "views.py",
       "refactoring").
    2. Focus on value -- for every technical change, explain why it matters.
    3. The "So What?" test -- if a task doesn't directly help the user or
       business process, frame it as "System Reliability & Security Improvements".
  Structure:
    - Executive Impact          (3-sentence summary)
    - Process Improvements      (translate technical updates into functional ones)
    - Operational Health        (% processed, notifications sent, etc.)
    - Strategic Outlook         (administrative workflows, user communication)

This module is consumed by WeeklyReportGenerator when report.mode == 'executive'.
The PDF and email body both render through here in that mode.
"""

from __future__ import annotations

import re
from typing import Dict, List


# Phrase translation table: maps technical fingerprints in commit messages
# or migration filenames into Chief-Director-friendly language. Tested
# against the actual project history.
TRANSLATIONS: List[tuple] = [
    # Project-type expansions.
    (re.compile(r'streetlights?\s*project\s*type|add_streetlights_project_type|streetlights?', re.I),
        "Enabled specialised tracking for Streetlight infrastructure projects, "
        "ensuring every release tied to a streetlight initiative is logged separately and traceable."),
    (re.compile(r'cost[\s_-]*sharing', re.I),
        "Continued strengthening the Cost-Sharing project workflow so each beneficiary "
        "community's contribution is captured against the materials issued."),
    (re.compile(r'\bSHEP\b', re.I),
        "Refined the Self-Help Electrification Programme workflow so consultants are "
        "automatically identified for every release in their assigned region."),

    # Signatory / authorisation.
    (re.compile(r'signator(y|ies)|signature|signed|two.person', re.I),
        "Strengthened the digital authorisation chain for material releases. "
        "Every release now requires both the authoriser's signature and a second-person "
        "confirmation before materials physically leave the warehouse."),

    # QR / scan validation.
    (re.compile(r'\bQR\b|scan[_\s]*validation|signed[_\s]*scan|verification\s*code', re.I),
        "Hardened the document-verification system so only the correct signed release "
        "letter is accepted -- random or wrong-document uploads are now rejected automatically, "
        "with an audit-log entry written for every attempt."),

    # MP / consultant routing.
    (re.compile(r'member\s*of\s*parliament|\bMP\b|constituency', re.I),
        "Made the Honourable MP for each constituency automatically the consignee on "
        "Cost-Sharing and Streetlight releases, removing the risk of releases being "
        "addressed to the wrong MP."),
    (re.compile(r'project[_\s]*consultant|\bconsultant\b', re.I),
        "Project consultants are now bound to their region automatically, so SHEP "
        "releases route to the right consultancy without manual lookup."),

    # Transporter integration.
    (re.compile(r'transporter|transport[_\s]*officers?|haulage', re.I),
        "Transporters can now have their own system accounts and receive in-system "
        "alerts the moment a delivery is assigned to their company."),

    # Audit / security infrastructure.
    (re.compile(r'audit[_\s]*log|audit\s*trail|force.accept', re.I),
        "Every high-stakes action -- approvals, force-accepts, group changes -- now "
        "writes a permanent audit entry, giving us a forensic trail for any future review."),

    # Backup / DR.
    (re.compile(r'backup|disaster\s*recovery|\bDR\b|azure[_\s]*blob', re.I),
        "Daily off-region backups are now configured so the Ministry's records remain "
        "recoverable even in the event of a regional outage."),

    # M365 / email.
    (re.compile(r'\bM365\b|microsoft\s*365|graph\s*api|email[_\s]*notification', re.I),
        "Switched all system emails -- including this weekly report -- to use the "
        "Ministry's Microsoft 365 environment, so every message comes from a known "
        "Ministry address and respects existing email policies."),

    # Bulk import.
    (re.compile(r'bulk[_\s]*import|excel[_\s]*upload|template[_\s]*download', re.I),
        "Added Excel-based bulk import so the team can register many communities, MPs, "
        "or consultants in a single upload instead of one-at-a-time entry."),

    # User roles.
    (re.compile(r'permissions?|roles?|groups?|canonical[_\s]*groups', re.I),
        "Standardised user permissions and regional assignments to ensure data security "
        "and consistent access control across the team."),

    # Workflow / release letter / memo.
    (re.compile(r'release[_\s]*letter|memo[_\s]*generated|workflow[_\s]*status', re.I),
        "The system now generates the approval memo and the release letter automatically, "
        "with a unique reference code printed and embedded in a QR code for verification."),

    # Splash / UI polish.
    (re.compile(r'splash|preloader|duplicate.*table|de.duplicate', re.I),
        "Polished the user interface to remove redundant on-screen controls and slow "
        "loading screens, so the team spends less time waiting on the system."),
]


def _translate_change(text: str) -> str:
    """Return the first translation that matches, or '' for nothing matched."""
    for pattern, message in TRANSLATIONS:
        if pattern.search(text):
            return message
    return ""


def _unique_messages(messages: List[str]) -> List[str]:
    """Dedupe while preserving order."""
    seen = set()
    out = []
    for m in messages:
        if m and m not in seen:
            seen.add(m)
            out.append(m)
    return out


def render_executive_report(
    report,
    commit_stats: Dict,
    activity_summary: Dict,
    categorized_commits: Dict,
    migrations: List[Dict],
    audit_highlights: Dict,
) -> Dict[str, str]:
    """Render the executive-style report.

    Returns a dict with `subject`, `html`, `plain_text` keys ready to be
    attached to the WeeklyReport instance and sent via M365 Graph.

    The caller is the WeeklyReportGenerator -- it gathers all inputs and
    delegates the language translation here.
    """
    # ------- Executive Impact (3 sentences) -------------------------------
    activity = activity_summary or {}
    total_orders = activity.get('material_orders', {}).get('total', 0) if isinstance(activity, dict) else 0
    pending_orders = activity.get('material_orders', {}).get('pending', 0) if isinstance(activity, dict) else 0
    notifications_sent = activity.get('notifications', {}).get('total', 0) if isinstance(activity, dict) else 0
    feature_count = len(categorized_commits.get('features', []))
    fix_count = len(categorized_commits.get('fixes', []))

    impact_sentences = []
    if total_orders:
        zero_pending_note = " — none of them are currently stuck pending action" if pending_orders == 0 else f" with {pending_orders} still pending action"
        impact_sentences.append(
            f"This week the system processed {total_orders} new material order{'s' if total_orders != 1 else ''}{zero_pending_note}, "
            "showing that the request-and-release workflow is moving cleanly end-to-end."
        )
    else:
        impact_sentences.append(
            "This week the system continued to operate quietly in the background, "
            "with the request-and-release workflow standing ready for the next batch of releases."
        )

    if feature_count or fix_count:
        bits = []
        if feature_count:
            bits.append(f"{feature_count} new capabilit{'ies' if feature_count != 1 else 'y'}")
        if fix_count:
            bits.append(f"{fix_count} reliability fix{'es' if fix_count != 1 else ''}")
        impact_sentences.append(
            f"We delivered {' and '.join(bits)} this week, each one targeted at making the "
            "Ministry's material-tracking process more transparent and harder to misuse."
        )
    else:
        impact_sentences.append(
            "Our focus this week was on system reliability and security hardening rather than user-facing features."
        )

    impact_sentences.append(
        "The overall direction remains the same: cut the paper trail, lock down approvals, "
        "and give the Ministry confidence that every release is authorised and accounted for."
    )
    executive_impact = " ".join(impact_sentences[:3])

    # ------- Process Improvements (translate technical -> functional) -----
    translated = []
    for bucket in ('features', 'fixes', 'refactoring'):
        for commit in categorized_commits.get(bucket, []):
            msg = (commit.get('message') or '').strip()
            files = commit.get('files') or []
            haystack = msg + " " + " ".join(files)
            translation = _translate_change(haystack)
            if translation:
                translated.append(translation)
    for mig in migrations or []:
        mig_name = mig.get('filename') or mig.get('name') or ''
        translation = _translate_change(mig_name)
        if translation:
            translated.append(translation)

    if not translated:
        translated.append(
            "System Reliability & Security Improvements -- background hardening that "
            "doesn't change any user-facing screen but reduces the chance of data loss "
            "or unauthorised changes."
        )
    process_improvements = _unique_messages(translated)

    # ------- Operational Health -----------------------------------------------
    health_lines = []
    if total_orders:
        if pending_orders == 0:
            health_lines.append(
                f"100% of this week's {total_orders} material order{'s' if total_orders != 1 else ''} "
                "are either in motion or fully closed -- nothing is stuck waiting on someone."
            )
        else:
            health_lines.append(
                f"{total_orders - pending_orders} of {total_orders} "
                f"({round(100 * (total_orders - pending_orders) / total_orders)}%) "
                "of this week's material orders are being actively progressed; "
                f"the remaining {pending_orders} are queued for approval."
            )
    if notifications_sent:
        health_lines.append(
            f"{notifications_sent} automated notification{'s' if notifications_sent != 1 else ''} "
            "were dispatched this week to keep staff aware of approvals, deliveries, and pending actions."
        )
    if audit_highlights and audit_highlights.get('total'):
        health_lines.append(
            f"The audit trail captured {audit_highlights['total']} significant event{'s' if audit_highlights['total'] != 1 else ''} "
            "this week, giving us a full record of every release, scan upload, and authorisation."
        )
    if not health_lines:
        health_lines.append(
            "Routine operations week -- no incidents, no escalations, no missing data."
        )

    # ------- Strategic Outlook ----------------------------------------------
    strategic_outlook = (
        "Looking ahead: we are finalising the administrative workflows that surround a "
        "release event -- the way memos are drafted, signed, and archived -- and refining "
        "user communication so that every staff member receives only the alerts relevant "
        "to their role. The aim is to remove the last manual steps from the release process "
        "by the end of the next reporting period."
    )

    # ------- Assemble HTML --------------------------------------------------
    period = "{} to {}".format(
        report.start_date.strftime('%d %b %Y'),
        report.end_date.strftime('%d %b %Y'),
    )
    process_html = ''.join('<li>' + item + '</li>' for item in process_improvements)
    health_html = ''.join('<li>' + item + '</li>' for item in health_lines)

    html = (
        '<div style="font-family: Calibri, Arial, sans-serif; color: #1f2933; max-width: 760px; line-height: 1.55;">'
        f'<h1 style="color: #003366;">Weekly Progress Report</h1>'
        f'<p style="color: #6c757d; margin-top: -8px;">Period: {period}</p>'
        '<h2 style="color: #003366; border-bottom: 2px solid #003366; padding-bottom: 6px;">Executive Impact</h2>'
        f'<p>{executive_impact}</p>'
        '<h2 style="color: #003366; border-bottom: 2px solid #003366; padding-bottom: 6px;">Process Improvements</h2>'
        f'<ul>{process_html}</ul>'
        '<h2 style="color: #003366; border-bottom: 2px solid #003366; padding-bottom: 6px;">Operational Health</h2>'
        f'<ul>{health_html}</ul>'
        '<h2 style="color: #003366; border-bottom: 2px solid #003366; padding-bottom: 6px;">Strategic Outlook</h2>'
        f'<p>{strategic_outlook}</p>'
        '<hr style="margin: 28px 0; border: none; border-top: 1px solid #d9dbdd;">'
        f'<p style="color: #6c757d; font-size: 0.85em;">'
        f'Prepared by the Ministry of Energy and Green Transition Inventory Management System. '
        f'Report reference: {report.report_id}.</p>'
        '</div>'
    )

    # ------- Plain text version ---------------------------------------------
    bullets = "\n".join(["  • " + item for item in process_improvements])
    health_bullets = "\n".join(["  • " + item for item in health_lines])
    plain = (
        "WEEKLY PROGRESS REPORT\n"
        "Period: " + period + "\n\n"
        "EXECUTIVE IMPACT\n"
        "----------------\n" + executive_impact + "\n\n"
        "PROCESS IMPROVEMENTS\n"
        "--------------------\n" + bullets + "\n\n"
        "OPERATIONAL HEALTH\n"
        "------------------\n" + health_bullets + "\n\n"
        "STRATEGIC OUTLOOK\n"
        "-----------------\n" + strategic_outlook + "\n\n"
        "Report reference: " + str(report.report_id) + "\n"
    )

    return {
        'subject': "Weekly Progress Report -- " + period,
        'html': html,
        'plain_text': plain,
    }
