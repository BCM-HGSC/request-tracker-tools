"""RT Ticket Analysis for automation-friendly YAML generation."""

import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def analyze_ticket(ticket_dir: Path) -> dict[str, Any]:
    """
    Analyze RT ticket directory and generate automation metadata.

    Args:
        ticket_dir: Directory containing downloaded RT ticket data

    Returns:
        Dictionary containing structured ticket analysis
    """
    logger.info(f"Analyzing ticket directory: {ticket_dir}")

    problems = []

    # Extract basic metadata
    metadata = extract_metadata(ticket_dir / "metadata.txt", problems)

    # Collect all message content
    all_content = collect_message_content(ticket_dir, problems)

    # Extract structured information
    subject = metadata.get("subject", "")
    project_batch_info = extract_project_and_batch_info(subject, all_content, problems)
    recipients = extract_recipients_structured(all_content, problems)
    data_files = extract_data_files(all_content, problems)
    processing_reqs = extract_processing_requirements(all_content, problems)

    # Build analysis structure
    analysis = build_analysis_structure(
        metadata, project_batch_info, recipients, data_files, processing_reqs, problems
    )

    # Write output files
    write_analysis_files(analysis, problems, ticket_dir)

    return analysis


def extract_metadata(metadata_path: Path, problems: list[str]) -> dict[str, Any]:
    """Extract basic ticket metadata from metadata.txt file."""
    metadata = {}

    if not metadata_path.exists():
        problems.append(f"Missing metadata file: {metadata_path}")
        logger.warning(f"Metadata file not found: {metadata_path}")
        return metadata

    try:
        content = metadata_path.read_text()
        for line in content.split("\n"):
            if ":" in line:
                key, value = line.split(":", 1)
                key = key.strip()
                value = value.strip()

                if key == "id":
                    metadata["ticket_id"] = value.replace("ticket/", "")
                elif key == "Subject":
                    metadata["subject"] = value
                elif key == "Requestors":
                    metadata["requestor_email"] = value
                elif key == "Owner":
                    metadata["assigned_to"] = value
                elif key == "Status":
                    metadata["status"] = value
                elif key == "Created":
                    metadata["created_date"] = value
                elif key == "Queue":
                    metadata["queue"] = value

    except Exception as e:
        problems.append(f"Error parsing metadata file: {e}")
        logger.warning(f"Failed to parse metadata: {e}")

    return metadata


def collect_message_content(ticket_dir: Path, problems: list[str]) -> str:
    """Collect all message content from history directories."""
    all_content = ""
    message_count = 0

    try:
        for item in ticket_dir.iterdir():
            if item.is_dir() and item.name.isdigit():
                message_path = item / "message.txt"
                if message_path.exists():
                    all_content += "\n" + message_path.read_text()
                    message_count += 1
    except Exception as e:
        problems.append(f"Error collecting message content: {e}")
        logger.warning(f"Failed to collect messages: {e}")

    if message_count == 0:
        problems.append("No message content found in history directories")
        logger.warning("No message files found")
    else:
        logger.debug(f"Collected content from {message_count} message files")

    return all_content


def extract_project_and_batch_info(
    subject: str, content: str, problems: list[str]
) -> dict[str, Any]:
    """Extract project name, batch information, and recipient organization."""
    info = {}

    try:
        # For MFTS Submission pattern: [SUBMISSION] MFTS Submission for Name, Batch Info
        submission_match = re.search(
            r"MFTS Submission for ([^,]+),\s*([^,]+),\s*(\d+)\s*sample",
            subject,
            re.IGNORECASE,
        )
        if submission_match:
            info["recipient_organization"] = submission_match.group(1).strip()
            batch_info = submission_match.group(2).strip()

            # Parse batch info for batch name and sample count
            if "batch" in batch_info.lower():
                info["batch_name"] = batch_info
                info["batch_sample_count"] = int(submission_match.group(3))
            else:
                info["project_name"] = batch_info

        # For MFTS OLINK pattern: MFTS OLINKHT PROJECT_ID
        olink_match = re.search(
            r"MFTS\s+(OLINK\w*)\s+([A-Z_\d]+)", subject, re.IGNORECASE
        )
        if olink_match:
            info["data_type"] = olink_match.group(1)
            info["project_id"] = olink_match.group(2)

        # Extract project name from content if available
        project_patterns = [
            r"TITLE OF THE SUBMITTED DATA.*?([^\n]+)",
            r"Dallas Hearts and Mind Study \(([^)]+)\)",
            r"Project:\s*([^\n]+)",
        ]

        for pattern in project_patterns:
            match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)
            if match:
                project_title = match.group(1).strip()
                if project_title and project_title != "(if needed)":
                    info["project_name"] = project_title
                    break

    except Exception as e:
        problems.append(f"Error extracting project/batch info: {e}")
        logger.warning(f"Project/batch extraction failed: {e}")

    return info


