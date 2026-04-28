# GRANT/REVOKE Complete Syntax Reference

Complete syntax reference for Hologres privilege management using PostgreSQL standard authorization.

## Privilege Types

| Privilege | Applies To | Description |
|-----------|-----------|-------------|
| `SELECT` | Table, View, Column | Read data |
| `INSERT` | Table | Insert rows |
| `UPDATE` | Table, Column | Modify existing rows |
| `DELETE` | Table | Delete rows |
| `TRUNCATE` | Table | Empty table (faster than DELETE) |
| `REFERENCES` | Table, Column | Create foreign key constraints |
| `TRIGGER` | Table | Create triggers |
| `USAGE` | Schema, Sequence | Access Schema objects / use sequence |
| `CREATE` | Schema, Database | Create objects within |
| `ALL` | Any | All applicable privileges |

## Schema Privileges

### Grant

```sql
-- Grant access to Schema (required for any table operation)
GRANT USAGE ON SCHEMA schema_name TO "user_id";
GRANT USAGE ON SCHEMA schema_name TO role_name;

-- Grant ability to create objects in Schema
GRANT CREATE ON SCHEMA schema_name TO "user_id";

-- Grant both
GRANT CREATE, USAGE ON SCHEMA schema_name TO "user_id";
```

### Revoke

```sql
REVOKE USAGE ON SCHEMA schema_name FROM "user_id";
REVOKE CREATE ON SCHEMA schema_name FROM "user_id";
REVOKE ALL ON SCHEMA schema_name FROM "user_id";
```

## Table Privileges

### Grant on Single Table

```sql
-- Read-only
GRANT SELECT ON TABLE schema_name.table_name TO "user_id";

-- Read-write
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE schema_name.table_name TO "user_id";

-- Full control
GRANT ALL ON TABLE schema_name.table_name TO "user_id";
```

### Grant on All Tables in Schema

```sql
-- All existing tables (does NOT affect future tables)
GRANT SELECT ON ALL TABLES IN SCHEMA public TO "user_id";

-- To all users
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO PUBLIC;
```

### Revoke

```sql
REVOKE SELECT ON TABLE schema_name.table_name FROM "user_id";
REVOKE ALL ON TABLE schema_name.table_name FROM "user_id";
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "user_id";
```

## Column Privileges

Restrict access to specific columns within a table.

### Grant

```sql
-- Grant SELECT on specific columns
GRANT SELECT (column1, column2) ON TABLE schema_name.table_name TO "user_id";

-- Grant UPDATE on specific columns
GRANT UPDATE (column1) ON TABLE schema_name.table_name TO "user_id";
```

### Revoke

```sql
REVOKE SELECT (column1, column2) ON TABLE schema_name.table_name FROM "user_id";
```

> **Note**: Column-level privileges are fine-grained but harder to maintain at scale. Consider using views as an alternative for restricting column access.

## View Privileges

```sql
-- Grant read access to a view
GRANT SELECT ON view_name TO "user_id";

-- Revoke
REVOKE SELECT ON view_name FROM "user_id";
```

## Grant with Transfer (WITH GRANT OPTION)

Allows the grantee to re-grant the same privilege to other users.

```sql
-- Grant SELECT and allow the user to re-grant it
GRANT SELECT ON TABLE schema_name.table_name TO "user_id" WITH GRANT OPTION;
```

To revoke the transfer right (but keep the privilege itself):

```sql
REVOKE GRANT OPTION FOR SELECT ON TABLE schema_name.table_name FROM "user_id";
```

## Owner Transfer

The Owner of an object has full control, including DROP and ALTER. Only Owner or Superuser can perform DDL.

```sql
-- Transfer table ownership to a user
ALTER TABLE schema_name.table_name OWNER TO "user_id";

-- Transfer to a role group (recommended)
ALTER TABLE schema_name.table_name OWNER TO role_name;

-- Transfer Schema ownership
ALTER SCHEMA schema_name OWNER TO "user_id";
```

## Role Management

Roles are groups without login privileges. Use them for organized access control.

```sql
-- Create a role (no login)
CREATE ROLE role_name;

-- Add user to role
GRANT role_name TO "user_id";

-- Remove user from role
REVOKE role_name FROM "user_id";

-- Drop role (must have no members or owned objects)
DROP ROLE role_name;
```

## Default Privileges (ALTER DEFAULT PRIVILEGES)

Configure automatic privileges for objects created in the future.

### Grant Default Privileges

```sql
-- All future tables by user1 in public → everyone can SELECT
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  GRANT SELECT ON TABLES TO PUBLIC;

-- All future tables by user1 in public → user2 gets full access
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  GRANT ALL ON TABLES TO "user2";

-- All future tables by user1 in public → role group gets SELECT
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  GRANT SELECT ON TABLES TO project_view_group;

-- Future sequences
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  GRANT USAGE ON SEQUENCES TO "user2";

-- Future functions
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  GRANT EXECUTE ON FUNCTIONS TO "user2";
```

### Revoke Default Privileges

```sql
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  REVOKE SELECT ON TABLES FROM PUBLIC;

ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  REVOKE ALL ON TABLES FROM "user2";
```

### Important Notes

- `FOR ROLE "X"` means only when user `X` creates the object
- Only applies to TABLE, SCHEMA, FUNCTION, SEQUENCE, or TYPE
- Does **not** affect already existing objects
- When using `SET SESSION ROLE group1;`, the creating role becomes `group1`
- Changing table Owner after creation does **not** trigger default privilege rules

## Catalog Row-Level Security (V3.0+)

Starting from V3.0, Hologres supports row-level security on system catalog tables. When enabled, users can only see metadata (in `pg_class`, `pg_namespace`, etc.) for objects they have privileges on.

```sql
-- Enable catalog RLS (Superuser, once per database)
ALTER DATABASE database_name SET hg_experimental_enable_catalog_rls = on;

-- Disable
ALTER DATABASE database_name SET hg_experimental_enable_catalog_rls = off;
```

After enabling:
- Superusers see all metadata
- Object Owners see their own objects
- Users with any privilege on an object can see its metadata
- Users without privileges cannot see the object in `pg_class`
