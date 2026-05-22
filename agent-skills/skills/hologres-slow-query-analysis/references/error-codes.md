# Hologres/PostgreSQL Error Codes Reference

## Error Code Extraction

Extract error codes from `hg_query_log.message` field:

```sql
ltrim(split_part(message, ': ', 2), ' ') AS error_code
```

This extracts the 5-character SQLSTATE code (e.g., `XX000`, `53200`, `57014`).

## Error Code → Type Mapping

### Class 08 - Connection Exception

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `08000` | ERRCODE_CONNECTION_EXCEPTION | connection_exception |
| `08003` | ERRCODE_CONNECTION_DOES_NOT_EXIST | connection_does_not_exist |
| `08006` | ERRCODE_CONNECTION_FAILURE | connection_failure |
| `08001` | ERRCODE_SQLCLIENT_UNABLE_TO_ESTABLISH_SQLCONNECTION | sqlclient_unable_to_establish_sqlconnection |
| `08004` | ERRCODE_SQLSERVER_REJECTED_ESTABLISHMENT_OF_SQLCONNECTION | sqlserver_rejected_establishment_of_sqlconnection |
| `08P01` | ERRCODE_PROTOCOL_VIOLATION | protocol_violation |
| `08P02` | ERRCODE_IDLE_SESSION_TIMEOUT | idle_session_timeout |

### Class 22 - Data Exception

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `22000` | ERRCODE_DATA_EXCEPTION | data_exception |
| `22012` | ERRCODE_DIVISION_BY_ZERO | division_by_zero |
| `22001` | ERRCODE_STRING_DATA_RIGHT_TRUNCATION | string_data_right_truncation |
| `22003` | ERRCODE_NUMERIC_VALUE_OUT_OF_RANGE | numeric_value_out_of_range |
| `22007` | ERRCODE_INVALID_DATETIME_FORMAT | invalid_datetime_format |
| `22008` | ERRCODE_DATETIME_FIELD_OVERFLOW | datetime_field_overflow |
| `22023` | ERRCODE_INVALID_PARAMETER_VALUE | invalid_parameter_value |
| `22004` | ERRCODE_NULL_VALUE_NOT_ALLOWED | null_value_not_allowed |
| `22P02` | ERRCODE_INVALID_TEXT_REPRESENTATION | invalid_text_representation |

### Class 23 - Integrity Constraint Violation

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `23000` | ERRCODE_INTEGRITY_CONSTRAINT_VIOLATION | integrity_constraint_violation |
| `23502` | ERRCODE_NOT_NULL_VIOLATION | not_null_violation |
| `23503` | ERRCODE_FOREIGN_KEY_VIOLATION | foreign_key_violation |
| `23505` | ERRCODE_UNIQUE_VIOLATION | unique_violation |
| `23514` | ERRCODE_CHECK_VIOLATION | check_violation |
| `23P01` | ERRCODE_EXCLUSION_VIOLATION | exclusion_violation |

### Class 25 - Invalid Transaction State

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `25000` | ERRCODE_INVALID_TRANSACTION_STATE | invalid_transaction_state |
| `25006` | ERRCODE_READ_ONLY_SQL_TRANSACTION | read_only_sql_transaction |
| `25P02` | ERRCODE_IN_FAILED_SQL_TRANSACTION | in_failed_sql_transaction |
| `25P03` | ERRCODE_IDLE_IN_TRANSACTION_SESSION_TIMEOUT | idle_in_transaction_session_timeout |

### Class 28 - Invalid Authorization Specification

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `28000` | ERRCODE_INVALID_AUTHORIZATION_SPECIFICATION | invalid_authorization_specification |
| `28P01` | ERRCODE_INVALID_PASSWORD | invalid_password |

### Class 40 - Transaction Rollback

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `40000` | ERRCODE_TRANSACTION_ROLLBACK | transaction_rollback |
| `40001` | ERRCODE_T_R_SERIALIZATION_FAILURE | serialization_failure |
| `40P01` | ERRCODE_T_R_DEADLOCK_DETECTED | deadlock_detected |
| `40003` | ERRCODE_T_R_STATEMENT_COMPLETION_UNKNOWN | statement_completion_unknown |

### Class 42 - Syntax Error or Access Rule Violation

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `42601` | ERRCODE_SYNTAX_ERROR | syntax_error |
| `42501` | ERRCODE_INSUFFICIENT_PRIVILEGE | insufficient_privilege |
| `42P01` | ERRCODE_UNDEFINED_TABLE | undefined_table |
| `42703` | ERRCODE_UNDEFINED_COLUMN | undefined_column |
| `42883` | ERRCODE_UNDEFINED_FUNCTION | undefined_function |
| `42P07` | ERRCODE_DUPLICATE_TABLE | duplicate_table |
| `42710` | ERRCODE_DUPLICATE_OBJECT | duplicate_object |
| `42804` | ERRCODE_DATATYPE_MISMATCH | datatype_mismatch |
| `42P16` | ERRCODE_INVALID_TABLE_DEFINITION | invalid_table_definition |
| `42809` | ERRCODE_WRONG_OBJECT_TYPE | wrong_object_type |

