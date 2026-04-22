"""One-time script to sync local MySQL DB with model definitions."""
from app.db.base import engine
from sqlalchemy import text


def safe_exec(conn, sql, desc=""):
    try:
        conn.execute(text(sql))
        return True
    except Exception as e:
        err = str(e)
        if "1060" in err or "Duplicate column" in err or "1050" in err or "already exists" in err:
            pass
        else:
            print(f"  WARN [{desc}]: {err[:120]}")
        return False


def main():
    with engine.connect() as conn:
        print("=== Creating missing tables ===")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS outreach_roles (
            role_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL,
            role_name VARCHAR(100) NOT NULL, description TEXT NULL,
            is_system TINYINT(1) NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (role_id), UNIQUE KEY uq_tenant_role_name (tenant_id, role_name),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        ) ENGINE=InnoDB""", "outreach_roles")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS reply_macros (
            macro_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL,
            title VARCHAR(255) NOT NULL, body_text TEXT NOT NULL, body_html TEXT NULL,
            category VARCHAR(100) NULL, variables_json TEXT NULL,
            usage_count INT NOT NULL DEFAULT 0, created_by INT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (macro_id), INDEX idx_macro_tenant (tenant_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        ) ENGINE=InnoDB""", "reply_macros")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS objection_templates (
            template_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL,
            objection_type VARCHAR(100) NOT NULL, objection_text TEXT NOT NULL,
            response_text TEXT NOT NULL, category VARCHAR(100) NULL,
            effectiveness_score INT NOT NULL DEFAULT 50,
            times_used INT NOT NULL DEFAULT 0, times_approved INT NOT NULL DEFAULT 0,
            created_by INT NULL, is_system TINYINT(1) NOT NULL DEFAULT 0,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (template_id), INDEX idx_objection_tenant (tenant_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        ) ENGINE=InnoDB""", "objection_templates")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS credit_usage (
            usage_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL, user_id INT NULL,
            usage_type VARCHAR(50) NOT NULL, credits_used FLOAT NOT NULL DEFAULT 1.0,
            description VARCHAR(500) NULL, reference_id VARCHAR(255) NULL,
            recorded_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (usage_id), INDEX idx_credit_tenant (tenant_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        ) ENGINE=InnoDB""", "credit_usage")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS goal_targets (
            goal_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL, user_id INT NULL,
            metric VARCHAR(50) NOT NULL, target_value FLOAT NOT NULL,
            current_value FLOAT NOT NULL DEFAULT 0.0,
            period VARCHAR(20) NOT NULL DEFAULT 'monthly',
            period_start VARCHAR(10) NULL, period_end VARCHAR(10) NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (goal_id), INDEX idx_goal_tenant (tenant_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        ) ENGINE=InnoDB""", "goal_targets")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS notifications (
            notification_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL, user_id INT NULL,
            title VARCHAR(255) NOT NULL, message TEXT NULL, category VARCHAR(50) NOT NULL,
            priority VARCHAR(20) NOT NULL DEFAULT 'normal', link VARCHAR(500) NULL,
            is_read TINYINT(1) NOT NULL DEFAULT 0, read_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (notification_id), INDEX idx_notif_tenant_user (tenant_id, user_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        ) ENGINE=InnoDB""", "notifications")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS ai_reply_drafts (
            draft_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL,
            thread_id VARCHAR(255) NOT NULL, campaign_id INT NULL,
            contact_id INT NULL, mailbox_id INT NULL,
            subject VARCHAR(500) NULL, body_html TEXT NOT NULL, body_text TEXT NULL,
            intent_detected VARCHAR(50) NULL, confidence_score INT NOT NULL DEFAULT 50,
            ai_model_used VARCHAR(100) NULL, status VARCHAR(20) NOT NULL DEFAULT 'pending',
            approved_by INT NULL, approved_at DATETIME NULL, sent_at DATETIME NULL,
            expires_at DATETIME NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (draft_id), INDEX idx_draft_thread (thread_id),
            INDEX idx_draft_tenant (tenant_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        ) ENGINE=InnoDB""", "ai_reply_drafts")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS outreach_drafts (
            draft_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL,
            contact_id INT NOT NULL, lead_id INT NULL, campaign_id INT NULL,
            step_id INT NULL, mailbox_id INT NOT NULL,
            subject VARCHAR(500) NOT NULL, body_html TEXT NOT NULL, body_text TEXT NULL,
            original_subject VARCHAR(500) NULL, original_body_html TEXT NULL,
            status ENUM('pending','approved','rejected','sent','expired') NOT NULL DEFAULT 'pending',
            source ENUM('campaign','pipeline','broadcast') NOT NULL,
            spam_score INT NOT NULL DEFAULT 0, spam_grade VARCHAR(20) NOT NULL DEFAULT 'clean',
            flagged_words_json TEXT NULL, deliverability_score FLOAT NULL,
            ai_rewritten TINYINT(1) NOT NULL DEFAULT 0,
            approved_by INT NULL, approved_at DATETIME NULL,
            rejected_by INT NULL, rejected_at DATETIME NULL,
            sent_at DATETIME NULL, expires_at DATETIME NULL,
            batch_id VARCHAR(36) NULL, variant_index INT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (draft_id), INDEX idx_od_tenant (tenant_id),
            INDEX idx_od_batch (batch_id), INDEX idx_od_status (status),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id),
            FOREIGN KEY (contact_id) REFERENCES contact_details(contact_id),
            FOREIGN KEY (mailbox_id) REFERENCES sender_mailboxes(mailbox_id)
        ) ENGINE=InnoDB""", "outreach_drafts")

        safe_exec(conn, """CREATE TABLE IF NOT EXISTS calendar_bookings (
            booking_id INT NOT NULL AUTO_INCREMENT, tenant_id INT NOT NULL,
            contact_id INT NULL, deal_id INT NULL, campaign_id INT NULL,
            provider VARCHAR(50) NOT NULL, booking_url VARCHAR(500) NULL,
            event_type VARCHAR(100) NULL, scheduled_at DATETIME NULL,
            duration_minutes INT NOT NULL DEFAULT 30,
            attendee_email VARCHAR(255) NULL, attendee_name VARCHAR(255) NULL,
            status VARCHAR(20) NOT NULL DEFAULT 'scheduled',
            external_id VARCHAR(255) NULL, notes TEXT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            is_archived TINYINT(1) NOT NULL DEFAULT 0,
            PRIMARY KEY (booking_id), INDEX idx_booking_tenant (tenant_id),
            FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id)
        ) ENGINE=InnoDB""", "calendar_bookings")

        conn.commit()
        print("=== All tables created ===")


if __name__ == "__main__":
    main()
