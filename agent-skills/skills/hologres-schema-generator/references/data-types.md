# Hologres Data Types Reference

## Numeric Types

| Type | Alias | Size | Range | Notes |
|------|-------|------|-------|-------|
| `SMALLINT` | `INT2` | 2 bytes | -32768 ~ 32767 | |
| `INTEGER` | `INT`, `INT4` | 4 bytes | -2^31 ~ 2^31-1 | Most common integer |
| `BIGINT` | `INT8` | 8 bytes | -2^63 ~ 2^63-1 | Recommended for IDs |
| `SERIAL` | - | 4 bytes | Auto-increment | Avoid as PK (causes table lock) |
| `BIGSERIAL` | - | 8 bytes | Auto-increment | Avoid as PK (causes table lock) |
| `REAL` | `FLOAT4` | 4 bytes | 6 decimal digits precision | Cannot be PK |
| `DOUBLE PRECISION` | `FLOAT8` | 8 bytes | 15 decimal digits precision | Cannot be PK |
| `NUMERIC(p,s)` | `DECIMAL(p,s)` | Variable | p: 1~38, s: 0~p | Cannot be PK; best for monetary values |
| `MONEY` | - | 8 bytes | -922337203685477.5808 ~ 922337203685477.5807 | Two decimal places |
| `BOOLEAN` | `BOOL` | 1 byte | TRUE / FALSE / NULL | |

## String / Character Types

| Type | Description | Max Length | Notes |
|------|-------------|-----------|-------|
| `TEXT` | Variable-length string | Unlimited | Recommended for most text columns |
| `VARCHAR(n)` | Variable-length with limit | n characters | Functionally same as TEXT with check |
| `CHAR(n)` | Fixed-length, blank-padded | n characters | Space padded; rarely needed |

> **Recommendation:** Always use `TEXT` unless you have a specific reason for `VARCHAR(n)`.

## Date / Time Types

| Type | Size | Resolution | Range | Notes |
|------|------|-----------|-------|-------|
| `DATE` | 4 bytes | 1 day | 4713 BC ~ 5874897 AD | Date only |
| `TIMESTAMP` | 8 bytes | 1 microsecond | 4713 BC ~ 294276 AD | Without timezone |
| `TIMESTAMPTZ` | 8 bytes | 1 microsecond | 4713 BC ~ 294276 AD | **Recommended** for event time |
| `TIME` | 8 bytes | 1 microsecond | 00:00:00 ~ 24:00:00 | Time only, no date |
| `TIMETZ` | 12 bytes | 1 microsecond | 00:00:00+1559 ~ 24:00:00-1559 | Time with timezone |
| `INTERVAL` | 16 bytes | 1 microsecond | -178000000 ~ 178000000 years | Time interval |

> **Recommendation:** Use `TIMESTAMPTZ` instead of `TIMESTAMP` for event timestamps to avoid timezone issues.

## Binary Types

| Type | Description | Notes |
|------|-------------|-------|
| `BYTEA` | Variable-length binary data | For binary blobs, images, serialized objects |

## Network Types

| Type | Description | Notes |
|------|-------------|-------|
| `INET` | IPv4 / IPv6 host address | Supports CIDR notation |

## Identifier Types

| Type | Description | Notes |
|------|-------------|-------|
| `UUID` | 128-bit universally unique identifier | `gen_random_uuid()` to generate |
| `OID` | Object identifier | Internal PostgreSQL type |

## JSON Types

| Type | Description | Notes |
|------|-------------|-------|
| `JSON` | Text JSON | Stores as-is, re-parses on access |
| `JSONB` | Binary JSON | **Recommended**; indexed, faster queries |

```sql
-- JSONB usage examples
CREATE TABLE events (
  id BIGINT PRIMARY KEY,
  payload JSONB
) WITH (orientation = 'column');

-- Query nested fields
SELECT payload->>'user_id' FROM events WHERE payload->>'type' = 'click';
SELECT payload->'address'->>'city' FROM events;
```

> **Note:** JSONB cannot be used as PK, distribution_key, clustering_key, or partition column.

## Bit String Types

| Type | Description | Notes |
|------|-------------|-------|
| `BIT(n)` | Fixed-length bit string | Exactly n bits |
| `VARBIT(n)` | Variable-length bit string | Up to n bits |

## Array Types

Hologres supports one-dimensional arrays of the following base types:

| Array Type | Base Type |
|-----------|-----------|
| `INT4[]` | INTEGER |
| `INT8[]` | BIGINT |
| `FLOAT4[]` | REAL |
| `FLOAT8[]` | DOUBLE PRECISION |
| `BOOLEAN[]` | BOOLEAN |
| `TEXT[]` | TEXT |
| `NUMERIC[]` | NUMERIC |

```sql
-- Array column example
CREATE TABLE user_tags (
  user_id BIGINT NOT NULL PRIMARY KEY,
  tags TEXT[],
  scores FLOAT8[]
) WITH (orientation = 'column');

-- Query
SELECT * FROM user_tags WHERE 'vip' = ANY(tags);
SELECT * FROM user_tags WHERE tags @> ARRAY['vip','active'];
```

> **Note:** Array columns cannot be PK, distribution_key, clustering_key, or partition column.

## Extension Types

| Type | Extension | Description | Notes |
|------|-----------|-------------|-------|
| `RoaringBitmap` | `roaringbitmap` | Compressed bitmap | UV/PV dedup; requires `CREATE EXTENSION roaringbitmap` |
| `PostGIS types` | `postgis` | Geometry/Geography | Spatial queries; requires `CREATE EXTENSION postgis` |

## Data Type Selection Guide

### For Primary Key

| Scenario | Recommended Type |
|----------|-----------------|
| Numeric ID | `BIGINT` |
| Composite key (date + id) | `TEXT` + `BIGINT` |
| Natural key | `TEXT` or `VARCHAR` |

**Prohibited as PK:** `FLOAT`, `DOUBLE PRECISION`, `NUMERIC`, `ARRAY`, `JSON`, `JSONB`

### For Distribution Key

| Scenario | Recommended Type |
|----------|-----------------|
| User/Order ID | `BIGINT` |
| String-based ID | `TEXT` |

**Prohibited as distribution_key:** `FLOAT`, `DOUBLE PRECISION`, `ARRAY`, `JSON`, `JSONB`

### For Partition Column

| Scenario | Recommended Type |
|----------|-----------------|
| Date string (yyyyMMdd) | `TEXT` |
| Date type | `DATE` (V1.3.22+) |
| Category ID | `INT` |

**Supported partition types:** `TEXT`, `VARCHAR`, `INT`, `BIGINT`, `DATE`

### For Clustering Key

| Scenario | Recommended Type |
|----------|-----------------|
| Time range query | `TIMESTAMPTZ`, `DATE`, `TEXT` (date string) |
| Category filtering | `TEXT`, `INT` |

### For Bitmap Columns

| Good candidates | Bad candidates |
|----------------|---------------|
| status, type, region (low cardinality) | user_id, order_id (high cardinality) |
| TEXT columns (auto-enabled by default) | Numeric IDs |

## Type Conversion Functions

```sql
-- Common casts
column::BIGINT       -- to BIGINT
column::TEXT         -- to TEXT
column::TIMESTAMPTZ  -- to TIMESTAMPTZ
column::DATE         -- to DATE
column::JSONB        -- to JSONB

-- Explicit cast syntax
CAST(column AS BIGINT)
CAST(column AS TIMESTAMPTZ)
```
