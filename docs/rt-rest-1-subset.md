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

### Search Tickets
**Endpoint**: `GET /REST/1.0/search/ticket?query={query}&orderby={sort}&format={format}&fields={fields}`

Runs a TicketSQL query and returns matching tickets.

**Parameters**:
- `query`: TicketSQL expression, e.g.
  `Queue = 'Submissions' AND Created >= '2026-08-01' AND Created < '2026-09-01'`.
  Dates compare against timestamps, so an inclusive end date must be expressed
  as `Created < {end-date + 1 day}`.
- `orderby`: sort field prefixed with `+` (ascending) or `-` (descending),
  e.g. `+Created`
- `format`: `i` (`ticket/{id}` only), `s` (`{id}: {subject}`), or `l`
  (multi-line, full ticket details without content)
- `fields`: comma-separated field names to include

**Response** (`format=l`), one block per ticket separated by a `--` line:
```
RT/4.4.3 200 Ok

id: ticket/{ticket-id}
Queue: {queue-name}
Subject: {subject}
Status: {status}
Created: {created-date}
LastUpdated: {last-updated-date}
Owner: {owner}

--

id: ticket/{ticket-id}
...
```

A query matching nothing returns `200 Ok` with a `No matching results.` payload.
An unknown queue name is not an error: RT simply matches no tickets. Validate
queue names against the queue list rather than relying on the search to fail.

### Search Queues
**Endpoint**: `GET /REST/1.0/search/queue?query={query}`

Lists queues. `query=id > 0` returns every queue visible to the user.

**Response**:
```
RT/4.4.3 200 Ok

{queue-id}: {queue-name}
{queue-id}: {queue-name}
```

Note that `GET /REST/1.0/queue/{name}` also answers `200 Ok` for a queue that
does not exist, with a `# No queue named {name} exists.` comment in the payload,
so the payload — not the status — decides.

**Important — CSRF guard**: RT treats a cookie-authenticated request that
carries arguments as a possible cross-site request forgery and serves an HTML
interstitial ("Possible cross-site request forgery") instead of the REST
payload, with HTTP status 200. Sending a same-origin `Referer` header satisfies
the check. `RTSession.fetch_rest_params()` does this for every parameterized
request; `fetch_rest()` needs no such header because it sends no arguments.

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

## Write Operations

Every write posts a single form variable named `content`, holding an
RFC822-ish block of `Field: value` lines. A value spanning multiple lines
continues with a **leading space** on each subsequent line; a blank line
inside a value must therefore be a line holding exactly one space, since an
empty line ends the field and RT silently drops the rest.

### Required header

**A same-origin `Referer` is required on every write.** Without it RT answers
with **HTTP 200** and its "Possible cross-site request forgery" HTML page, and
the write does not happen. Measured against rt.hgsc.bcm.edu 4.4.3:

| POST variant | result |
| --- | --- |
| urlencoded, no extra headers | HTTP 200, CSRF interstitial, nothing written |
| urlencoded + `Referer: https://rt.hgsc.bcm.edu/` | `RT/4.4.3 200 Ok` |
| urlencoded + `Referer` + `X-Requested-With` | identical; `X-Requested-With` is not needed |
| multipart, no extra headers | CSRF interstitial; encoding is irrelevant |

This is the same guard `fetch_rest_params()` works around for GETs carrying
query parameters. `parser.is_csrf_interstitial()` detects the rejection, which
is otherwise invisible: the status line says 200 and the body is HTML rather
than an RT response.

### Create a ticket

```
POST /REST/1.0/ticket/new
content=id: ticket/new
Queue: Submissions
Subject: ...
Requestor: someone@example.org
Owner: username
Text: first line
 continuation line
```

`Queue` is required. Other fields: `Cc`, `AdminCc`, `Status`, `Priority`,
`InitialPriority`, `FinalPriority`, `TimeEstimated`, `Starts`, `Due`, and
`CF-{Name}` for custom fields.

Success response: `# Ticket 39945 created.`

### Comment on or reply to a ticket

Both use the same endpoint and differ only in `Action`:

```
POST /REST/1.0/ticket/{id}/comment
content=id: {id}
Action: comment        # or: correspond
Text: the message
Cc: someone@example.org
Bcc: ...
TimeWorked: ...
```

- `Action: comment` is an internal note. RT mails nobody, though it still
  records an outgoing `CommentEmailRecord` history entry.
- `Action: correspond` is a reply. RT mails the requestors, and moves a `new`
  ticket to `open`.
- `Cc` and `Bcc` apply to that transaction only.

Success responses: `# Comments added` and `# Correspondence added`
respectively. Both arrive with no trailing id.

### Failure reporting

RT reports a rejected write in the **body**, with `200 Ok` on the status line
— for example `# Could not create ticket.` followed by field errors. Treat any
response that does not match a known success comment as a failure rather than
assuming success from the status line.

Attachments (`Attachment:` in the block plus a multipart `attachment_$i` per
file) are documented upstream but not implemented here.

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
- Use only `\n`, not `\r\n` in POST content (see Write Operations)
- Multi-line attachment lists use indented continuation lines

## SSL Configuration

This project uses custom SSL certificate verification:
- **Certificate File**: Bundled with the package (loaded automatically from package data)
- **Cookie Storage**: Mozilla cookie jar format (`cookies.txt`)
- **Session Management**: Persistent across CLI invocations via saved cookies

---

*This documentation covers only the RT REST API subset used by rt-tools. For operations it does not use — editing fields, links, merges, attachments on writes — refer to the full documentation.*
