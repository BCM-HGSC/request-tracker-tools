# RT Ticket Test Fixtures

This directory contains test fixtures simulating RT API responses for a complete ticket download automation test.

## Structure

```
rt_ticket_data/
├── metadata.bin          # RT response for /ticket/123 (basic ticket info)
├── history.bin           # RT response for /ticket/123/history (ticket history)
├── attachments.bin       # RT response for /ticket/123/attachments (attachment list)
├── attachment_456.bin    # RT response for /ticket/123/attachments/456 (attachment metadata)
├── attachment_456_content.bin  # RT response for /ticket/123/attachments/456/content (file data)
└── attachment_789.bin    # Additional attachment metadata
└── attachment_789_content.bin  # Additional attachment content
```

## Usage

Tests will use these fixtures to:
1. Mock RT API responses for various endpoints
2. Verify that ticket download automation creates the correct directory structure
3. Validate that downloaded files match expected content

## Format

All `.bin` files contain raw RT API responses including headers:
- `RT/4.4.3 200 Ok\n\n{payload}`
- Content URLs include the 3-newline suffix: `{content}\n\n\n`