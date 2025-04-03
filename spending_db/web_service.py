from flask import Flask, render_template, request, redirect, url_for
import psycopg2
import psycopg2.extras
import os

app = Flask(__name__)

# Database connection parameters
DB_PARAMS = {
    "dbname": "spending_db",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",
    "port": "5432"
}

def get_db_connection():
    """Create a database connection"""
    conn = psycopg2.connect(**DB_PARAMS)
    conn.autocommit = True
    return conn

@app.route('/')
def index():
    """Display the main page with unique description:vendor pairs"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Query to get unique description:vendor pairs in alphabetical order
        query = """
        SELECT DISTINCT description, vendor, COUNT(*) as count, SUM(CASE 
            WHEN amount ~ '^[0-9.,]+$' THEN CAST(amount AS NUMERIC) 
            ELSE 0 
        END) as total_amount
        FROM transactions
        GROUP BY description, vendor
        ORDER BY description ASC
        """
        
        cur.execute(query)
        transaction_pairs = cur.fetchall()
        
        # Check if we have a tags table, create it if it doesn't exist
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'transaction_tags'
            );
        """)
        
        has_tags_table = cur.fetchone()[0]
        
        if not has_tags_table:
            # Create tags table
            cur.execute("""
                CREATE TABLE transaction_tags (
                    id SERIAL PRIMARY KEY,
                    description TEXT,
                    vendor TEXT,
                    tag TEXT,
                    UNIQUE (description, vendor)
                );
            """)
        
        # Get existing tags
        cur.execute("SELECT description, vendor, tag FROM transaction_tags")
        existing_tags = {(row['description'], row['vendor']): row['tag'] for row in cur.fetchall()}
        
        cur.close()
        conn.close()
        
        return render_template('index.html', 
                              transaction_pairs=transaction_pairs,
                              existing_tags=existing_tags)
                              
    except Exception as e:
        return f"Database error: {str(e)}"

@app.route('/update_tag', methods=['POST'])
def update_tag():
    """Update or create a tag for a description:vendor pair"""
    description = request.form.get('description')
    vendor = request.form.get('vendor')
    tag = request.form.get('tag')
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Upsert tag - insert if not exists, update if exists
        cur.execute("""
            INSERT INTO transaction_tags (description, vendor, tag)
            VALUES (%s, %s, %s)
            ON CONFLICT (description, vendor) 
            DO UPDATE SET tag = EXCLUDED.tag
        """, (description, vendor, tag))
        
        cur.close()
        conn.close()
        
        return redirect(url_for('index'))
        
    except Exception as e:
        return f"Error updating tag: {str(e)}"

if __name__ == '__main__':
    # Create templates directory if it doesn't exist
    if not os.path.exists('templates'):
        os.makedirs('templates')
        
    app.run(host='0.0.0.0', port=5000, debug=True) 