def extract_recipients_structured(
    content: str, problems: list[str]
) -> list[dict[str, str]]:
    """Extract recipient information with structured parsing."""
    recipients = []

    try:
        # Look for structured recipient format
        recipient_pattern = (
            r"Recipient#(\d+)[\s\S]*?Data recipient name:\s*([^\n]+)[\s\S]*?"
            r"Data recipient institution:\s*([^\n]+)[\s\S]*?"
            r"Data recipient institutional email:\s*([^\s<]+)"
        )

        matches = re.findall(recipient_pattern, content, re.IGNORECASE)
        for match in matches:
            recipient_num, name, institution, email = match
            # Clean up email (remove mailto links)
            email = re.sub(r"<mailto:[^>]+>", "", email).strip()

            recipients.append(
                {
                    "name": name.strip(),
                    "institution": institution.strip(),
                    "email": email,
                }
            )

        # Fallback to simple email extraction if structured format not found
        if not recipients:
            lines = content.split("\n")
            for i, line in enumerate(lines):
                line = line.strip()
                email_match = re.search(
                    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", line
                )
                if email_match:
                    email = email_match.group(0)
                    name = None

                    # Look for name in previous lines
                    for j in range(1, 4):
                        if i - j >= 0:
                            prev_line = lines[i - j].strip()
                            if prev_line and not re.match(
                                r"^(thanks|sincerely|hi|hello)",
                                prev_line,
                                re.IGNORECASE,
                            ):
                                if (
                                    re.match(r"^[A-Za-z\s]+$", prev_line)
                                    and len(prev_line.split()) <= 4
                                ):
                                    name = prev_line
                                    break

                    recipients.append(
                        {"name": name, "email": email, "institution": None}
                    )

    except Exception as e:
        problems.append(f"Error extracting recipients: {e}")
        logger.warning(f"Recipient extraction failed: {e}")

    # Remove duplicates based on email
    seen_emails = set()
    unique_recipients = []
    for recipient in recipients:
        email = recipient.get("email")
        if email and email not in seen_emails:
            unique_recipients.append(recipient)
            seen_emails.add(email)
        elif not email:  # Keep recipients without email
            unique_recipients.append(recipient)

    if not unique_recipients:
        problems.append("No recipients found in ticket content")
        logger.warning("No recipients extracted")

    return unique_recipients


