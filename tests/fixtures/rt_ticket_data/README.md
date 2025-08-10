# RT Ticket Test Fixtures

This directory contains test fixtures simulating RT API responses for complete ticket download automation testing with recursive history fetching.

## Structure

### Core Endpoints
```
rt_ticket_data/
├── metadata.bin          # RT response for /ticket/123 (basic ticket info)
├── history.bin           # RT response for /ticket/123/history (basic history list)
├── attachments.bin       # RT response for /ticket/123/attachments (attachment list with sizes)
```

### Individual History Entries (Recursive Fetching)
```
├── history_456.bin       # RT response for /ticket/123/history/id/456 (Create entry)
├── history_457.bin       # RT response for /ticket/123/history/id/457 (Correspond entry)
├── history_458.bin       # RT response for /ticket/123/history/id/458 (AddWatcher entry)
```

### Attachment Metadata and Content
```
├── attachment_456.bin    # Metadata for attachment 456 (empty/unnamed)
├── attachment_456_content.bin  # Content for attachment 456 (empty)
├── attachment_789.bin    # Metadata for attachment 789 (PDF document)
├── attachment_789_content.bin  # Content for attachment 789 (PDF data)
├── attachment_790.bin    # Metadata for attachment 790 (Excel file)
├── attachment_790_content.bin  # Content for attachment 790 (Excel data)
├── attachment_800.bin    # Metadata for attachment 800 (PDF, non-email)
├── attachment_800_content.bin  # Content for attachment 800 (PDF data)
├── attachment_801.bin    # Metadata for attachment 801 (Excel, non-email)
├── attachment_801_content.bin  # Content for attachment 801 (Excel data)
```

## Test Scenarios

### Attachment Processing
- **Zero-byte attachments**: 456 (skipped during download)
- **Outgoing emails**: 789, 790 (skipped via X-RT-Loop-Prevention header detection)
- **Regular attachments**: 800, 801 (downloaded as `{history_id}-{attachment_id}.{ext}`)

### History Processing
- **Basic history list**: Simple format with IDs and descriptions
- **Recursive fetching**: Individual entries fetched due to broken `format=l` parameter
- **Expected downloads**: `458-800.pdf`, `458-801.xlsx` (from AddWatcher history entry)

## Usage

Tests use these fixtures to:
1. Mock RT API responses for recursive history fetching workflow
2. Test zero-byte attachment detection and skipping
3. Test outgoing email attachment filtering
4. Verify correct filename format: `{history_id}-{attachment_id}.{extension}`
5. Validate attachment cache building with size parsing

## Format

All `.bin` files contain raw RT API responses with RT headers:
- Standard format: `RT/4.4.3 200 Ok\n\n{payload}`
- Content URLs include 3-newline suffix: `{content}\n\n\n`
- Empty content responses return completely empty HTTP body (zero bytes)

## Pre-commit Hooks

`.bin` files are excluded from pre-commit processing as they contain binary test data that should not be modified by text-processing hooks.
