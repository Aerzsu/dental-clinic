# Create this file as: core/migrations/0003_simplify_models.py
# Replace the problematic migration with this simpler version

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0001_initial'),  # Adjust based on your users app migration
        ('core', '0002_auto_20250906_0253'),  # Adjust this to match your actual last migration
    ]

    operations = [
        # Create new simplified tables
        migrations.RunSQL(
            sql="""
            -- Create new SystemSetting table with correct structure
            CREATE TABLE core_systemsetting_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                key VARCHAR(100) NOT NULL UNIQUE,
                value TEXT NOT NULL,
                description TEXT NOT NULL,
                is_active BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL
            );
            """,
            reverse_sql="DROP TABLE IF EXISTS core_systemsetting_new;",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Copy existing SystemSetting data (only key, value, and other compatible fields)
            INSERT INTO core_systemsetting_new (id, key, value, description, is_active, created_at, updated_at)
            SELECT 
                id, 
                key, 
                value,
                '' as description,
                COALESCE(is_active, 1),
                COALESCE(created_at, datetime('now')),
                COALESCE(updated_at, datetime('now'))
            FROM core_systemsetting;
            """,
            reverse_sql="-- No reverse needed",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Replace old SystemSetting table
            DROP TABLE core_systemsetting;
            ALTER TABLE core_systemsetting_new RENAME TO core_systemsetting;
            """,
            reverse_sql="-- No reverse needed",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Create new Holiday table with correct structure
            CREATE TABLE core_holiday_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                name VARCHAR(100) NOT NULL,
                date DATE NOT NULL,
                is_active BOOLEAN NOT NULL,
                is_recurring BOOLEAN NOT NULL,
                created_at DATETIME NOT NULL,
                UNIQUE(name, date)
            );
            """,
            reverse_sql="DROP TABLE IF EXISTS core_holiday_new;",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Copy existing Holiday data
            INSERT INTO core_holiday_new (id, name, date, is_active, is_recurring, created_at)
            SELECT 
                id, 
                name, 
                date,
                COALESCE(is_active, 1),
                COALESCE(is_recurring, 0),
                COALESCE(created_at, datetime('now'))
            FROM core_holiday;
            """,
            reverse_sql="-- No reverse needed",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Replace old Holiday table
            DROP TABLE core_holiday;
            ALTER TABLE core_holiday_new RENAME TO core_holiday;
            """,
            reverse_sql="-- No reverse needed",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Create new AuditLog table with correct structure
            CREATE TABLE core_auditlog_new (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                action VARCHAR(20) NOT NULL,
                model_name VARCHAR(50) NOT NULL,
                object_id INTEGER,
                object_repr VARCHAR(200) NOT NULL,
                changes JSON NOT NULL,
                ip_address VARCHAR(39),
                timestamp DATETIME NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users_user (id) DEFERRABLE INITIALLY DEFERRED
            );
            """,
            reverse_sql="DROP TABLE IF EXISTS core_auditlog_new;",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Copy existing AuditLog data (excluding user_agent if it exists)
            INSERT INTO core_auditlog_new (id, user_id, action, model_name, object_id, object_repr, changes, ip_address, timestamp)
            SELECT 
                id, 
                user_id, 
                action, 
                model_name,
                object_id,
                COALESCE(object_repr, ''),
                COALESCE(changes, '{}'),
                ip_address,
                COALESCE(timestamp, datetime('now'))
            FROM core_auditlog;
            """,
            reverse_sql="-- No reverse needed",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Replace old AuditLog table
            DROP TABLE core_auditlog;
            ALTER TABLE core_auditlog_new RENAME TO core_auditlog;
            """,
            reverse_sql="-- No reverse needed",
        ),
        
        migrations.RunSQL(
            sql="""
            -- Create indexes for AuditLog
            CREATE INDEX core_auditlog_user_timestamp_idx ON core_auditlog (user_id, timestamp);
            CREATE INDEX core_auditlog_model_timestamp_idx ON core_auditlog (model_name, timestamp);
            CREATE INDEX core_auditlog_action_timestamp_idx ON core_auditlog (action, timestamp);
            """,
            reverse_sql="-- Indexes will be dropped with table",
        ),
    ]