def extract_data_files(content: str, problems: list[str]) -> dict[str, Any]:
    """Extract data files and their specifications."""
    data_info = {"files": [], "base_paths": [], "file_types": set()}

    try:
        # Extract file paths
        path_pattern = r"/[a-zA-Z0-9_/.-]+"
        paths = re.findall(path_pattern, content)

        # Extract specific file names with proper compound extension handling
        compound_extensions = ["csv.gz", "fastq.gz", "vcf.gz", "tar.gz"]
        simple_extensions = ["parquet", "pdf", "xlsx", "tsv", "txt"]

        all_extensions = compound_extensions + simple_extensions
        ext_pattern = "|".join([ext.replace(".", r"\.") for ext in all_extensions])
        file_pattern = rf"\b([A-Za-z0-9_.-]+\.({ext_pattern}))\b"
        files = re.findall(file_pattern, content, re.IGNORECASE)

        seen_files = set()
        for file_match in files:
            filename, ext = file_match
            if filename not in seen_files:
                data_info["files"].append({"filename": filename, "extension": ext})
                data_info["file_types"].add(ext)
                seen_files.add(filename)

        # Extract base paths
        for path in paths:
            if len(path) > 20:  # Filter out short paths
                data_info["base_paths"].append(path)

        # Remove duplicates
        data_info["file_types"] = list(data_info["file_types"])
        data_info["base_paths"] = list(set(data_info["base_paths"]))

    except Exception as e:
        problems.append(f"Error extracting data files: {e}")
        logger.warning(f"Data file extraction failed: {e}")

    return data_info


def extract_processing_requirements(
    content: str, problems: list[str]
) -> dict[str, Any]:
    """Extract processing and delivery requirements."""
    requirements = {}

    try:
        # MD5 checksum requirement
        requirements["md5_checksums_required"] = bool(
            re.search(r"md5|checksum|hash", content, re.IGNORECASE)
        )

        # Transfer method
        if "mfts" in content.lower():
            requirements["transfer_method"] = "MFTS"

        # Multiple batches
        multi_batch_match = re.search(
            r"WILL THERE BE SEVERAL BATCHES.*?(\w+)", content, re.IGNORECASE | re.DOTALL
        )
        if multi_batch_match:
            requirements["multiple_batches_expected"] = (
                multi_batch_match.group(1).lower() == "yes"
            )

        # Additional files
        additional_files_match = re.search(
            r"ADDITIONAL FILES.*?(\w+)", content, re.IGNORECASE | re.DOTALL
        )
        if additional_files_match:
            requirements["additional_files"] = (
                additional_files_match.group(1).lower() == "yes"
            )

    except Exception as e:
        problems.append(f"Error extracting processing requirements: {e}")
        logger.warning(f"Processing requirements extraction failed: {e}")

    return requirements


def build_analysis_structure(
    metadata: dict[str, Any],
    project_batch_info: dict[str, Any],
    recipients: list[dict[str, str]],
    data_files: dict[str, Any],
    processing_reqs: dict[str, Any],
    problems: list[str],
) -> dict[str, Any]:
    """Build the final analysis structure following the schema."""

    # Calculate confidence and processing readiness
    confidence = calculate_confidence_level(metadata, recipients, data_files, problems)
    ready_for_processing = len(problems) == 0 and len(recipients) > 0

    # Build schema-compliant structure
    analysis = {
        # Core identification
        "ticket_id": metadata.get("ticket_id"),
        "status": metadata.get("status"),
        "queue": metadata.get("queue"),
        "created_date": metadata.get("created_date"),
        "assigned_to": metadata.get("assigned_to"),
        # Request classification
        "request_type": "data_transfer",  # Default classification
        "transfer_method": processing_reqs.get("transfer_method", "MFTS"),
        # Project information
        "project": {
            "name": project_batch_info.get("project_name"),
            "id": project_batch_info.get("project_id"),
            "recipient_organization": project_batch_info.get("recipient_organization"),
            "data_type": project_batch_info.get("data_type"),
        },
        # Batch information
        "batch": {
            "name": project_batch_info.get("batch_name"),
            "sample_count": project_batch_info.get("batch_sample_count"),
        },
        # Communication
        "requestor": {"email": metadata.get("requestor_email")},
        "recipients": recipients,
        # Data specifications
        "data_specifications": {
            "files": data_files.get("files", []),
            "file_types": data_files.get("file_types", []),
            "base_paths": data_files.get("base_paths", []),
            "total_files": len(data_files.get("files", [])),
        },
        # Processing requirements
        "processing_requirements": {
            "md5_checksums_required": processing_reqs.get(
                "md5_checksums_required", False
            ),
            "multiple_batches_expected": processing_reqs.get(
                "multiple_batches_expected", False
            ),
            "additional_files_expected": processing_reqs.get("additional_files", False),
        },
        # Automation metadata
        "automation_status": {
            "parsed_date": date.today().isoformat(),
            "ready_for_processing": ready_for_processing,
            "analysis_confidence": confidence,
        },
    }

    return analysis


