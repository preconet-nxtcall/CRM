from app.models import db
from sqlalchemy import text, inspect

def run_schema_patch():
    """
    Checks for missing columns and adds them via raw SQL.
    Safe to run on every startup (idempotent).
    """
    try:
        print("Running schema patcher...")
        engine = db.engine
        inspector = inspect(engine)
        
        # Check if table exists first
        if 'attendances' not in inspector.get_table_names():
            return
            
        columns = [c['name'] for c in inspector.get_columns('attendances')]
        
        # Columns to add
        new_columns = {
            'check_out_latitude': 'FLOAT',
            'check_out_longitude': 'FLOAT',
            'check_out_address': 'VARCHAR(500)',
            'check_out_image': 'VARCHAR(1024)',
            'current_session_id': 'VARCHAR(100)' # For single device login
        }
        
        with engine.connect() as conn:
            for col_name, col_type in new_columns.items():
                if col_name not in columns:
                    print(f"Adding missing column: {col_name} ({col_type})")
                    try:
                        # Use text() for safety
                        conn.execute(text(f'ALTER TABLE attendances ADD COLUMN {col_name} {col_type}'))
                        print(f"✅ Added {col_name}")
                    except Exception as e:
                        print(f"❌ Failed to add {col_name}: {e}")
            

            # Message for attendances
            # Now check USERS table for session_id and new guard fields
            if 'users' in inspector.get_table_names():
                user_cols = [c['name'] for c in inspector.get_columns('users')]
                
                # 1. current_session_id
                if 'current_session_id' not in user_cols:
                    print("Adding current_session_id to users table...")
                    try:
                         conn.execute(text('ALTER TABLE users ADD COLUMN current_session_id VARCHAR(100)'))
                         print("✅ Added current_session_id to users")
                    except Exception as e:
                         print(f"❌ Failed to add current_session_id: {e}")

                # 2. status
                if 'status' not in user_cols:
                    print("Adding status to users table...")
                    try:
                         conn.execute(text("ALTER TABLE users ADD COLUMN status VARCHAR(20) DEFAULT 'active'"))
                         print("✅ Added status to users")
                    except Exception as e:
                         print(f"❌ Failed to add status: {e}")

                # 3. is_suspended
                if 'is_suspended' not in user_cols:
                    print("Adding is_suspended to users table...")
                    try:
                         conn.execute(text("ALTER TABLE users ADD COLUMN is_suspended BOOLEAN DEFAULT FALSE"))
                         print("✅ Added is_suspended to users")
                    except Exception as e:
                         print(f"❌ Failed to add is_suspended: {e}")

                # 4. subscription_expiry_date
                if 'subscription_expiry_date' not in user_cols:
                    print("Adding subscription_expiry_date to users table...")
                    try:
                         conn.execute(text("ALTER TABLE users ADD COLUMN subscription_expiry_date TIMESTAMP"))
                         print("✅ Added subscription_expiry_date to users")
                    except Exception as e:
                         print(f"❌ Failed to add subscription_expiry_date: {e}")

                # 5. fcm_token
                if 'fcm_token' not in user_cols:
                    print("Adding fcm_token to users table...")
                    try:
                         conn.execute(text("ALTER TABLE users ADD COLUMN fcm_token VARCHAR(255)"))
                         print("✅ Added fcm_token to users")
                    except Exception as e:
                         print(f"❌ Failed to add fcm_token: {e}")

            # ADMINS table for session_id
            if 'admins' in inspector.get_table_names():
                admin_cols = [c['name'] for c in inspector.get_columns('admins')]
                
                if 'current_session_id' not in admin_cols:
                    print("Adding current_session_id to admins table...")
                    try:
                         conn.execute(text('ALTER TABLE admins ADD COLUMN current_session_id VARCHAR(100)'))
                         print("✅ Added current_session_id to admins")
                    except Exception as e:
                         print(f"❌ Failed to add current_session_id: {e}")

            # CALL HISTORY - recording_path
            if 'call_history' in inspector.get_table_names():
                ch_cols = [c['name'] for c in inspector.get_columns('call_history')]
                if 'recording_path' not in ch_cols:
                    print("Adding recording_path to call_history table...")
                    try:
                         conn.execute(text('ALTER TABLE call_history ADD COLUMN recording_path VARCHAR(1024)'))
                         print("✅ Added recording_path to call_history")
                    except Exception as e:
                         print(f"❌ Failed to add recording_path: {e}")

            conn.commit()
            
            # Create password_resets table if missing
            if 'password_resets' not in inspector.get_table_names():
                print("Creating password_resets table...")
                try:
                    conn.execute(text('''
                        CREATE TABLE password_resets (
                            id SERIAL PRIMARY KEY,
                            email VARCHAR(150) NOT NULL,
                            token VARCHAR(100) UNIQUE NOT NULL,
                            expires_at TIMESTAMP NOT NULL,
                            used BOOLEAN DEFAULT FALSE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    '''))
                    # Add index on email for faster lookups
                    conn.execute(text('CREATE INDEX idx_pwd_reset_email ON password_resets (email)'))
                    print("✅ Created password_resets table")
                except Exception as e:
                    print(f"❌ Failed to create password_resets table: {e}")

            # -------------------------------------------------------------
            # FACEBOOK & LEAD SCHEMA MIGRATION (Development Fix)
            # -------------------------------------------------------------
            # If 'facebook_pages' has 'user_id' instead of 'admin_id', drop it to allow recreation.
            if 'facebook_pages' in inspector.get_table_names():
                cols = [c['name'] for c in inspector.get_columns('facebook_pages')]
                if 'user_id' in cols and 'admin_id' not in cols:
                    print("⚠️ Detected legacy 'facebook_pages' schema (user_id). Dropping to recreate with admin_id...")
                    try:
                        conn.execute(text('DROP TABLE facebook_pages CASCADE')) 
                        # CASCADE might fail on SQLite, usually standard DROP works unless FK constraints block it.
                        print("✅ Dropped legacy facebook_pages table.")
                    except Exception:
                        try:
                            conn.execute(text('DROP TABLE facebook_pages')) 
                            print("✅ Dropped legacy facebook_pages table (retry).")
                        except Exception as e2:
                             print(f"❌ Failed to drop facebook_pages: {e2}")

            # Same for 'leads'
            if 'leads' in inspector.get_table_names():
                cols = [c['name'] for c in inspector.get_columns('leads')]
                if 'user_id' in cols and 'admin_id' not in cols:
                     print("⚠️ Detected legacy 'leads' schema (user_id). Dropping to recreate with admin_id...")
                     try:
                        conn.execute(text('DROP TABLE leads CASCADE'))
                        print("✅ Dropped legacy leads table.")
                     except Exception:
                        try:
                             conn.execute(text('DROP TABLE leads'))
                             print("✅ Dropped legacy leads table (retry).")
                        except Exception as e2:
                             print(f"❌ Failed to drop leads: {e2}")

            # -------------------------------------------------------------
            # LEADS TABLE - Real Estate Fields
            # -------------------------------------------------------------
            if 'leads' in inspector.get_table_names():
                lead_cols = [c['name'] for c in inspector.get_columns('leads')]
                new_lead_cols = {
                    'property_type': 'VARCHAR(100)',
                    'location': 'VARCHAR(255)',
                    'budget': 'VARCHAR(100)',
                    'requirement': 'TEXT'
                }
                for col, dtype in new_lead_cols.items():
                    if col not in lead_cols:
                        print(f"Adding {col} to leads table...")
                        try:
                            # Use text() for safety
                            conn.execute(text(f'ALTER TABLE leads ADD COLUMN {col} {dtype}'))
                            print(f"✅ Added {col} to leads")
                        except Exception as e:
                            print(f"❌ Failed to add {col}: {e}")

            # INDIAMART SETTINGS - auto_sync_enabled
            if 'indiamart_settings' in inspector.get_table_names():
                im_cols = [c['name'] for c in inspector.get_columns('indiamart_settings')]
                if 'auto_sync_enabled' not in im_cols:
                    print("Adding auto_sync_enabled to indiamart_settings table...")
                    try:
                         # Default TRUE
                         conn.execute(text("ALTER TABLE indiamart_settings ADD COLUMN auto_sync_enabled BOOLEAN DEFAULT TRUE"))
                         print("✅ Added auto_sync_enabled to indiamart_settings")
                    except Exception as e:
                         print(f"❌ Failed to add auto_sync_enabled: {e}")

            # -------------------------------------------------------------
            # MAGICBRICKS TABLES
            # -------------------------------------------------------------
            if 'magicbricks_settings' not in inspector.get_table_names():
                print("Creating magicbricks_settings table...")
                try:
                    conn.execute(text('''
                        CREATE TABLE magicbricks_settings (
                            id SERIAL PRIMARY KEY,
                            admin_id INTEGER NOT NULL UNIQUE,
                            imap_host VARCHAR(100) DEFAULT 'imap.gmail.com',
                            email_id VARCHAR(100) NOT NULL,
                            app_password VARCHAR(255) NOT NULL,
                            last_sync_time TIMESTAMP,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (admin_id) REFERENCES admins (id)
                        )
                    '''))
                    print("✅ Created magicbricks_settings table")
                except Exception as e:
                    print(f"❌ Failed to create magicbricks_settings: {e}")


            if 'processed_emails' not in inspector.get_table_names():
                print("Creating processed_emails table...")
                try:
                    conn.execute(text('''
                        CREATE TABLE processed_emails (
                            id SERIAL PRIMARY KEY,
                            admin_id INTEGER NOT NULL,
                            message_id VARCHAR(255) NOT NULL,
                            lead_source VARCHAR(50) DEFAULT 'MAGICBRICKS',
                            processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (admin_id) REFERENCES admins (id),
                            CONSTRAINT uq_admin_message_id UNIQUE (admin_id, message_id)
                        )
                    '''))
                    print("✅ Created processed_emails table")
                except Exception as e:
                    print(f"❌ Failed to create processed_emails: {e}")

            # -------------------------------------------------------------
            # 99ACRES TABLES
            # -------------------------------------------------------------
            if 'ninety_nine_acres_settings' not in inspector.get_table_names():
                print("Creating ninety_nine_acres_settings table...")
                try:
                    conn.execute(text('''
                        CREATE TABLE ninety_nine_acres_settings (
                            id SERIAL PRIMARY KEY,
                            admin_id INTEGER NOT NULL UNIQUE,
                            imap_host VARCHAR(100) DEFAULT 'imap.gmail.com',
                            email_id VARCHAR(100) NOT NULL,
                            app_password VARCHAR(255) NOT NULL,
                            last_sync_time TIMESTAMP,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (admin_id) REFERENCES admins (id)
                        )
                    '''))
                    print("✅ Created ninety_nine_acres_settings table")
                except Exception as e:
                    print(f"❌ Failed to create ninety_nine_acres_settings: {e}")


                except Exception as e:
                    print(f"❌ Failed to create ninety_nine_acres_settings: {e}")

            # -------------------------------------------------------------
            # JUSTDIAL TABLES
            # -------------------------------------------------------------

            if 'justdial_settings' not in inspector.get_table_names():
                print("Creating justdial_settings table...")
                try:
                    conn.execute(text('''
                        CREATE TABLE justdial_settings (
                            id SERIAL PRIMARY KEY,
                            admin_id INTEGER NOT NULL UNIQUE,
                            imap_host VARCHAR(100) DEFAULT 'imap.gmail.com',
                            email_id VARCHAR(100) NOT NULL,
                            app_password VARCHAR(255) NOT NULL,
                            last_sync_time TIMESTAMP,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (admin_id) REFERENCES admins (id)
                        )
                    '''))
                    print("✅ Created justdial_settings table")
                except Exception as e:
                    print(f"❌ Failed to create justdial_settings: {e}")

            # -------------------------------------------------------------
            # HOUSING TABLES
            # -------------------------------------------------------------
            if 'housing_settings' not in inspector.get_table_names():
                print("Creating housing_settings table...")
                try:
                    conn.execute(text('''
                        CREATE TABLE housing_settings (
                            id SERIAL PRIMARY KEY,
                            admin_id INTEGER NOT NULL UNIQUE,
                            imap_host VARCHAR(100) DEFAULT 'imap.gmail.com',
                            email_id VARCHAR(100) NOT NULL,
                            app_password VARCHAR(255) NOT NULL,
                            last_sync_time TIMESTAMP,
                            is_active BOOLEAN DEFAULT TRUE,
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (admin_id) REFERENCES admins (id)
                        )
                    '''))
                    print("✅ Created housing_settings table")
                except Exception as e:
                    print(f"❌ Failed to create housing_settings: {e}")

            # -------------------------------------------------------------
            # FACEBOOK CONNECTIONS (Strict SaaS)
            # -------------------------------------------------------------
            if 'facebook_connections' not in inspector.get_table_names():
                print("Creating facebook_connections table...")
                try:
                    conn.execute(text('''
                        CREATE TABLE facebook_connections (
                            id SERIAL PRIMARY KEY,
                            admin_id INTEGER NOT NULL UNIQUE,
                            page_id VARCHAR(100),
                            page_name VARCHAR(255),
                            business_manager_id VARCHAR(100) NOT NULL,
                            system_user_id VARCHAR(100) NOT NULL,
                            encrypted_system_token TEXT NOT NULL,
                            install_id VARCHAR(100),
                            status VARCHAR(50) DEFAULT 'active',
                            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                            FOREIGN KEY (admin_id) REFERENCES admins (id)
                        )
                    '''))
                    print("✅ Created facebook_connections table")
                except Exception as e:
                    print(f"❌ Failed to create facebook_connections: {e}")

            # Update facebook_pages with connection_id (renaming or adding)
            if 'facebook_pages' in inspector.get_table_names():
                fb_cols = [c['name'] for c in inspector.get_columns('facebook_pages')]
                if 'connection_id' not in fb_cols:
                    print("Adding connection_id to facebook_pages table...")
                    try:
                         conn.execute(text('ALTER TABLE facebook_pages ADD COLUMN connection_id INTEGER REFERENCES facebook_connections(id)'))
                         print("✅ Added connection_id to facebook_pages")
                    except Exception as e:
                         print(f"❌ Failed to add connection_id: {e}")

            conn.commit()
            print("Schema patch complete.")
            
    except Exception as e:
        print(f"Schema patch failed: {e}")
