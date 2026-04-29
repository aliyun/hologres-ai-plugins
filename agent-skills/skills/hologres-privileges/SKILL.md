---
name: hologres-privileges
description: |
  Hologres privilege management using PostgreSQL standard authorization model (expert permission model).
  Use for creating users, granting/revoking Schema/table/column/view privileges, configuring default
  privileges for future objects, diagnosing permission issues, and planning role-based access control.
  Triggers: "hologres权限", "hologres grant", "hologres revoke", "permission denied", "权限管理",
  "hologres privileges", "hologres authorization", "default privileges", "角色权限", "授权"
---

## Prerequisites

This skill requires **hologres-cli** to be installed first:

```bash
pip install hologres-cli
```

All SQL execution depends on `hologres-cli` commands (`hologres sql run --write`).

# Hologres Privilege Management (Expert Permission Model)

Manage fine-grained access control in Hologres using standard PostgreSQL GRANT/REVOKE syntax.

## Permission Model Overview

Hologres provides three permission models. **This skill focuses on the Expert Model.**

| Model | Granularity | Use Case |
|-------|------------|----------|
| **Expert (PostgreSQL Standard)** | Table/Column/View level | Fine-grained control, per-table/per-user |
| SPM (Simple Permission Model) | Database level | Quick setup, 4 preset role groups |
| SLPM (Schema-Level Permission Model) | Schema level | Multi-team isolation with simplified management |

> The expert model uses standard PostgreSQL `GRANT`/`REVOKE` syntax. It only applies to **existing objects** — use `ALTER DEFAULT PRIVILEGES` for future objects.

## Quick Start

```sql
-- 1. Create user (RAM user format: p4_<uid>)
CREATE USER "p4_1822780xxx";

-- 2. Grant Schema access (required for any table query)
GRANT USAGE ON SCHEMA public TO "p4_1822780xxx";

-- 3. Grant table read permission
GRANT SELECT ON TABLE public.orders TO "p4_1822780xxx";

-- 4. Verify permission
SELECT has_table_privilege('p4_1822780xxx', 'public.orders', 'SELECT');
```

## User Management

### Account Types

| Type | Format | Example |
|------|--------|---------|
| Alibaba Cloud main account | Numeric UID | `11822780xxx` |
| RAM sub-account | `p4_` + UID | `p4_1822780xxx` |
| Custom user (BASIC) | `BASIC$` + name | `BASIC$dev_user` |

### Create Users

```sql
-- Create user with login privilege
CREATE USER "p4_1822780xxx";

-- Create user as Superuser
CREATE USER "p4_1822780xxx" SUPERUSER;

-- Create custom user with password
CREATE USER "BASIC$dev_user" WITH PASSWORD 'secure_password';
```

### Alter Users

```sql
-- Promote to Superuser
ALTER USER "p4_1822780xxx" SUPERUSER;

-- Demote to normal user
ALTER USER "p4_1822780xxx" NOSUPERUSER;

-- Change custom user password
ALTER USER "BASIC$dev_user" WITH PASSWORD 'new_password';
```

### Delete Users

```sql
-- Drop user (no owned objects)
DROP USER "p4_1822780xxx";

-- Drop user with owned objects (transfer first)
REASSIGN OWNED BY "p4_old_uid" TO "p4_new_uid";
DROP USER "p4_old_uid";
```

## Core Grant Syntax

### Schema Privileges

```sql
-- Grant Schema access (required before any table query)
GRANT USAGE ON SCHEMA schema_name TO "user_id";

-- Grant ability to create tables in Schema
GRANT CREATE ON SCHEMA schema_name TO "user_id";
```

### Table Privileges

```sql
-- Grant specific privileges on a single table
GRANT SELECT ON TABLE schema_name.table_name TO "user_id";
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE schema_name.table_name TO "user_id";

-- Grant on all existing tables in a Schema
GRANT SELECT ON ALL TABLES IN SCHEMA public TO "user_id";

-- Grant to all users
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA public TO PUBLIC;
```

### Column Privileges

```sql
-- Grant SELECT on specific columns only
GRANT SELECT (column1, column2) ON TABLE schema_name.table_name TO "user_id";
```

### View Privileges

```sql
GRANT SELECT ON view_name TO "user_id";
```

### Grant with Transfer (WITH GRANT OPTION)

```sql
-- Allow the grantee to re-grant this privilege to others
GRANT SELECT ON TABLE schema_name.table_name TO "user_id" WITH GRANT OPTION;
```