### Class 53 - Insufficient Resources

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `53000` | ERRCODE_INSUFFICIENT_RESOURCES | insufficient_resources |
| `53100` | ERRCODE_DISK_FULL | disk_full |
| `53200` | ERRCODE_OUT_OF_MEMORY | out_of_memory |
| `53300` | ERRCODE_TOO_MANY_CONNECTIONS | too_many_connections |
| `53400` | ERRCODE_CONFIGURATION_LIMIT_EXCEEDED | configuration_limit_exceeded |

### Class 54 - Program Limit Exceeded

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `54000` | ERRCODE_PROGRAM_LIMIT_EXCEEDED | program_limit_exceeded |
| `54001` | ERRCODE_STATEMENT_TOO_COMPLEX | statement_too_complex |
| `54011` | ERRCODE_TOO_MANY_COLUMNS | too_many_columns |
| `54023` | ERRCODE_TOO_MANY_ARGUMENTS | too_many_arguments |

### Class 55 - Object Not In Prerequisite State

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `55000` | ERRCODE_OBJECT_NOT_IN_PREREQUISITE_STATE | object_not_in_prerequisite_state |
| `55006` | ERRCODE_OBJECT_IN_USE | object_in_use |
| `55P02` | ERRCODE_CANT_CHANGE_RUNTIME_PARAM | cant_change_runtime_param |
| `55P03` | ERRCODE_LOCK_NOT_AVAILABLE | lock_not_available |

### Class 57 - Operator Intervention

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `57000` | ERRCODE_OPERATOR_INTERVENTION | operator_intervention |
| `57014` | ERRCODE_QUERY_CANCELED | query_canceled |
| `57P01` | ERRCODE_ADMIN_SHUTDOWN | admin_shutdown |
| `57P02` | ERRCODE_CRASH_SHUTDOWN | crash_shutdown |
| `57P03` | ERRCODE_CANNOT_CONNECT_NOW | cannot_connect_now |
| `57P04` | ERRCODE_DATABASE_DROPPED | database_dropped |

### Class 58 - System Error

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `58000` | ERRCODE_SYSTEM_ERROR | system_error |
| `58030` | ERRCODE_IO_ERROR | io_error |
| `58P01` | ERRCODE_UNDEFINED_FILE | undefined_file |

### Class P0 - PL/pgSQL Error

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `P0000` | ERRCODE_PLPGSQL_ERROR | plpgsql_error |
| `P0001` | ERRCODE_RAISE_EXCEPTION | raise_exception |
| `P0002` | ERRCODE_NO_DATA_FOUND | no_data_found |
| `P0003` | ERRCODE_TOO_MANY_ROWS | too_many_rows |

### Class HG - Hologres Specific

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `HG000` | ERRCODE_HG_NEED_RETRY | hg_need_retry |
| `HG001` | ERRCODE_HG_PLPGSQL_NEED_RETRY | hg_plpgsql_need_retry |

### Class XX - Internal Error

| SQLSTATE | Error Type | Description |
| :--- | :--- | :--- |
| `XX000` | ERRCODE_INTERNAL_ERROR | internal_error |
| `XX001` | ERRCODE_DATA_CORRUPTED | data_corrupted |
| `XX002` | ERRCODE_INDEX_CORRUPTED | index_corrupted |

## Diagnostic SQL: Error Code Distribution

```sql
-- Group failed queries by error code (past 3 hours)
SELECT ltrim(split_part(message, ': ', 2), ' ') AS error_code,
       count(*) AS error_count,
       min(query_start) AS first_seen,
       max(query_start) AS last_seen,
       count(DISTINCT usename) AS affected_users
FROM hologres.hg_query_log
WHERE query_start >= now() - interval '3 h'
  AND status = 'FAILED'
GROUP BY 1
ORDER BY 2 DESC
LIMIT 20;
```

## Error Code Class Summary

| Class Prefix | Category | Severity |
| :--- | :--- | :--- |
| `08` | Connection | High - connectivity issues |
| `22` | Data Exception | Medium - data quality/format |
| `23` | Constraint Violation | Medium - data integrity |
| `25` | Transaction State | Medium - transaction management |
| `40` | Transaction Rollback | High - concurrency conflict |
| `42` | Syntax/Access | Low-Medium - user error |
| `53` | Insufficient Resources | **Critical** - system capacity |
| `54` | Program Limit | Medium - query complexity |
| `55` | Object State | Medium - DDL conflict |
| `57` | Operator Intervention | High - system operations |
| `58` | System Error | **Critical** - infrastructure |
| `HG` | Hologres Specific | Medium - transient, retry |
| `XX` | Internal Error | **Critical** - engine bug |
