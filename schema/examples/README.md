# RT Ticket Schema Examples

This directory contains example JSON instances that conform to the RT Ticket Automation Schema (`../rt_ticket_schema.json`). These examples demonstrate different types of RT tickets and their structured metadata.

## Example Types

### 1. Olink Data Transfer (`olink_data_transfer.json`)
**Use Case**: Simple proteomics data transfer to external collaborators

**Key Features**:
- Single project with OLINKHT data type
- Multiple file formats (parquet, csv.gz, pdf)
- Two recipients at same institution
- No batch structure (single delivery)
- No MD5 checksums required

**Pattern**: Research collaboration data sharing

---

### 2. Genomic Batch Submission (`genomic_batch_submission.json`)
**Use Case**: Large-scale genomic reprocessing with batch organization

**Key Features**:
- Batch-focused (project name unknown)
- 69 samples in named batch
- MD5 checksums required
- Minimal file list (manifest file)
- Recipient organization specified

**Pattern**: Production reprocessing workflows

---

### 3. RNA-seq Multi-Batch (`rna_seq_multi_batch.json`)
**Use Case**: Complex multi-batch RNA sequencing study

**Key Features**:
- Full project metadata (name, ID, data type)
- Part of multi-batch series (1 of 3)
- FASTQ files with compound extensions
- Multiple file types and base paths
- Related ticket references
- MD5 checksums and additional files expected

**Pattern**: Large-scale sequencing projects with multiple deliveries

## Schema Validation

All examples can be validated against the schema:

```bash
# Using ajv-cli
ajv validate -s ../rt_ticket_schema.json -d olink_data_transfer.json
ajv validate -s ../rt_ticket_schema.json -d genomic_batch_submission.json
ajv validate -s ../rt_ticket_schema.json -d rna_seq_multi_batch.json
```

```python
# Using Python jsonschema
import json
import jsonschema

with open('../rt_ticket_schema.json') as f:
    schema = json.load(f)

for example in ['olink_data_transfer.json', 'genomic_batch_submission.json', 'rna_seq_multi_batch.json']:
    with open(example) as f:
        ticket = json.load(f)

    try:
        jsonschema.validate(ticket, schema)
        print(f"✅ {example} is valid")
    except jsonschema.ValidationError as e:
        print(f"❌ {example}: {e.message}")
```

## Key Differences Illustrated

| Feature | Olink Transfer | Genomic Batch | RNA-seq Multi |
|---------|---------------|---------------|---------------|
| **Project Focus** | Single project | Batch-focused | Multi-batch project |
| **Data Type** | OLINKHT | Unknown | RNA-seq |
| **Sample Count** | None specified | 69 samples | 24 samples |
| **File Complexity** | Simple (3 files) | Minimal (1 file) | Complex (4+ files) |
| **MD5 Required** | No | Yes | Yes |
| **Multi-batch** | No | No | Yes (1 of 3) |
| **Recipients** | 2 (same org) | 2 (different orgs) | 2 (same org) |

## Usage Patterns

### Automation Decision Tree
1. **Check `request_type`**: Filter for `data_transfer` vs `data_submission`
2. **Examine `processing_requirements.md5_checksums_required`**: Determine validation needs
3. **Look at `processing_requirements.multiple_batches_expected`**: Plan for additional tickets
4. **Use `automation_status.analysis_confidence`**: Decide on manual review needs

### File Handling Patterns
- **Compound Extensions**: Always use full extension (`.fastq.gz` not `.gz`)
- **Path Resolution**: Use `base_paths` to locate files on storage systems
- **Type Filtering**: Use `file_types` array for processing pipeline selection

### Recipient Management
- **Email-based Deduplication**: Ensure unique recipients per ticket
- **Institution Tracking**: Use for organizational reporting
- **Notification Lists**: Build from `recipients` array

These examples provide a foundation for implementing RT ticket automation systems with proper schema validation and consistent metadata extraction.
