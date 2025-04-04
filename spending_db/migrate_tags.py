#!/usr/bin/env python3
import psycopg2
import time

# Database connection parameters
DB_PARAMS = {
    "dbname": "spending_db",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": "5432"
}

def get_db_connection():
    """Create a database connection with retry logic"""
    max_retries = 5
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            conn = psycopg2.connect(**DB_PARAMS)
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError as e:
            retry_count += 1
            print(f"Database connection failed (attempt {retry_count}/{max_retries}): {str(e)}")
            if retry_count < max_retries:
                time.sleep(2)  # Wait 2 seconds before retrying
            else:
                raise

def migrate_tags():
    """Migrate transaction_tags table from (description, amount) to description only"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        print("Starting migration of transaction_tags table...")
        
        # Create backup of current table
        print("Creating backup of transaction_tags table...")
        cur.execute("""
            CREATE TABLE IF NOT EXISTS transaction_tags_backup AS 
            SELECT * FROM transaction_tags
        """)
        
        # Get existing tags (taking the first occurrence of each description)
        print("Extracting unique description-tag pairs...")
        cur.execute("""
            SELECT DISTINCT ON (description) description, tag 
            FROM transaction_tags 
            ORDER BY description, id
        """)
        
        unique_tags = cur.fetchall()
        print(f"Found {len(unique_tags)} unique description-tag pairs")
        
        # Drop the existing table and constraints
        print("Dropping existing transaction_tags table...")
        cur.execute("DROP TABLE transaction_tags")
        
        # Create new table with description as unique
        print("Creating new transaction_tags table with description as unique key...")
        cur.execute("""
            CREATE TABLE transaction_tags (
                id SERIAL PRIMARY KEY,
                description TEXT UNIQUE,
                tag TEXT
            )
        """)
        
        # Insert the unique tags
        print("Inserting unique description-tag pairs...")
        inserted_count = 0
        for desc_tag in unique_tags:
            description = desc_tag[0]
            tag = desc_tag[1]
            
            cur.execute("""
                INSERT INTO transaction_tags (description, tag)
                VALUES (%s, %s)
            """, (description, tag))
            inserted_count += 1
        
        print(f"Successfully inserted {inserted_count} description-tag pairs")
        print("Migration completed successfully")
        
        cur.close()
        conn.close()
        return True
    except Exception as e:
        print(f"Error during migration: {str(e)}")
        return False

if __name__ == "__main__":
    migrate_tags() 