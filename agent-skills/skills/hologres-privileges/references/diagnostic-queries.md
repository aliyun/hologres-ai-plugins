# Permission Diagnostic SQL Collection

Ready-to-use SQL queries for diagnosing and auditing Hologres permissions.

## Roles and Users

### List All Roles

```sql
SELECT rolname,
       rolsuper AS is_super,
       rolcanlogin AS can_login,
       rolcreatedb AS can_createdb,
       rolcreaterole AS can_createrole
FROM pg_roles
ORDER BY rolname;
```

### Show Display Names (Alibaba Cloud accounts)

```sql
SELECT rolname, user_display_name(rolname) AS display_name
FROM pg_roles
WHERE rolcanlogin = true
ORDER BY rolname;
```

### Check Role Membership

```sql
-- Which roles does a user belong to?
SELECT r.rolname AS role,
       m.rolname AS member
FROM pg_auth_members am
JOIN pg_roles r ON r.oid = am.roleid
JOIN pg_roles m ON m.oid = am.member
WHERE m.rolname = 'user_id'
ORDER BY r.rolname;
```

### Check if a User Belongs to a Role

```sql
SELECT pg_has_role('user_id', 'role_name', 'MEMBER') AS is_member;
```

## Table Privilege Checks

### Check Specific Privilege on a Table

```sql
-- Returns true/false
SELECT has_table_privilege('user_id', 'schema.table', 'SELECT');
SELECT has_table_privilege('user_id', 'schema.table', 'INSERT');
SELECT has_table_privilege('user_id', 'schema.table', 'UPDATE');
SELECT has_table_privilege('user_id', 'schema.table', 'DELETE');
```

### List All Table Grants for a User

```sql
SELECT table_schema, table_name, privilege_type, is_grantable
FROM information_schema.role_table_grants
WHERE grantee = 'user_id'
ORDER BY table_schema, table_name, privilege_type;
```

### Find All Users with Privileges on a Table

```sql
SELECT rolname,
       has_table_privilege(rolname, 'schema.table', 'SELECT') AS select,
       has_table_privilege(rolname, 'schema.table', 'INSERT') AS insert,
       has_table_privilege(rolname, 'schema.table', 'UPDATE') AS update,
       has_table_privilege(rolname, 'schema.table', 'DELETE') AS delete
FROM pg_roles
WHERE has_table_privilege(rolname, 'schema.table',
  'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
ORDER BY rolname;
```

### List All Tables a User Can Access

```sql
SELECT nc.nspname AS schema, c.relname AS table_name
FROM pg_namespace nc
JOIN pg_class c ON nc.oid = c.relnamespace
WHERE c.relkind IN ('r', 'v')
  AND nc.nspname NOT IN ('pg_catalog', 'information_schema', 'hologres')
  AND (
    pg_has_role('user_id', c.relowner, 'USAGE')
    OR has_table_privilege('user_id', c.oid, 'SELECT')
  )
ORDER BY nc.nspname, c.relname;
```

## Schema Privilege Checks

### Check Schema Privileges

```sql
SELECT has_schema_privilege('user_id', 'schema_name', 'USAGE') AS has_usage;
SELECT has_schema_privilege('user_id', 'schema_name', 'CREATE') AS has_create;
```

### List All Schemas a User Can Access

```sql
SELECT nspname AS schema_name
FROM pg_namespace
WHERE has_schema_privilege('user_id', nspname, 'USAGE')
  AND nspname NOT LIKE 'pg_%'
  AND nspname != 'information_schema'
ORDER BY nspname;
```

## Default Privilege Checks

### View Configured Default Privileges

```sql
SELECT pg_catalog.pg_get_userbyid(d.defaclrole) AS "Owner",
  n.nspname AS "Schema",
  CASE d.defaclobjtype
    WHEN 'r' THEN 'table'
    WHEN 'S' THEN 'sequence'
    WHEN 'f' THEN 'function'
    WHEN 'T' THEN 'type'
    WHEN 'n' THEN 'schema'
  END AS "Type",
  pg_catalog.array_to_string(d.defaclacl, E'\n') AS "Access privileges"
FROM pg_catalog.pg_default_acl d
LEFT JOIN pg_catalog.pg_namespace n ON n.oid = d.defaclnamespace
ORDER BY 1, 2, 3;
```

### ACL String Quick Reference

ACL format: `grantee=privileges/grantor`

| Character | Privilege |
|-----------|-----------|
| `r` | SELECT (read) |
| `w` | UPDATE (write) |
| `a` | INSERT (append) |
| `d` | DELETE |
| `D` | TRUNCATE |
| `x` | REFERENCES |
| `t` | TRIGGER |
| `U` | USAGE |
| `C` | CREATE |
| `*` | Grant option for preceding privilege |

Example: `user1=r/admin` means `user1` has SELECT, granted by `admin`.

## Owner Queries

### Find Owner of a Table

```sql
SELECT n.nspname AS schema, c.relname AS table_name,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relname = 'table_name'
  AND n.nspname = 'schema_name';
```

### List All Table Owners in a Schema

```sql
SELECT c.relname AS table_name,
       pg_get_userbyid(c.relowner) AS owner
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'schema_name'
  AND c.relkind = 'r'
ORDER BY c.relname;
```

## Comprehensive Audit: Full User Permission Profile

```sql
-- Complete privilege report for a specific user across all schemas
WITH user_tables AS (
  SELECT table_schema, table_name,
         array_agg(privilege_type ORDER BY privilege_type) AS privileges
  FROM information_schema.role_table_grants
  WHERE grantee = 'user_id'
  GROUP BY table_schema, table_name
)
SELECT table_schema AS schema,
       table_name AS table,
       array_to_string(privileges, ', ') AS granted_privileges
FROM user_tables
ORDER BY table_schema, table_name;
```