def calculate_confidence_level(
    metadata: dict[str, Any],
    recipients: list[dict[str, str]],
    data_files: dict[str, Any],
    problems: list[str],
) -> str:
    """Calculate analysis confidence level based on completeness."""
    if len(problems) > 3:
        return "low"
    elif len(problems) > 0 or not recipients or not data_files.get("files"):
        return "medium"
    elif metadata.get("ticket_id") and recipients and data_files.get("files"):
        return "high"
    else:
        return "medium"


def write_analysis_files(
    analysis: dict[str, Any], problems: list[str], ticket_dir: Path
) -> None:
    """Write analysis YAML and problems report if needed."""

    # Write main analysis file
    analysis_path = ticket_dir / "analysis.yaml"
    try:
        with open(analysis_path, "w") as f:
            yaml.dump(
                analysis,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        logger.info(f"Generated analysis file: {analysis_path}")
    except Exception as e:
        logger.error(f"Failed to write analysis YAML: {e}")
        raise

    # Write problems file if issues exist
    if problems:
        problems_path = ticket_dir / "analysis_problems.yaml"
        try:
            problems_report = {
                "ticket_id": analysis.get("ticket_id"),
                "analysis_date": analysis["automation_status"]["parsed_date"],
                "problem_count": len(problems),
                "problems": problems,
                "next_steps": [
                    "Review ticket content for missing information",
                    "Request clarification from ticket requestor if needed",
                    "Re-run analyze-ticket after content updates",
                ],
            }
            with open(problems_path, "w") as f:
                yaml.dump(
                    problems_report, f, default_flow_style=False, allow_unicode=True
                )
            logger.warning(
                f"Analysis completed with {len(problems)} problems. "
                f"See: {problems_path}"
            )
        except Exception as e:
            logger.error(f"Failed to write problems YAML: {e}")
            raise


def validate_ticket_analysis(analysis: dict[str, Any]) -> tuple[bool, list[str]]:
    """
    Validate ticket analysis structure against schema requirements.

    Args:
        analysis: Ticket analysis dictionary

    Returns:
        Tuple of (is_valid, list_of_errors)
    """
    errors = []

    # Check required top-level fields
    required_fields = [
        "ticket_id",
        "status",
        "request_type",
        "transfer_method",
        "requestor",
        "recipients",
        "automation_status",
    ]

    for field in required_fields:
        if field not in analysis:
            errors.append(f"Missing required field: {field}")

    # Validate requestor has email
    if "requestor" in analysis:
        if not analysis["requestor"].get("email"):
            errors.append("Requestor must have email address")

    # Validate recipients
    if "recipients" in analysis:
        if not analysis["recipients"]:
            errors.append("At least one recipient is required")
        else:
            for i, recipient in enumerate(analysis["recipients"]):
                if not recipient.get("email"):
                    errors.append(f"Recipient {i} missing email address")

    # Validate automation_status
    if "automation_status" in analysis:
        auto_status = analysis["automation_status"]
        if "parsed_date" not in auto_status:
            errors.append("automation_status missing parsed_date")
        if "ready_for_processing" not in auto_status:
            errors.append("automation_status missing ready_for_processing")

    # Validate file extensions if present
    if "data_specifications" in analysis and "files" in analysis["data_specifications"]:
        valid_extensions = [
            "parquet",
            "csv.gz",
            "fastq.gz",
            "vcf.gz",
            "tar.gz",
            "pdf",
            "xlsx",
            "tsv",
            "txt",
        ]
        for file_info in analysis["data_specifications"]["files"]:
            ext = file_info.get("extension")
            if ext and ext not in valid_extensions:
                errors.append(f"Invalid file extension: {ext}")

    is_valid = len(errors) == 0
    return is_valid, errors
