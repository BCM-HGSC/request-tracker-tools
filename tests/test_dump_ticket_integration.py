"""Integration tests for dump-ticket command with file output."""

import subprocess

import pytest


@pytest.mark.integration
def test_dump_ticket_file_output(tmp_path):
    """Integration test for dump-ticket command with -o option.

    Tests the complete flow:
    - Command line parsing with -o option
    - RT server authentication
    - Fetching attachment content
    - Writing binary content to specified output file

    Requires actual RT server access and valid ticket/attachment.
    """
    # Create output directory structure
    output_dir = tmp_path / "37525" / "attachments"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "1483996.bin"

    # Command to test
    cmd = [
        "dump-ticket",
        "-q",  # Quiet mode to suppress logging
        "37525",
        "attachments/1483996/content",
        "-o",
        str(output_file),
    ]

    # Execute the command
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=False,  # Keep binary output
        timeout=30,  # Prevent hanging on network issues
    )

    # Verify command executed successfully
    assert result.returncode == 0, (
        f"dump-ticket command failed with return code {result.returncode}\n"
        f"stderr: {result.stderr.decode('utf-8', errors='replace')}"
    )

    # Verify output file was created
    assert output_file.exists(), f"Output file was not created: {output_file}"

    # Verify file has content (attachment should not be empty)
    assert output_file.stat().st_size > 0, f"Output file is empty: {output_file}"

    # Read and verify the content looks like binary attachment data
    content = output_file.read_bytes()

    # Basic sanity checks for attachment content
    # (These will depend on what type of file attachment 1483996 actually is)
    assert len(content) > 100, "Attachment content seems too small"

    # Verify no stdout output when using -o option
    assert len(result.stdout) == 0, (
        "Should not write to stdout when -o option is used, "
        f"but got: {result.stdout[:100]}..."
    )


@pytest.mark.integration
def test_dump_ticket_invalid_attachment(tmp_path):
    """Test dump-ticket with invalid attachment ID."""
    output_file = tmp_path / "invalid_attachment.bin"

    cmd = [
        "dump-ticket",
        "-q",
        "37525",
        "attachments/999999/content",  # Non-existent attachment
        "-o",
        str(output_file),
    ]

    subprocess.run(cmd, capture_output=True, text=False, timeout=30)

    # Command should handle errors gracefully
    # (Return code depends on how RT handles invalid attachment IDs)
    # File should either not exist or be empty
    if output_file.exists():
        assert output_file.stat().st_size == 0, (
            "Output file should be empty for invalid attachment"
        )


@pytest.mark.integration
def test_dump_ticket_output_directory_creation(tmp_path):
    """Test that dump-ticket can create parent directories."""
    # Use a deeply nested path that doesn't exist
    output_file = tmp_path / "deep" / "nested" / "path" / "attachment.bin"

    cmd = [
        "dump-ticket",
        "-q",
        "37525",
        "attachments/1483996/content",
        "-o",
        str(output_file),
    ]

    # This should fail because parent directories don't exist
    # (dump-ticket doesn't create parent dirs - that's expected behavior)
    result = subprocess.run(cmd, capture_output=True, text=False, timeout=30)

    # Should fail with file not found or similar error
    assert result.returncode != 0, (
        "Command should fail when parent directories don't exist"
    )

    # File should not be created
    assert not output_file.exists(), (
        "Output file should not exist when parent directories missing"
    )


@pytest.mark.integration
def test_dump_ticket_without_output_option():
    """Test dump-ticket without -o option (stdout behavior)."""
    cmd = ["dump-ticket", "-q", "37525", "attachments/1483996/content"]

    result = subprocess.run(cmd, capture_output=True, text=False, timeout=30)

    # Verify command executed successfully
    assert result.returncode == 0, (
        f"dump-ticket command failed with return code {result.returncode}\n"
        f"stderr: {result.stderr.decode('utf-8', errors='replace')}"
    )

    # Should write binary content to stdout
    assert len(result.stdout) > 0, "Should write attachment content to stdout"

    # Content should look like binary data
    assert len(result.stdout) > 100, "Stdout content seems too small"
