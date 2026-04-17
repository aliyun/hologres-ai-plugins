# Hologres CLI Safety Features

Safety guardrails to prevent accidental data loss and ensure safe operations.

## Row Limit Protection

### Purpose
Prevents accidental retrieval of large result sets that could:
- Consume excessive memory
- Slow down the client
- Transfer unnecessary data

### Behavior
- Queries without `LIMIT` that return >100 rows fail with `LIMIT_REQUIRED` error
- Default limit threshold: 100 rows

### Examples

```bash
# Will fail if table has >100 rows
hologres sql "SELECT * FROM large_table"
# Error: {"ok": false, "error": {"code": "LIMIT_REQUIRED", "message": "Query returns >100 rows, add LIMIT clause"}}

# Solution 1: Add LIMIT
hologres sql "SELECT * FROM large_table LIMIT 50"

# Solution 2: Disable check (use with caution)
hologres sql --no-limit-check "SELECT * FROM large_table"
```

### When to disable
- Exporting full tables (use `hologres data export` instead)
- Aggregation queries (COUNT, SUM, etc.)
- When you explicitly need all rows

## Write Protection

### Purpose
Prevents accidental write operations by requiring explicit intent.

### Behavior
- INSERT, UPDATE, DELETE, TRUNCATE require `--write` flag
- Without flag, these operations fail with `WRITE_GUARD_ERROR`

### Examples

```bash
# Will fail
hologres sql "INSERT INTO logs VALUES (1, 'test')"
# Error: {"ok": false, "error": {"code": "WRITE_GUARD_ERROR", "message": "Write operation requires --write flag"}}

# Correct usage
hologres sql --write "INSERT INTO logs VALUES (1, 'test')"
```

## Dangerous Write Blocking

### Purpose
Prevents mass data modifications that could cause data loss.

### Behavior
- DELETE without WHERE clause is blocked
- UPDATE without WHERE clause is blocked
- Returns `DANGEROUS_WRITE_BLOCKED` error

### Examples

```bash
# Blocked - would delete all rows
hologres sql --write "DELETE FROM users"
# Error: {"ok": false, "error": {"code": "DANGEROUS_WRITE_BLOCKED", "message": "DELETE without WHERE clause is blocked"}}

# Blocked - would update all rows
hologres sql --write "UPDATE users SET status='inactive'"
# Error: {"ok": false, "error": {"code": "DANGEROUS_WRITE_BLOCKED", "message": "UPDATE without WHERE clause is blocked"}}

# Correct usage - specific rows
hologres sql --write "DELETE FROM users WHERE status='deleted'"
hologres sql --write "UPDATE users SET status='inactive' WHERE last_login < '2023-01-01'"
```

### Intentional full-table operations
If you intentionally want to affect all rows:
```bash
# Use WHERE true
hologres sql --write "DELETE FROM temp_table WHERE true"

# Or use TRUNCATE (faster for clearing tables)
hologres sql --write "TRUNCATE TABLE temp_table"
```

## Sensitive Data Masking

### Purpose
Protects sensitive information from being displayed in query results.

### Behavior
Auto-detects sensitive columns by name pattern and masks values:

| Column Pattern | Example Input | Masked Output |
|----------------|---------------|---------------|
| phone, mobile, tel | 13812345678 | `138****5678` |
| email | john@example.com | `j***@example.com` |
| password, secret, token | mysecret123 | `********` |
| id_card, ssn | 110101199001011234 | `110***********1234` |
| bank_card, credit_card | 6222021234567890123 | `***************0123` |

### Disabling masking

```bash
# Disable for specific query
hologres sql --no-mask "SELECT * FROM users LIMIT 10"
```

## Audit Logging

### Purpose
Maintains history of all operations for accountability and debugging.

### Behavior
- All commands logged to `~/.hologres/sql-history.jsonl`
- Includes: timestamp, command, SQL, result status

### Log format
```jsonl
{"timestamp": "2024-01-15T10:30:00Z", "command": "sql", "sql": "SELECT * FROM users LIMIT 10", "ok": true}
{"timestamp": "2024-01-15T10:31:00Z", "command": "sql", "sql": "INSERT INTO logs...", "ok": true, "write": true}
```

### Viewing history
```bash
hologres history
hologres history -n 50
```

## Error Codes Summary

| Code | Trigger | Resolution |
|------|---------|------------|
| `CONNECTION_ERROR` | Cannot connect to database | Check DSN, network, credentials |
| `QUERY_ERROR` | SQL syntax or execution error | Fix SQL statement |
| `LIMIT_REQUIRED` | SELECT without LIMIT, >100 rows | Add LIMIT or use --no-limit-check |
| `WRITE_GUARD_ERROR` | Write operation without --write | Add --write flag |
| `DANGEROUS_WRITE_BLOCKED` | DELETE/UPDATE without WHERE | Add WHERE clause |
| `WRITE_BLOCKED` | Write operation not allowed | Use read-only queries |
| `EXPORT_ERROR` | Data export failed | Check table/query and file path |
| `IMPORT_ERROR` | Data import failed | Check CSV format and table schema |