### Owner Transfer

Only the table Owner or Superuser can DROP/ALTER a table.

```sql
-- Transfer table ownership
ALTER TABLE schema_name.table_name OWNER TO "user_id";

-- Transfer ownership to a role group
ALTER TABLE schema_name.table_name OWNER TO role_name;
```

## Default Privileges (Future Objects)

`GRANT` only applies to existing objects. Use `ALTER DEFAULT PRIVILEGES` so that future tables automatically inherit permissions.

```sql
-- All future tables created by user1 in public schema are readable by everyone
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  GRANT SELECT ON TABLES TO PUBLIC;

-- Only user2 can read future tables created by user1
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  GRANT SELECT ON TABLES TO "user2";

-- Revoke a default privilege rule
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA public
  REVOKE SELECT ON TABLES FROM PUBLIC;

-- Check current default privilege settings
SELECT pg_catalog.pg_get_userbyid(d.defaclrole) AS "Owner",
  n.nspname AS "Schema",
  CASE d.defaclobjtype
    WHEN 'r' THEN 'table' WHEN 'S' THEN 'sequence'
    WHEN 'f' THEN 'function' WHEN 'T' THEN 'type'
  END AS "Type",
  pg_catalog.array_to_string(d.defaclacl, E'\n') AS "Access privileges"
FROM pg_catalog.pg_default_acl d
LEFT JOIN pg_catalog.pg_namespace n ON n.oid = d.defaclnamespace
ORDER BY 1, 2, 3;
```

> **Important**: `ALTER DEFAULT PRIVILEGES FOR ROLE "X"` only applies when user `X` creates the object. If another user creates tables, the rule does not trigger.

## Revoke Privileges

| Scope | SQL |
|-------|-----|
| Single table | `REVOKE SELECT ON TABLE schema.table FROM "user_id";` |
| All tables in Schema | `REVOKE ALL ON ALL TABLES IN SCHEMA public FROM "user_id";` |
| Schema access | `REVOKE USAGE ON SCHEMA schema_name FROM "user_id";` |
| Column privilege | `REVOKE SELECT (col1) ON TABLE schema.table FROM "user_id";` |

## Permission Diagnostics Quick Reference

```sql
-- List all roles with key attributes
SELECT rolname, rolsuper, rolcanlogin FROM pg_roles;

-- Check if a user has SELECT on a specific table
SELECT has_table_privilege('user_id', 'schema.table', 'SELECT');

-- List all table grants for a specific role
SELECT table_schema, table_name, privilege_type
FROM information_schema.role_table_grants
WHERE grantee = 'user_id';

-- Find all users with any privilege on a specific table
SELECT rolname FROM pg_roles
WHERE has_table_privilege(rolname, 'schema.table', 'SELECT');
```

For more diagnostic queries, see [diagnostic-queries.md](references/diagnostic-queries.md).

## Common Errors and Troubleshooting

| Error | Cause | Solution |
|-------|-------|----------|
| `permission denied for table xxx` | Missing table privilege | `GRANT SELECT ON TABLE xxx TO "user";` |
| `must be the owner of table xxx` | Non-owner attempting DDL | `ALTER TABLE xxx OWNER TO "user";` |
| `permission denied for Schema xxx` | Missing Schema USAGE | `GRANT USAGE ON SCHEMA xxx TO "user";` |

## References

| Document | Content |
|----------|---------|
| [grant-revoke-reference.md](references/grant-revoke-reference.md) | Complete GRANT/REVOKE syntax reference |
| [diagnostic-queries.md](references/diagnostic-queries.md) | Permission diagnostic SQL collection |
| [best-practices.md](references/best-practices.md) | Role group planning best practices |

## Best Practices

1. **Never use the main account for business queries** — create dedicated users
2. **Always GRANT USAGE ON SCHEMA first** — without it, no table queries work
3. **Use role groups instead of per-user grants** — create `project_dev`, `project_write`, `project_view` roles
4. **Use ALTER DEFAULT PRIVILEGES for future tables** — combine with `GRANT ON ALL TABLES` for existing tables
5. **Regularly audit permissions** with diagnostic SQL from [diagnostic-queries.md](references/diagnostic-queries.md)
6. **Transfer ownership before dropping users** — use `REASSIGN OWNED BY`
7. **Enable catalog RLS on V3.0+** to protect metadata visibility (`hg_experimental_enable_catalog_rls`)
