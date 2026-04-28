# Privilege Management Best Practices

Role group planning methodology and operational workflows for Hologres expert permission model.

## Role Group Design Principles

### Why Role Groups?

Granting privileges to individual users is error-prone and hard to maintain. Role groups provide:
- **Centralized control** — change the group, all members inherit the change
- **Scalable onboarding** — new users just need `GRANT role TO user`
- **Clear access tiers** — each group has a well-defined permission boundary

### Three-Tier Role Group Pattern

For each project or business domain, create three role groups:

| Role Group | Naming Convention | Privileges |
|------------|-------------------|------------|
| **Dev** | `<project>_dev` | CREATE + USAGE on Schema, ALL on tables, OWNER of objects |
| **Write** | `<project>_write` | USAGE on Schema, SELECT + INSERT + UPDATE + DELETE on tables |
| **View** | `<project>_view` | USAGE on Schema, SELECT on tables |

```sql
-- Example: project "analytics"
CREATE ROLE analytics_dev;
CREATE ROLE analytics_write;
CREATE ROLE analytics_view;
```

## Recommended Setup Workflow

### Step 1: Create Role Groups

```sql
CREATE ROLE analytics_dev;
CREATE ROLE analytics_write;
CREATE ROLE analytics_view;
```

### Step 2: Grant Schema Privileges to Groups

```sql
-- Dev: full Schema control
GRANT CREATE, USAGE ON SCHEMA analytics TO analytics_dev;

-- Write + View: access only
GRANT USAGE ON SCHEMA analytics TO analytics_write;
GRANT USAGE ON SCHEMA analytics TO analytics_view;
```

### Step 3: Grant Table Privileges (Existing Tables)

```sql
-- Dev: full control on all existing tables
GRANT ALL ON ALL TABLES IN SCHEMA analytics TO analytics_dev;

-- Write: read-write
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA analytics TO analytics_write;

-- View: read-only
GRANT SELECT ON ALL TABLES IN SCHEMA analytics TO analytics_view;
```

### Step 4: Configure Default Privileges (Future Tables)

This ensures tables created later automatically inherit privileges:

```sql
-- For each developer who creates tables, run:
ALTER DEFAULT PRIVILEGES FOR ROLE "developer_user1" IN SCHEMA analytics
  GRANT ALL ON TABLES TO analytics_dev;

ALTER DEFAULT PRIVILEGES FOR ROLE "developer_user1" IN SCHEMA analytics
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO analytics_write;

ALTER DEFAULT PRIVILEGES FOR ROLE "developer_user1" IN SCHEMA analytics
  GRANT SELECT ON TABLES TO analytics_view;
```

> Repeat for each developer who creates tables in this Schema.

### Step 5: Add Users to Groups

```sql
-- Developers
GRANT analytics_dev TO "p4_dev_user1";
GRANT analytics_dev TO "p4_dev_user2";

-- Data writers (ETL accounts, etc.)
GRANT analytics_write TO "p4_etl_account";

-- Analysts (read-only)
GRANT analytics_view TO "p4_analyst1";
GRANT analytics_view TO "p4_analyst2";
```

### Step 6: Transfer Table Ownership (Optional)

For shared ownership, transfer tables to the dev group:

```sql
ALTER TABLE analytics.report_daily OWNER TO analytics_dev;
```

## Existing Tables vs Future Tables

| Scope | Command | When to Use |
|-------|---------|-------------|
| Existing tables | `GRANT ... ON ALL TABLES IN SCHEMA` | One-time setup, covers current tables |
| Future tables | `ALTER DEFAULT PRIVILEGES FOR ROLE ...` | Ongoing, covers tables created later |

**Always use both together** for complete coverage:

```sql
-- Existing tables
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analytics_view;

-- Future tables (for each creator)
ALTER DEFAULT PRIVILEGES FOR ROLE "creator_user" IN SCHEMA public
  GRANT SELECT ON TABLES TO analytics_view;
```

## Cross-Schema Management

When a project spans multiple schemas:

```sql
-- Repeat grants for each Schema
GRANT USAGE ON SCHEMA schema1 TO analytics_view;
GRANT USAGE ON SCHEMA schema2 TO analytics_view;
GRANT SELECT ON ALL TABLES IN SCHEMA schema1 TO analytics_view;
GRANT SELECT ON ALL TABLES IN SCHEMA schema2 TO analytics_view;

-- Default privileges per Schema per creator
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA schema1
  GRANT SELECT ON TABLES TO analytics_view;
ALTER DEFAULT PRIVILEGES FOR ROLE "user1" IN SCHEMA schema2
  GRANT SELECT ON TABLES TO analytics_view;
```

## Audit and Periodic Review

### Recommended Checks

| Check | Frequency | Query |
|-------|-----------|-------|
| Users with Superuser | Weekly | `SELECT rolname FROM pg_roles WHERE rolsuper;` |
| Orphaned roles (no login, no members) | Monthly | See below |
| Tables with no explicit grants | Monthly | See below |
| Default privilege coverage | After team changes | `\ddp` or `pg_default_acl` query |

### Find Orphaned Roles

```sql
SELECT r.rolname
FROM pg_roles r
WHERE NOT r.rolcanlogin
  AND NOT r.rolsuper
  AND NOT EXISTS (
    SELECT 1 FROM pg_auth_members am WHERE am.roleid = r.oid
  )
  AND r.rolname NOT LIKE 'pg_%';
```

### Find Tables Without Explicit Grants

```sql
SELECT n.nspname AS schema, c.relname AS table_name
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind = 'r'
  AND n.nspname NOT IN ('pg_catalog', 'information_schema', 'hologres')
  AND c.relacl IS NULL
ORDER BY n.nspname, c.relname;
```

## Common Anti-Patterns

| Anti-Pattern | Problem | Recommended Alternative |
|-------------|---------|------------------------|
| Granting SUPERUSER to all developers | No access control, security risk | Create dev role group with targeted privileges |
| Per-user table grants without role groups | Unmaintainable as team grows | Use role groups (dev/write/view pattern) |
| Only using `GRANT ON ALL TABLES` without `ALTER DEFAULT PRIVILEGES` | New tables have no grants | Always configure both existing + default |
| Not granting USAGE ON SCHEMA | Users get "permission denied" despite table grants | Always grant Schema USAGE first |
| Dropping users without `REASSIGN OWNED BY` | Orphaned objects, broken ownership | Transfer ownership before dropping |
