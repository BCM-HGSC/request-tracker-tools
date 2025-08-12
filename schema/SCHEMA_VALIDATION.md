# RT Ticket Schema Validation Guide

## Overview

The RT Ticket Automation Schema (`rt_ticket_schema.json`) provides a formal JSON Schema specification for validating structured metadata extracted from RT tickets. This enables consistent data validation and automated processing.

## Schema Key Features

### 1. **Strict Type Validation**
- Required fields ensure essential data is present
- Enum constraints limit values to known options
- Format validation for emails and file paths

### 2. **Compound File Extension Support**
- Properly handles `.csv.gz`, `.fastq.gz`, `.vcf.gz`, `.tar.gz`
- Prevents incorrect parsing of compressed files as simple `.gz`

### 3. **Project vs Batch Separation**
- `project`: High-level information (name, ID, organization, data type)
- `batch`: Processing-specific details (batch name, sample count)

### 4. **Deduplication Requirements**
- Recipients must have unique email addresses
- Files must have unique filenames within a ticket

## Validation Rules

### Required Fields
All tickets must include:
- `ticket_id`: RT ticket number
- `status`: Current ticket status
- `request_type`: Classification of request
- `transfer_method`: Data transfer mechanism
- `requestor.email`: Valid email address
- `recipients`: At least one recipient with email
- `automation_status.parsed_date`: Processing date
- `automation_status.ready_for_processing`: Boolean flag

### Data Type Constraints

#### File Extensions
Only these extensions are allowed:
- **Compound**: `csv.gz`, `fastq.gz`, `vcf.gz`, `tar.gz`
- **Simple**: `parquet`, `pdf`, `xlsx`, `tsv`, `txt`

#### Request Types
- `data_transfer`: Standard MFTS transfers
- `data_submission`: New data submissions
- `technical_support`: Support requests

#### Transfer Methods
- `MFTS`: Managed File Transfer System
- `FTP`, `Aspera`, `Box`, `Other`: Alternative methods

#### Biological Data Types
- `OLINKHT`: Olink Explore HT proteomics
- `WGS`: Whole Genome Sequencing
- `RNA-seq`, `ChIP-seq`, `ATAC-seq`: Sequencing types
- `Proteomics`, `Metabolomics`: Multi-omics data

### Validation Examples

#### ✅ Valid Ticket
```json
{
  "ticket_id": "37603",
  "status": "new",
  "request_type": "data_transfer",
  "transfer_method": "MFTS",
  "requestor": {"email": "researcher@bcm.edu"},
  "recipients": [
    {
      "name": "John Doe",
      "email": "john.doe@utsouthwestern.edu",
      "institution": "UT Southwestern"
    }
  ],
  "automation_status": {
    "parsed_date": "2025-08-11",
    "ready_for_processing": true
  }
}
```

#### ❌ Invalid Examples

**Missing Required Field:**
```json
{
  "ticket_id": "37603",
  "status": "new"
  // Missing request_type, transfer_method, requestor, recipients, automation_status
}
```

**Invalid File Extension:**
```json
{
  "data_specifications": {
    "files": [
      {
        "filename": "data.gz",
        "extension": "gz"  // Should be compound extension like "csv.gz"
      }
    ]
  }
}
```

**Invalid Email Format:**
```json
{
  "requestor": {
    "email": "not-an-email"  // Must be valid email format
  }
}
```

## Usage with Validation Tools

### Python (jsonschema)
```python
import json
import jsonschema

# Load schema
with open('rt_ticket_schema.json') as f:
    schema = json.load(f)

# Load ticket data
with open('ticket_data.json') as f:
    ticket = json.load(f)

# Validate
try:
    jsonschema.validate(ticket, schema)
    print("✅ Ticket is valid")
except jsonschema.ValidationError as e:
    print(f"❌ Validation error: {e.message}")
```

### Command Line (ajv-cli)
```bash
# Install ajv-cli
npm install -g ajv-cli

# Validate ticket data
ajv validate -s rt_ticket_schema.json -d ticket_data.json
```

## Schema Evolution

### Version 2.0 Features
- Project/batch separation
- Compound file extension support
- Recipient deduplication
- Enhanced automation metadata

### Future Considerations
- Sample-level metadata for complex batches
- Quality control metrics
- Processing pipeline specifications
- Integration with LIMS systems

## Best Practices

1. **Always validate** extracted ticket data against the schema
2. **Use compound extensions** for compressed files (`.csv.gz` not `.gz`)
3. **Deduplicate recipients** by email address
4. **Set confidence levels** based on extraction quality
5. **Include processing requirements** for automation decisions

## Common Validation Errors

| Error | Cause | Solution |
|-------|-------|----------|
| Missing required field | Incomplete extraction | Improve parsing logic |
| Invalid enum value | Unknown status/type | Update enum constraints |
| Format violation | Bad email/path format | Add format validation |
| Type mismatch | Wrong data type | Fix type conversion |
| Additional properties | Extra fields | Remove or allow in schema |

This schema specification ensures consistent, validated metadata extraction for reliable RT ticket automation.
