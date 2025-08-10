# RT REST 1.0 API Subset Documentation

This document covers only the RT REST 1.0 API endpoints used by this project. For complete API documentation, see `docs/rt-rest-1-snapshot.html`.

## Base Configuration

- **Base URL**: `https://rt.hgsc.bcm.edu`
- **REST API Base**: `https://rt.hgsc.bcm.edu/REST/1.0`
- **Response Format**: All responses follow pattern: `RT/{version} {status_code} {status_text}\n\n{payload}`

## Authentication

### Session Check
**Endpoint**: `GET /REST/1.0`

Tests if current session is authenticated.

**Response**:
```
RT/3.4.5 200 Ok

# Invalid object specification: 'index.html'

id: index.html
```

**Authentication Status**: Check if response text matches pattern `rt/[.0-9]+\s+200\sok` (case insensitive).

### Login
**Endpoint**: `POST https://rt.hgsc.bcm.edu` (base URL, not REST endpoint)

**Parameters**:
- `user`: Username
- `pass`: Password

**Purpose**: Authenticate and receive session cookies for subsequent requests.

**Note**: The REST Interface does not support HTTP-Authentication. You must obtain session cookies via form-based login, then submit cookies with each REST API request.

### Logout
**Endpoint**: `GET /REST/1.0/logout`

Ends the session and clears authentication cookies.

## Ticket Operations

### Get Ticket Metadata
**Endpoint**: `GET /REST/1.0/ticket/{ticket-id}`

Gets basic ticket information without history or comments.

**Response**:
```
RT/3.4.5 200 Ok

id: ticket/{ticket-id}
Queue: {queue-name}
Owner: {owner}
Creator: {creator}
Subject: {subject}
Status: {status}
Priority: {priority}
InitialPriority: {initial-priority}
FinalPriority: {final-priority}
Requestors: {requestors}
Cc: {cc-list}
AdminCc: {admin-cc-list}
Created: {created-date}
Starts: {starts-date}
Started: {started-date}
Due: {due-date}
Resolved: {resolved-date}
Told: {told-date}
TimeEstimated: {time-estimated}
TimeWorked: {time-worked}
TimeLeft: {time-left}
```

## History Operations

### Get Basic History
**Endpoint**: `GET /REST/1.0/ticket/{ticket-id}/history`

Gets list of all history items for a ticket.

**Response**:
```
RT/3.4.5 200 Ok

# {history-count}/{history-count} (/total)

{history-id}: {history-description}
{history-id}: {history-description}
...
```

### Get Detailed History (Long Format)

**NOTE:** Due to a bug, this option is broken. Do not use it.

### Get Detailed History (Recursively)

- Download and parse `GET /REST/1.0/ticket/{ticket-id}/history`
- For each history-id:
    - Download and parse `GET /REST/1.0/ticket/{ticket-id}/history/id/{history-id}`

**Response**:
```
RT/4.4.3 200 Ok

# {history-count}/{history-count} (id/{history-id}/total)

id: {history-id}
Ticket: {ticket-id}
TimeTaken: {time-taken}
Type: {entry-type}
Field: {field}
OldValue: {old-value}
NewValue: {new-value}
Data: {data}
Description: {description}
Content: {content-text}
Creator: {creator}
Created: {created-date}

Attachments:
             {attachment-id}: {filename} ({size})
             {attachment-id}: {filename} ({size})


```


## Attachment Operations

### Get Attachments List
**Endpoint**: `GET /REST/1.0/ticket/{ticket-id}/attachments`

Gets list of all attachments with metadata for MIME type and filename caching.

**Response Format**:
```
RT/4.4.3 200 Ok

{attachment-id}: {filename} ({mime-type} / {size})
{attachment-id}: {filename} ({mime-type} / {size})
...
```

**Example**:
```
456: (Unnamed) (text/plain / 0.2k)
789: sample_document.pdf (application/pdf / 45k)
790: data_file.xlsx (application/vnd.openxmlformats-officedocument.spreadsheetml.sheet / 23k)
```

### Get Attachment Metadata
**Endpoint**: `GET /REST/1.0/ticket/{ticket-id}/attachments/{attachment-id}`

Gets detailed metadata for a specific attachment, including headers.

**Response**:
```
RT/3.8.0 200 Ok

id: {attachment-id}
Subject: {subject}
Creator: {user-id}
Created: {timestamp}
Transaction: {transaction-id}
Parent: {parent-id}
MessageId: {message-id}
Filename: {filename}
ContentType: {mime-type}
ContentEncoding: {encoding}

Headers: {mime-headers}
         {additional-headers}
         X-RT-Loop-Prevention: {rt-server}
         {more-headers}

Content: {content-preview}
```

**Usage**: Check `Headers` section for `X-RT-Loop-Prevention:` to identify outgoing RT-generated emails that should be skipped.

### Get Attachment Content
**Endpoint**: `GET /REST/1.0/ticket/{ticket-id}/attachments/{attachment-id}/content`

Gets raw binary attachment content without metadata.

**Response**:
```
RT/3.8.0 200 Ok

{binary-content-data}


```

**Important**:
- Content URLs end with 3 newlines (`\n\n\n`) that must be stripped
- Response parsing automatically handles this for `/content` endpoints
- Content is returned as binary data, ready for file writing

## Response Parsing

### Standard RT Response Format
All RT REST responses follow this pattern:
```
RT/{version} {status_code} {status_text}\n\n{payload}
```

### Status Codes
- **Success**: `RT/4.4.3 200 Ok`
- **Error**: `RT/4.4.3 404 Not Found`, etc.
- **Authentication**: Check for "200 Ok" specifically

### Content Termination
- Standard endpoints: Payload ends after header
- `/content` endpoints: Payload ends with `\n\n\n` which is automatically stripped

## History Entry Types

Common history entry types encountered:
- `Create`: Ticket creation
- `Correspond`: Outgoing correspondence (usually emails)
- `Comment`: Internal comments
- `AddWatcher`: Adding watchers/files
- `Status`: Status changes
- `Priority`: Priority changes
- `CustomField`: Custom field updates

## Data Format Notes

- History timestamps are in UTC
- Boolean values return as `1` (true) and `0` (false)
- Comments in response body start with `#` symbol
- Use only `\n`, not `\r\n` in POST content
- Multi-line attachment lists use indented continuation lines

## SSL Configuration

This project uses custom SSL certificate verification:
- **Certificate File**: `rt.hgsc.bcm.edu.pem` (must be present in working directory)
- **Cookie Storage**: Mozilla cookie jar format (`cookies.txt`)
- **Session Management**: Persistent across CLI invocations via saved cookies

---

*This documentation covers only the RT REST API subset used by rt-tools. For complete API documentation including ticket creation, editing, search, and other operations, refer to the full documentation.*
