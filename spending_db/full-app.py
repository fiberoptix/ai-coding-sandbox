from flask import Flask, render_template_string, request, redirect, url_for, render_template
import psycopg2
import psycopg2.extras
import os
import time
from urllib.parse import urlparse, parse_qs
import sqlite3

app = Flask(__name__)

# Database connection parameters - adapts to both local and Docker environments
DB_PARAMS = {
    "dbname": "spending_db",
    "user": "postgres",
    "password": "postgres",
    "host": "localhost",  # This connects to Docker container or local instance
    "port": "5432"
}

def get_build_number():
    """Get the current build number from environment variable"""
    try:
        return os.environ.get('BUILD_NUMBER', '1')
    except Exception:
        return "?"  # Return a placeholder if any error occurs

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

def initialize_database():
    """Create necessary tables if they don't exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Create tags table if it doesn't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tags (
            id SERIAL PRIMARY KEY,
            description TEXT UNIQUE,
            tag TEXT
        )
    """)
    
    # Create records_history table if it doesn't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records_history (
            id SERIAL PRIMARY KEY,
            date TEXT,
            description TEXT,
            vendor TEXT,
            amount TEXT,
            tag TEXT,
            imported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    # Create records_imported table if it doesn't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS records_imported (
            id SERIAL PRIMARY KEY,
            date TEXT,
            description TEXT,
            vendor TEXT,
            amount TEXT
        )
    """)
    
    conn.commit()
    cur.close()
    conn.close()
    print("Database initialization complete.")

def auto_apply_tags():
    """Apply tags to untagged transactions based on existing pattern matches"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    print("Auto-applying tags to transactions...")
    
    # Get all existing tags
    cur.execute("SELECT description, tag FROM tags")
    existing_tags = cur.fetchall()
    
    tags_applied = 0
    
    # Get all unique descriptions that don't have tags yet
    cur.execute("""
        SELECT DISTINCT t.description
        FROM records_imported t
        LEFT JOIN tags tt ON t.description = tt.description
        WHERE tt.id IS NULL
    """)
    
    untagged_descriptions = cur.fetchall()
    print(f"Found {len(untagged_descriptions)} untagged transaction descriptions")
    
    # For each untagged description, find exact matches in existing tags
    for untagged in untagged_descriptions:
        description = untagged[0]
        
        # Look for exact match - unlikely with our new structure but we'll keep this for consistency
        for existing in existing_tags:
            if description == existing[0]:
                # Apply tag
                cur.execute("""
                    INSERT INTO tags (description, tag)
                    VALUES (%s, %s)
                    ON CONFLICT (description) DO NOTHING
                """, (description, existing[1]))
                tags_applied += 1
                break
    
    conn.commit()
    
    print(f"Applied {tags_applied} tags based on exact matches")
    
    # For remaining untagged descriptions, try partial matching
    cur.execute("""
        SELECT DISTINCT t.description
        FROM records_imported t
        LEFT JOIN tags tt ON t.description = tt.description
        WHERE tt.id IS NULL
    """)
    
    still_untagged = cur.fetchall()
    partial_matches = 0
    
    for untagged in still_untagged:
        description = untagged[0]
        
        # Find most commonly used tag for similar descriptions
        cur.execute("""
            SELECT tag, COUNT(*) AS count
            FROM tags
            WHERE description ILIKE %s OR %s ILIKE '%' || description || '%'
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 1
        """, ('%' + description + '%', description))
        
        matches = cur.fetchone()
        if matches:
            # Apply the most common tag
            cur.execute("""
                INSERT INTO tags (description, tag)
                VALUES (%s, %s)
                ON CONFLICT (description) DO NOTHING
            """, (description, matches[0]))
            partial_matches += 1
    
    conn.commit()
    print(f"Applied {partial_matches} tags based on partial description matches")
    
    total_applied = tags_applied + partial_matches
    print(f"Total auto-tagging: {total_applied} transactions")
    
    cur.close()
    conn.close()
    return total_applied

def get_history_count():
    """Get the count of transactions in the records_history table"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM records_history")
    count = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    return count

def get_tags_count():
    """Get the count of unique tags in the records_history table"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(DISTINCT tag) FROM records_history")
    count = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    return count

# HTML template 
HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Data Import and Tagging</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        .container {
            width: 100%;
        }
        input[type="text"] {
            padding: 8px;
            margin-right: 5px;
        }
        select {
            padding: 8px;
            margin-right: 5px;
        }
        button {
            padding: 8px;
            background-color: #007BFF;
            color: white;
            border: none;
            cursor: pointer;
        }
        .tag-form {
            display: flex;
            align-items: center;
        }
        .tag-input {
            flex-grow: 1;
            margin-right: 5px;
        }
        .tag-submit {
            flex-shrink: 0;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 20px;
        }
        th, td {
            padding: 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .pagination {
            margin-top: 20px;
            text-align: center;
        }
        .pagination a {
            margin: 0 5px;
        }
        .alert {
            padding: 15px;
            background-color: #d4edda;
            color: #155724;
            margin-bottom: 15px;
            border-radius: 4px;
        }
        .search-section {
            margin-bottom: 20px;
        }
        .stats {
            margin-top: 20px;
            padding: 15px;
            background-color: #f8f9fa;
            border-radius: 4px;
        }
        .build-info {
            position: absolute;
            top: 10px;
            right: 20px;
            padding: 5px 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
            font-size: 12px;
            color: #6c757d;
            border: 1px solid #dee2e6;
        }
        .btn-group {
            display: flex;
            gap: 10px;
            margin-bottom: 15px;
        }
        .btn-import {
            padding: 8px;
            background-color: #28a745;
            color: white;
            border: none;
            cursor: pointer;
        }
        .file-import-form {
            display: none;
            margin-top: 15px;
            padding: 15px;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            background-color: #f8f9fa;
        }
        .file-import-form.active {
            display: block;
        }
        @media (max-width: 768px) {
            .tag-form {
                flex-direction: column;
                align-items: stretch;
            }
            .tag-input, .tag-submit {
                width: 100%;
                margin-right: 0;
                margin-bottom: 5px;
            }
        }
    </style>
    <script>
        function showImportForm() {
            document.getElementById('importRecordsForm').classList.toggle('active');
        }
        
        function confirmClear() {
            return confirm('Are you sure you want to clear the selected tables? This cannot be undone.');
        }
        
        function confirmPush() {
            return confirm('Are you sure you want to push all tagged transactions to history? This will remove them from the current working set.');
        }
    </script>
</head>
<body>
    <div class="build-info">Build: {{ build_number }}</div>
    <div class="container">
        <h1>Data Import and Tagging</h1>
        <p>Tag your transactions to categorize spending patterns.</p>
        
        <div class="btn-group">
            <a href="/"><button>Home</button></a>
            <button class="btn-import" onclick="showImportForm()">Import New Records</button>
            <a href="/most_common"><button>Most Common</button></a>
            <a href="/monthly_summary"><button>Monthly Summary</button></a>
            <a href="/tag_summary"><button>Tag Summary</button></a>
        </div>
        
        <div id="importRecordsForm" class="file-import-form">
            <h3>Import Transactions CSV</h3>
            <form action="/import_records" method="post" enctype="multipart/form-data">
                <p>Select a CSV file with transactions to import. The file should have headers for date, description, vendor, and amount.</p>
                <input type="file" name="records_file" required>
                <div style="margin-top: 10px;">
                    <label>
                        <input type="checkbox" name="clear_existing" value="yes">
                        Clear existing imported records before importing
                    </label>
                </div>
                <button type="submit" style="margin-top: 10px;">Import Records</button>
            </form>
        </div>
        
        <div class="search-section" style="background-color: #e6ffe6; padding: 15px; border-radius: 5px; margin-bottom: 20px; border: 1px solid #99cc99;">
            <form method="GET" action="/data_import_tagging">
                <span style="font-weight: bold; margin-right: 10px;">SEARCH:</span>
                <input type="text" name="search" value="{{ search }}" placeholder="Search transactions..." autofocus>
                <select name="filter">
                    <option value="all" {% if filter == 'all' %}selected{% endif %}>All Transactions</option>
                    <option value="untagged" {% if filter == 'untagged' %}selected{% endif %}>Untagged Only</option>
                    <option value="tagged" {% if filter == 'tagged' %}selected{% endif %}>Tagged Only</option>
                </select>
                <button type="submit">Search</button>
            </form>
        </div>

        {% if auto_tagged and auto_tagged > 0 %}
        <div class="alert">
            <p>{{ auto_tagged }} transactions tagged successfully with "{{ tag if tag else 'tag' }}"!</p>
            <p><small>Note: Tags are applied to unique descriptions. All transactions with the same description are automatically tagged together.</small></p>
        </div>
        {% endif %}
        
        {% if moved_count and moved_count > 0 %}
        <div class="alert" style="background-color: #d4edda; color: #155724; padding: 15px; margin-bottom: 15px; border-radius: 4px;">
            <strong>Success!</strong> {{ moved_count }} transactions moved to history.
            <p><small>Tagged transactions have been moved to the persistent history table and removed from the current working set.</small></p>
        </div>
        {% endif %}
        
        {% if transactions|length > 0 %}
            {% if search %}
            <div class="tag-all-section" style="background-color: #ffebcc; padding: 15px; border-radius: 5px; margin-bottom: 20px; border: 1px solid #ffcc80;">
                <form id="tag-all-form" method="POST" action="/tag_all_confirmation">
                    <span style="font-weight: bold; margin-right: 10px;">TAG:</span>
                    <input type="hidden" name="search" value="{{ search }}">
                    <input type="hidden" name="filter" value="{{ filter }}">
                    <input type="hidden" name="from_page" value="{% if request.path == '/most_common' %}most_common{% else %}index{% endif %}">
                    <input type="hidden" name="sort" value="{{ sort }}">
                    <input type="hidden" name="sort_dir" value="{{ sort_dir }}">
                    <input type="text" name="tag" placeholder="Enter tag for all results" required style="width: 250px; padding: 8px; margin-right: 5px;">
                    <button type="submit" style="padding: 8px; background-color: #007BFF; color: white; border: none; cursor: pointer;">Tag All Matching Transactions</button>
                </form>
            </div>
            {% elif request.args.get('show_tag_all') == 'true' %}
            <div class="tag-all-section" style="background-color: #ffebcc; padding: 15px; border-radius: 5px; margin-bottom: 20px; border: 1px solid #ffcc80;">
                <form id="tag-all-form-most-common" method="POST" action="/tag_all_confirmation">
                    <span style="font-weight: bold; margin-right: 10px;">TAG:</span>
                    <input type="hidden" name="search" value="">
                    <input type="hidden" name="filter" value="{{ filter }}">
                    <input type="hidden" name="from_page" value="{% if request.path == '/most_common' %}most_common{% else %}index{% endif %}">
                    <input type="hidden" name="sort" value="{{ sort }}">
                    <input type="hidden" name="sort_dir" value="{{ sort_dir }}">
                    <input type="text" name="tag" placeholder="Enter tag for all displayed results" required style="width: 250px; padding: 8px; margin-right: 5px;">
                    <button type="submit" style="padding: 8px; background-color: #007BFF; color: white; border: none; cursor: pointer;">Tag All Displayed Transactions</button>
                </form>
            </div>
            {% else %}
            <div style="margin-bottom: 20px; text-align: center;">
                <a href="{% if request.path == '/most_common' %}{{ url_for('most_common', filter=filter, sort=sort, dir=sort_dir, show_tag_all='true') }}{% else %}{{ url_for('index', search=search, filter=filter, sort=sort, dir=sort_dir, show_tag_all='true') }}{% endif %}" 
                  style="padding: 8px 15px; background-color: #ffebcc; color: #333; text-decoration: none; border-radius: 5px; border: 1px solid #ffcc80;">
                    Show Tag Options
                </a>
            </div>
            {% endif %}
        {% endif %}
        
        <div class="stats">
            <h3>Statistics</h3>
            <div style="display: flex; justify-content: space-between;">
                <div>
                    <table style="width: auto; margin-bottom: 10px;">
                        <tr>
                            <td style="text-align: right; padding-right: 15px;">Total transactions:</td>
                            <td style="text-align: right;">{{ total_transactions }}</td>
                        </tr>
                        <tr>
                            <td style="text-align: right; padding-right: 15px;">Total unique descriptions:</td>
                            <td style="text-align: right;">{{ total_unique_descriptions }}</td>
                        </tr>
                        <tr>
                            <td style="text-align: right; padding-right: 15px;">Unique descriptions tagged:</td>
                            <td style="text-align: right;">{{ tagged_count }}</td>
                        </tr>
                        <tr>
                            <td style="text-align: right; padding-right: 15px;">Total transactions tagged:</td>
                            <td style="text-align: right;">{{ total_tagged_transactions }}</td>
                        </tr>
                        <tr>
                            <td style="text-align: right; padding-right: 15px;">Remaining to tag:</td>
                            <td style="text-align: right;">{{ remaining_to_tag }}</td>
                        </tr>
                    </table>
                </div>
                <div style="margin-left: 20px; text-align: center;">
                    <div style="margin-bottom: 15px;">
                        <form action="/push_to_history" method="post" onsubmit="return confirm('Are you sure you want to move all tagged transactions to history? This action cannot be undone.');">
                            <button type="submit" style="padding: 10px 15px; background-color: #007BFF; color: white; border: none; border-radius: 4px; cursor: pointer;">Push to transaction_history</button>
                        </form>
                    </div>
                    <div>
                        <table style="width: auto; margin: 0 auto;">
                            <tr>
                                <td style="text-align: right; padding-right: 15px; font-weight: bold;">Total Transactions in History:</td>
                                <td style="text-align: right; font-weight: bold;">{{ history_count }}</td>
                            </tr>
                            <tr>
                                <td style="text-align: right; padding-right: 15px; font-weight: bold;">Total Tags in History:</td>
                                <td style="text-align: right; font-weight: bold;">{{ tags_count }}</td>
                            </tr>
                        </table>
                    </div>
                </div>
            </div>
        </div>
        
        <div style="overflow-x: auto;">
            <table>
                <thead>
                    <tr>
                        <th><a href="?sort=description&dir={% if sort == 'description' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&page={{ page }}&filter={{ filter }}{% if search %}&search={{ search }}{% endif %}" style="color: inherit; text-decoration: none;">Description {% if sort == 'description' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                        <th><a href="?sort=count&dir={% if sort == 'count' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&page={{ page }}&filter={{ filter }}{% if search %}&search={{ search }}{% endif %}" style="color: inherit; text-decoration: none;">Count {% if sort == 'count' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                        <th><a href="?sort=amount&dir={% if sort == 'amount' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&page={{ page }}&filter={{ filter }}{% if search %}&search={{ search }}{% endif %}" style="color: inherit; text-decoration: none;">Amount {% if sort == 'amount' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                        <th>Tag</th>
                    </tr>
                </thead>
                <tbody>
                    {% for transaction in transactions %}
                    <tr>
                        <td>{{ transaction.description }}</td>
                        <td>{{ transaction.count }}</td>
                        <td>{{ transaction.total }}</td>
                        <td>
                            <form class="tag-form" action="/update_tag" method="post">
                                <input type="hidden" name="description" value="{{ transaction.description }}">
                                <input type="hidden" name="page" value="{{ page }}">
                                <input type="hidden" name="search" value="{{ search }}">
                                <input type="hidden" name="filter" value="{{ filter }}">
                                <input type="hidden" name="sort" value="{{ sort }}">
                                <input type="hidden" name="sort_dir" value="{{ sort_dir }}">
                                <input type="hidden" name="from_page" value="{% if request.path == '/most_common' %}most_common{% else %}index{% endif %}">
                                <input type="text" name="tag" class="tag-input" 
                                      value="{{ existing_tags[transaction.description] if transaction.description in existing_tags else '' }}" 
                                       placeholder="Enter tag...">
                                <button type="submit" class="tag-submit">Save</button>
                            </form>
                        </td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        <div style="margin-top: 20px;">
            <a href="/export_tags" download="transaction_tags.csv">Export Tags as CSV</a>
            <span style="margin: 0 10px;">|</span>
            <a href="/export_history" download="transaction_history.csv">Export All Historical Transactions as CSV</a>
            <div style="margin-top: 15px;">
                <form action="/import_tags" method="post" enctype="multipart/form-data">
                    <input type="file" name="tags_file" accept=".csv" required style="display: inline-block;">
                    <button type="submit" style="padding: 5px 10px; background-color: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer;">Import Tags</button>
                </form>
                <form action="/import_history" method="post" enctype="multipart/form-data" style="margin-top: 5px;">
                    <input type="file" name="history_file" accept=".csv" required style="display: inline-block;">
                    <button type="submit" style="padding: 5px 10px; background-color: #28a745; color: white; border: none; border-radius: 4px; cursor: pointer;">Import History</button>
                </form>
            </div>
            
            <div style="margin-top: 20px; padding: 15px; background-color: #f8d7da; border-radius: 5px; border: 1px solid #f5c6cb;">
                <h4>Clear Database Tables</h4>
                <form action="/clear_database" method="post" onsubmit="return confirm('WARNING: This will permanently delete data from the selected tables. Are you sure you want to continue?');">
                    <div style="margin-bottom: 10px;">
                        <input type="checkbox" id="clear_transactions" name="tables" value="records_imported">
                        <label for="clear_transactions">Current Transactions</label>
                    </div>
                    <div style="margin-bottom: 10px;">
                        <input type="checkbox" id="clear_tags" name="tables" value="tags">
                        <label for="clear_tags">Transaction Tags</label>
                    </div>
                    <div style="margin-bottom: 10px;">
                        <input type="checkbox" id="clear_history" name="tables" value="records_history">
                        <label for="clear_history">Transaction History</label>
                    </div>
                    <button type="submit" style="padding: 5px 10px; background-color: #dc3545; color: white; border: none; border-radius: 4px; cursor: pointer;">Clear Selected Tables</button>
                </form>
            </div>
        </div>
    </div>
</body>
</html>
"""

@app.route('/data_import_tagging')
def index():
    search = request.args.get('search', '')
    filter_type = request.args.get('filter', 'all')
    auto_tagged = request.args.get('auto_tagged', 0, type=int)
    unique_tags_applied = request.args.get('unique_tags_applied', 0, type=int)
    moved_count = request.args.get('moved_count', 0, type=int)
    tags_imported = request.args.get('tags_imported', 0, type=int)
    history_imported = request.args.get('history_imported', 0, type=int)
    records_imported = request.args.get('records_imported', 0, type=int)
    cleared = request.args.get('cleared', '')
    page = request.args.get('page', 1, type=int)
    sort = request.args.get('sort', 'count')  # Default sort by count
    sort_dir = request.args.get('dir', 'desc')  # Default direction is descending
    items_per_page = 100
    
    # Get build number
    build_number = get_build_number()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Count total unique descriptions
        cur.execute("SELECT COUNT(DISTINCT description) FROM records_imported")
        total_unique_descriptions = cur.fetchone()[0]
        
        # Count of tagged descriptions
        cur.execute("""
            SELECT COUNT(*) 
            FROM tags t
            WHERE EXISTS (
                SELECT 1 FROM records_imported ri
                WHERE ri.description = t.description
            )
        """)
        tagged_count = cur.fetchone()[0]
        
        # Count of total transactions
        cur.execute("SELECT COUNT(*) FROM records_imported")
        total_transactions = cur.fetchone()[0]
        
        # Count of total tagged transactions
        cur.execute("""
            SELECT COUNT(*) 
            FROM records_imported t
            JOIN tags tt ON t.description = tt.description
        """)
        total_tagged_transactions = cur.fetchone()[0]
        
        # Count of untagged descriptions
        total_untagged_descriptions = total_unique_descriptions - tagged_count if total_unique_descriptions else 0
        
        # Get count of transaction history
        history_count = get_history_count()
        
        # Get count of unique tags
        tags_count = get_tags_count()
        
        # Remaining to tag
        remaining_to_tag = total_transactions - total_tagged_transactions
        
        # Base query for transactions grouped by description
        query = """
            SELECT t.description, t.vendor, COUNT(*) as count, SUM(
                CASE 
                    WHEN t.amount ~ '^-?[0-9.,$]+$' 
                    THEN REPLACE(REPLACE(t.amount, ',', ''), '$', '')::numeric 
                    ELSE 0 
                END
            ) as total, tt.tag
            FROM records_imported t
            LEFT JOIN tags tt ON t.description = tt.description
        """
        
        # Add filter conditions
        where_clause = []
        params = []
        
        # Apply search filter if provided
        if search:
            where_clause.append("(t.description ILIKE %s OR t.vendor ILIKE %s)")
            params.extend(['%' + search + '%', '%' + search + '%'])
        
        # Apply tag filter
        if filter_type == 'tagged':
            where_clause.append("tt.id IS NOT NULL")
        elif filter_type == 'untagged':
            where_clause.append("tt.id IS NULL")
        
        if where_clause:
            query += " WHERE " + " AND ".join(where_clause)
        
        # Group by description, vendor, and tag
        query += " GROUP BY t.description, t.vendor, tt.tag"
        
        # Add sorting based on parameters
        if sort == 'description':
            query += f" ORDER BY t.description {sort_dir.upper()}"
        elif sort == 'amount':
            query += f""" ORDER BY SUM(
                CASE 
                    WHEN t.amount ~ '^-?[0-9.,$]+$' 
                    THEN REPLACE(REPLACE(t.amount, ',', ''), '$', '')::numeric 
                    ELSE 0 
                END
            ) {sort_dir.upper()}"""
        else:  # Default to count
            query += f" ORDER BY COUNT(*) {sort_dir.upper()}"
        
        # Execute count query for pagination
        count_query = "SELECT COUNT(*) FROM (" + query + ") as subquery"
        cur.execute(count_query, params)
        total_items = cur.fetchone()[0]
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        # Add pagination
        query += " LIMIT %s OFFSET %s"
        offset = (page - 1) * items_per_page
        params.extend([items_per_page, offset])
        
        # Execute final query
        cur.execute(query, params)
        transaction_data = cur.fetchall()
        
        # Format the results for display
        formatted_transactions = []
        for item in transaction_data:
            description, vendor, count, total, tag = item
            formatted_transactions.append({
                'description': description,
                'vendor': vendor,
                'count': count,
                'total': "${:,.2f}".format(float(total)) if total is not None else "$0.00",
                'tag': tag or ''
            })
        
        # Get existing tags for autocomplete and for template
        cur.execute("SELECT description, tag FROM tags ORDER BY tag")
        existing_tags = {}
        for row in cur.fetchall():
            existing_tags[row[0]] = row[1]
        
        # Get unique tag values for autocomplete
        cur.execute("SELECT DISTINCT tag FROM tags WHERE tag IS NOT NULL AND tag != '' ORDER BY tag")
        tag_values = [row[0] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return render_template_string(HTML_TEMPLATE, 
                                    transactions=formatted_transactions,
                                    existing_tags=existing_tags,
                                    tag_values=tag_values,
                                    page=page,
                                    total_pages=total_pages,
                                    search=search,
                                    filter=filter_type,
                                    auto_tagged=auto_tagged,
                                    unique_tags_applied=unique_tags_applied,
                                    total_transactions=total_transactions,
                                    tagged_count=tagged_count,
                                    total_tagged_transactions=total_tagged_transactions,
                                    total_untagged_descriptions=total_untagged_descriptions,
                                    history_count=history_count,
                                    tags_count=tags_count,
                                    total_unique_descriptions=total_unique_descriptions,
                                    moved_count=moved_count,
                                    tags_imported=tags_imported,
                                    history_imported=history_imported,
                                    records_imported=records_imported,
                                    cleared=cleared,
                                    remaining_to_tag=remaining_to_tag,
                                    build_number=build_number,
                                    sort=sort,
                                    sort_dir=sort_dir)
                
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/update_tag', methods=['POST'])
def update_tag():
    """Update or create a tag for a description"""
    description = request.form.get('description')
    tag = request.form.get('tag')
    page = request.form.get('page', 1)
    search = request.form.get('search', '')
    filter_type = request.form.get('filter', 'all')
    from_page = request.form.get('from_page', '')  # Get the source page parameter
    sort = request.form.get('sort', 'count')  # Get sort parameter
    sort_dir = request.form.get('sort_dir', 'desc')  # Get sort direction parameter
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Upsert tag - insert if not exists, update if exists
        cur.execute("""
            INSERT INTO tags (description, tag)
            VALUES (%s, %s)
            ON CONFLICT (description) 
            DO UPDATE SET tag = EXCLUDED.tag
        """, (description, tag))
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Check if we should redirect back to most_common
        if from_page == 'most_common':
            # Always filter by untagged for most_common page after tagging
            # This ensures the tagged item disappears
            return redirect(url_for('most_common', page=page, filter='untagged', sort=sort, dir=sort_dir))
        
        # Otherwise, redirect back to the index page as before
        redirect_url = url_for('index', page=page, sort=sort, dir=sort_dir)
        if search:
            redirect_url += f"&search={search}"
        if filter_type != 'all':
            redirect_url += f"&filter={filter_type}"
            
        return redirect(redirect_url)
        
    except Exception as e:
        return f"Error updating tag: {str(e)}"

@app.route('/auto_tag')
def auto_tag():
    """Auto-apply tags to transactions"""
    tags_applied = auto_apply_tags()
    return redirect(url_for('index', auto_tagged=tags_applied))

@app.route('/export_tags')
def export_tags():
    """Export tags as CSV file"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all tags
        cur.execute("""
            SELECT description, tag 
            FROM tags 
            ORDER BY tag, description
        """)
        
        tags = cur.fetchall()
        
        # Create CSV content
        csv_content = "description,tag\n"
        for tag in tags:
            # Properly escape fields that might contain commas or quotes
            description = tag[0].replace('"', '""')  # Double quotes to escape quotes
            tag_value = tag[1].replace('"', '""')
            
            # Always quote fields for consistent formatting
            description = f'"{description}"'
            tag_value = f'"{tag_value}"'
            
            csv_content += f"{description},{tag_value}\n"
        
        cur.close()
        conn.close()
        
        # Create response with CSV file
        from flask import Response
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=transaction_tags.csv"}
        )
        
    except Exception as e:
        return f"Error exporting tags: {str(e)}"

@app.route('/tag_all', methods=['GET', 'POST'])
def tag_all():
    """Tag all matching descriptions"""
    if request.method == 'POST':
        search_term = request.form.get('search', '')
        tag = request.form.get('tag', '').strip()
        filter_type = request.form.get('filter', 'all')
        from_page = request.form.get('from_page', 'index')
        sort = request.form.get('sort', 'count')
        sort_dir = request.form.get('sort_dir', 'desc')
    else:  # GET request from confirmation page
        search_term = request.args.get('search', '')
        tag = request.args.get('tag', '').strip()
        filter_type = request.args.get('filter', 'all')
        from_page = request.args.get('from_page', 'index')
        sort = request.args.get('sort', 'count')
        sort_dir = request.args.get('sort_dir', 'desc')
    
    if not tag:
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Find all descriptions that match the search term
        query = """
            SELECT DISTINCT description 
            FROM records_imported 
            WHERE description ILIKE %s
        """
        params = ['%' + search_term + '%']
        
        # Add tag filtering if needed
        if filter_type == 'tagged':
            query += " AND description IN (SELECT description FROM tags)"
        elif filter_type == 'untagged':
            query += " AND description NOT IN (SELECT description FROM tags)"
            
        cur.execute(query, params)
        matching_descriptions = cur.fetchall()
        
        # Insert or update tags for all matching descriptions
        for desc in matching_descriptions:
            cur.execute("""
                INSERT INTO tags (description, tag)
                VALUES (%s, %s)
                ON CONFLICT (description) 
                DO UPDATE SET tag = EXCLUDED.tag
            """, (desc[0], tag))
        
        conn.commit()
        cur.close()
        conn.close()
        
        unique_tags_applied = len(matching_descriptions)
        
        # Redirect back to the appropriate page
        if from_page == 'most_common':
            return redirect(url_for('most_common', filter=filter_type, unique_tags_applied=unique_tags_applied, sort=sort, dir=sort_dir))
        else:
            return redirect(url_for('index', search=search_term, filter=filter_type, unique_tags_applied=unique_tags_applied, sort=sort, dir=sort_dir))
        
    except Exception as e:
        return f"Error tagging all: {str(e)}"

@app.route('/row_count')
def row_count():
    """Get the total number of rows in the transactions table"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        cur.execute("SELECT COUNT(*) FROM transactions")
        count = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        return f"Total rows in transactions table: {count}"
    except Exception as e:
        return f"Error counting rows: {str(e)}"

@app.route('/check_duplicates')
def check_duplicates():
    """Check for duplicate rows in the transactions table"""
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Check for duplicates
        cur.execute("""
            SELECT date, description, amount, COUNT(*) as count
            FROM transactions
            GROUP BY date, description, amount
            HAVING COUNT(*) > 1
            ORDER BY count DESC
            LIMIT 10
        """)
        
        duplicates = cur.fetchall()
        
        # Count distinct rows
        cur.execute("""
            SELECT COUNT(*) FROM (
                SELECT DISTINCT date, description, amount
                FROM transactions
            ) as unique_rows
        """)
        
        unique_count = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        result = f"Total rows: 2750<br>Unique rows: {unique_count}<br><br>"
        
        if duplicates:
            result += "Top duplicates:<br><table border='1'><tr><th>Date</th><th>Description</th><th>Amount</th><th>Count</th></tr>"
            for dup in duplicates:
                result += f"<tr><td>{dup['date']}</td><td>{dup['description']}</td><td>{dup['amount']}</td><td>{dup['count']}</td></tr>"
            result += "</table>"
        else:
            result += "No duplicates found."
        
        return result
    except Exception as e:
        return f"Error checking duplicates: {str(e)}"

@app.route('/most_common')
def most_common():
    """Show the most common transactions sorted by count"""
    filter_type = request.args.get('filter', 'untagged')  # Default to untagged items
    page = request.args.get('page', 1, type=int)
    moved_count = request.args.get('moved_count', 0, type=int)
    records_imported = request.args.get('records_imported', 0, type=int)
    sort = request.args.get('sort', 'count')  # Default sort by count
    sort_dir = request.args.get('dir', 'desc')  # Default direction is descending
    items_per_page = 100
    
    # Get build number
    build_number = get_build_number()
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Count all descriptions that aren't tagged yet
        cur.execute("""
            SELECT COUNT(DISTINCT t.description)
            FROM records_imported t
            LEFT JOIN tags tt ON t.description = tt.description
            WHERE tt.id IS NULL
        """)
        untagged_descriptions_count = cur.fetchone()[0]
        
        # Count all unique descriptions
        cur.execute("SELECT COUNT(DISTINCT description) FROM records_imported")
        total_unique_descriptions = cur.fetchone()[0]
        
        # Count tagged descriptions
        cur.execute("""
            SELECT COUNT(*) 
            FROM tags t
            WHERE EXISTS (
                SELECT 1 FROM records_imported ri
                WHERE ri.description = t.description
            )
        """)
        tagged_count = cur.fetchone()[0]
        
        # Count total transactions
        cur.execute("SELECT COUNT(*) FROM records_imported")
        total_transactions = cur.fetchone()[0]
        
        # Count tagged transactions
        cur.execute("""
            SELECT COUNT(*) 
            FROM records_imported t
            JOIN tags tt ON t.description = tt.description
        """)
        total_tagged_transactions = cur.fetchone()[0]
        
        # Get count of transaction history
        history_count = get_history_count()
        
        # Get count of unique tags
        tags_count = get_tags_count()
        
        # Calculate remaining to tag
        remaining_to_tag = total_transactions - total_tagged_transactions
        
        # Build the query for most common descriptions
        query = """
            SELECT t.description, t.vendor, COUNT(*) as count, 
                   SUM(
                       CASE 
                           WHEN t.amount ~ '^-?[0-9.,$]+$' 
                           THEN REPLACE(REPLACE(t.amount, ',', ''), '$', '')::numeric 
                           ELSE 0 
                       END
                   ) as total_amount, 
                   tt.tag
            FROM records_imported t
            LEFT JOIN tags tt ON t.description = tt.description
        """
        
        # Apply filters
        params = []
        if filter_type == 'tagged':
            query += " WHERE tt.id IS NOT NULL"
        elif filter_type == 'untagged':
            query += " WHERE tt.id IS NULL"
        
        # Group by description, vendor, and tag
        query += " GROUP BY t.description, t.vendor, tt.tag"
        
        # Add dynamic sorting based on parameters
        if sort == 'description':
            query += f" ORDER BY t.description {sort_dir.upper()}"
        elif sort == 'amount':
            query += f""" ORDER BY SUM(
                CASE 
                    WHEN t.amount ~ '^-?[0-9.,$]+$' 
                    THEN REPLACE(REPLACE(t.amount, ',', ''), '$', '')::numeric 
                    ELSE 0 
                END
            ) {sort_dir.upper()}"""
        else:  # Default to count
            query += f" ORDER BY COUNT(*) {sort_dir.upper()}"
        
        # Count total results for pagination
        count_query = "SELECT COUNT(*) FROM (" + query + ") as subquery"
        cur.execute(count_query, params)
        total_items = cur.fetchone()[0]
        total_pages = (total_items + items_per_page - 1) // items_per_page
        
        # Add pagination
        query += " LIMIT %s OFFSET %s"
        offset = (page - 1) * items_per_page
        params.extend([items_per_page, offset])
        
        # Execute query
        cur.execute(query, params)
        transaction_data = cur.fetchall()
        
        # Format for display
        formatted_transactions = []
        for item in transaction_data:
            description, vendor, count, total, tag = item
            formatted_transactions.append({
                'description': description,
                'vendor': vendor,
                'count': count,
                'total': "${:,.2f}".format(float(total)) if total is not None else "$0.00",
                'tag': tag or ''
            })
        
        # Get existing tags for autocomplete and for template
        cur.execute("SELECT description, tag FROM tags ORDER BY tag")
        existing_tags = {}
        for row in cur.fetchall():
            existing_tags[row[0]] = row[1]
        
        # Get unique tag values for autocomplete
        cur.execute("SELECT DISTINCT tag FROM tags WHERE tag IS NOT NULL AND tag != '' ORDER BY tag")
        tag_values = [row[0] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        return render_template_string(HTML_TEMPLATE, 
                                    transactions=formatted_transactions,
                                    existing_tags=existing_tags,
                                    tag_values=tag_values,
                                    page=page,
                                    total_pages=total_pages,
                                    search="",
                                    filter=filter_type,
                                    auto_tagged=0,
                                    unique_tags_applied=0,
                                    total_transactions=total_transactions,
                                    tagged_count=tagged_count,
                                    total_tagged_transactions=total_tagged_transactions,
                                    total_untagged_descriptions=untagged_descriptions_count,
                                    history_count=history_count,
                                    tags_count=tags_count,
                                    total_unique_descriptions=total_unique_descriptions,
                                    moved_count=moved_count,
                                    records_imported=records_imported,
                                    remaining_to_tag=remaining_to_tag,
                                    build_number=build_number,
                                    sort=sort,
                                    sort_dir=sort_dir)
                
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/push_to_history', methods=['POST'])
def push_to_history():
    """Push all tagged transactions to history"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Insert tagged transactions into history
        cur.execute("""
            INSERT INTO records_history (date, description, vendor, amount, tag)
            SELECT t.date, t.description, t.vendor, t.amount, tt.tag
            FROM records_imported t
            JOIN tags tt ON t.description = tt.description
            WHERE NOT EXISTS (
                SELECT 1 FROM records_history h
                WHERE h.date = t.date AND h.description = t.description AND h.vendor = t.vendor AND h.amount = t.amount
            )
        """)
        
        # Count how many were moved
        moved_count = cur.rowcount
        
        # Delete tagged transactions from import table
        cur.execute("""
            DELETE FROM records_imported
            WHERE description IN (SELECT description FROM tags)
        """)
        
        # We no longer clear the tags table, keeping the tags for future matching
        
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('index', moved_count=moved_count))
        
    except Exception as e:
        return f"Error pushing to history: {str(e)}"

@app.route('/export_history')
def export_history():
    """Export all transactions from records_history as CSV file"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all transactions from history
        cur.execute("""
            SELECT date, description, vendor, amount, tag, imported_date
            FROM records_history 
            ORDER BY date, description
        """)
        
        transactions = cur.fetchall()
        
        # Create CSV content
        csv_content = "date,description,vendor,amount,tag,imported_date\n"
        for transaction in transactions:
            # Properly escape fields that might contain commas or quotes
            date = transaction[0].replace('"', '""') if transaction[0] else ""
            description = transaction[1].replace('"', '""') if transaction[1] else ""
            vendor = transaction[2].replace('"', '""') if transaction[2] else ""
            amount = transaction[3].replace('"', '""') if transaction[3] else ""
            tag = transaction[4].replace('"', '""') if transaction[4] else ""
            imported_date = transaction[5].strftime("%Y-%m-%d %H:%M:%S") if transaction[5] else ""
            
            # Always quote fields for consistent formatting
            date = f'"{date}"'
            description = f'"{description}"'
            vendor = f'"{vendor}"'
            amount = f'"{amount}"'
            tag = f'"{tag}"'
            imported_date = f'"{imported_date}"'
            
            csv_content += f"{date},{description},{vendor},{amount},{tag},{imported_date}\n"
        
        cur.close()
        conn.close()
        
        # Create response with CSV file
        from flask import Response
        return Response(
            csv_content,
            mimetype="text/csv",
            headers={"Content-disposition": "attachment; filename=records_history.csv"}
        )
        
    except Exception as e:
        return f"Error exporting history: {str(e)}"

@app.route('/import_tags', methods=['POST'])
def import_tags():
    """Import tags from a CSV file"""
    if 'tags_file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['tags_file']
    if file.filename == '':
        return redirect(url_for('index'))
    
    if file:
        try:
            # Read the CSV data
            csv_data = file.read().decode('utf-8')
            lines = csv_data.strip().split('\n')
            
            # Skip header line
            if len(lines) > 1:
                header = lines[0]
                data_lines = lines[1:]
                
                conn = get_db_connection()
                cur = conn.cursor()
                
                # Clear existing tags if requested
                clear_existing = request.form.get('clear_existing') == 'yes'
                if clear_existing:
                    cur.execute("TRUNCATE tags")
                
                # Process each line
                tags_imported = 0
                for line in data_lines:
                    # Handle quoted fields with commas
                    parts = []
                    in_quotes = False
                    current_part = ''
                    for char in line:
                        if char == '"':
                            in_quotes = not in_quotes
                        elif char == ',' and not in_quotes:
                            parts.append(current_part)
                            current_part = ''
                        else:
                            current_part += char
                    parts.append(current_part)
                    
                    if len(parts) >= 2:
                        description = parts[0].strip().strip('"')
                        tag = parts[1].strip().strip('"')
                        
                        # Insert or update tag
                        cur.execute("""
                            INSERT INTO tags (description, tag)
                            VALUES (%s, %s)
                            ON CONFLICT (description) 
                            DO UPDATE SET tag = EXCLUDED.tag
                        """, (description, tag))
                        tags_imported += 1
                
                conn.commit()
                cur.close()
                conn.close()
                
                return redirect(url_for('index', tags_imported=tags_imported))
                
        except Exception as e:
            return f"Error importing tags: {str(e)}"
    
    return redirect(url_for('index'))

@app.route('/import_history', methods=['POST'])
def import_history():
    """Import transaction history from a CSV file"""
    if 'history_file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['history_file']
    if file.filename == '':
        return redirect(url_for('index'))
    
    if file:
        try:
            # Read the CSV data
            csv_data = file.read().decode('utf-8')
            lines = csv_data.strip().split('\n')
            
            # Skip header line
            if len(lines) > 1:
                header = lines[0]
                data_lines = lines[1:]
                
                conn = get_db_connection()
                cur = conn.cursor()
                
                # Clear existing history if requested
                clear_existing = request.form.get('clear_existing') == 'yes'
                if clear_existing:
                    cur.execute("TRUNCATE records_history")
                
                # Process each line
                history_imported = 0
                for line in data_lines:
                    # Handle quoted fields with commas
                    parts = []
                    in_quotes = False
                    current_part = ''
                    for char in line:
                        if char == '"':
                            in_quotes = not in_quotes
                        elif char == ',' and not in_quotes:
                            parts.append(current_part)
                            current_part = ''
                        else:
                            current_part += char
                    parts.append(current_part)
                    
                    if len(parts) >= 5:  # At least date, description, vendor, amount, tag
                        date = parts[0].strip().strip('"')
                        description = parts[1].strip().strip('"')
                        vendor = parts[2].strip().strip('"')
                        amount = parts[3].strip().strip('"')
                        tag = parts[4].strip().strip('"')
                        
                        # Insert into transaction_history
                        cur.execute("""
                            INSERT INTO records_history (date, description, vendor, amount, tag)
                            VALUES (%s, %s, %s, %s, %s)
                            ON CONFLICT DO NOTHING
                        """, (date, description, vendor, amount, tag))
                        history_imported += 1
                
                conn.commit()
                cur.close()
                conn.close()
                
                return redirect(url_for('index', history_imported=history_imported))
                
        except Exception as e:
            return f"Error importing history: {str(e)}"
    
    return redirect(url_for('index'))

@app.route('/import_records', methods=['POST'])
def import_records():
    """Import new transactions from a CSV file"""
    if 'records_file' not in request.files:
        return redirect(url_for('index'))
    
    file = request.files['records_file']
    if file.filename == '':
        return redirect(url_for('index'))
    
    if file:
        try:
            # Read the CSV data
            csv_data = file.read().decode('utf-8')
            # Clean up any unexpected characters
            csv_data = csv_data.replace('%', '')  # Remove % characters
            lines = csv_data.strip().split('\n')
            
            # Skip header line
            if len(lines) > 1:
                header = lines[0]
                data_lines = lines[1:]
                
                conn = get_db_connection()
                cur = conn.cursor()
                
                # Clear existing records if requested
                clear_existing = request.form.get('clear_existing') == 'yes'
                if clear_existing:
                    cur.execute("TRUNCATE records_imported")
                
                # Process each line
                records_imported = 0
                errors = 0
                
                for line in data_lines:
                    try:
                        # Skip empty lines
                        if not line.strip():
                            continue
                            
                        # Handle quoted fields with commas
                        parts = []
                        in_quotes = False
                        current_part = ''
                        for char in line:
                            if char == '"':
                                in_quotes = not in_quotes
                            elif char == ',' and not in_quotes:
                                parts.append(current_part)
                                current_part = ''
                            else:
                                current_part += char
                        parts.append(current_part)
                        
                        # Ensure we have enough parts (at least date, description, vendor, amount)
                        if len(parts) >= 4:
                            date = parts[0].strip().strip('"')
                            description = parts[1].strip().strip('"')
                            vendor = parts[2].strip().strip('"')
                            amount = parts[3].strip().strip('"')
                            
                            # Insert into records_imported
                            cur.execute("""
                                INSERT INTO records_imported (date, description, vendor, amount)
                                VALUES (%s, %s, %s, %s)
                                ON CONFLICT DO NOTHING
                            """, (date, description, vendor, amount))
                            records_imported += 1
                        else:
                            errors += 1
                            print(f"Skipping invalid line: {line} - not enough fields ({len(parts)})")
                    except Exception as line_error:
                        errors += 1
                        print(f"Error processing line: {line} - {str(line_error)}")
                
                conn.commit()
                cur.close()
                conn.close()
                
                # Log import results
                print(f"Import complete: {records_imported} records imported, {errors} errors")
                
                # Auto-apply tags to newly imported records
                if records_imported > 0:
                    try:
                        auto_tagged = auto_apply_tags()
                        return redirect(url_for('index', records_imported=records_imported, auto_tagged=auto_tagged))
                    except Exception as auto_tag_error:
                        import traceback
                        error_msg = f"Import was successful with {records_imported} records, but auto-tagging failed: {str(auto_tag_error)}"
                        print(error_msg)
                        traceback.print_exc()
                        # Still redirect to index but without auto_tagged parameter
                        return redirect(url_for('index', records_imported=records_imported))
                
                return redirect(url_for('index', records_imported=records_imported))
                
        except Exception as e:
            import traceback
            print(f"Error importing records: {str(e)}")
            traceback.print_exc()
            return f"Error importing records: {str(e)}"
    
    return redirect(url_for('index'))

@app.route('/clear_database', methods=['POST'])
def clear_database():
    """Clear database tables"""
    try:
        tables_to_clear = request.form.getlist('tables')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        for table in tables_to_clear:
            if table in ['records_imported', 'tags', 'records_history']:
                cur.execute(f"TRUNCATE {table}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('index', cleared=','.join(tables_to_clear)))
        
    except Exception as e:
        return f"Error clearing tables: {str(e)}"

@app.route('/monthly_summary')
def monthly_summary():
    """
    Display spending summary grouped by month with detailed daily transactions.
    """
    # Get connection through the existing function
    conn = get_db_connection()
    cursor = conn.cursor()

    # Get monthly aggregated data for totals
    cursor.execute("""
        SELECT 
            TO_CHAR(date::date, 'YYYY-MM') as year_month,
            TO_CHAR(date::date, 'MM') as month_num,
            TO_CHAR(date::date, 'YYYY') as year,
            TO_CHAR(date::date, 'Month') as month_name,
            tag, 
            SUM(amount::numeric) as total_amount, 
            COUNT(*) as transaction_count 
        FROM records_history 
        GROUP BY year_month, month_num, year, month_name, tag 
        ORDER BY year_month DESC, tag
    """)
    
    monthly_data = cursor.fetchall()
    
    # Process and format monthly data
    months = []
    current_month = None
    
    month_order = {
        "01": 1, "02": 2, "03": 3, "04": 4, "05": 5, "06": 6,
        "07": 7, "08": 8, "09": 9, "10": 10, "11": 11, "12": 12
    }
    
    for row in monthly_data:
        year_month = row[0]
        month_num = row[1]
        year = row[2]
        month_name = row[3].strip()
        tag = row[4]
        total_amount = row[5]
        transaction_count = row[6]
        
        if current_month is None or current_month['year_month'] != year_month:
            current_month = {
                'year_month': year_month,
                'month_name': month_name,
                'month_num': month_num,
                'month_order': month_order.get(month_num, 99),  # For sorting
                'year': year,
                'entries': [],
                'total': 0,
                'credits_total': 0,
                'debits_total': 0
            }
            months.append(current_month)
        
        current_month['entries'].append({
            'tag': tag,
            'amount': total_amount,
            'count': transaction_count
        })
        current_month['total'] += float(total_amount if total_amount is not None else 0)
        
        # Track credits and debits separately
        if total_amount > 0:
            current_month['credits_total'] += float(total_amount)
        else:
            current_month['debits_total'] += float(abs(total_amount))
    
    # Sort months by month number (1-12) chronologically
    sorted_months = sorted(months, key=lambda x: x['month_order'])
    
    # Get all transactions for detailed view
    cursor.execute("""
        SELECT 
            TO_CHAR(date::date, 'YYYY-MM') as year_month,
            TO_CHAR(date::date, 'MM') as month_num,
            TO_CHAR(date::date, 'Month') as month_name,
            TO_CHAR(date::date, 'DD') as day,
            date::date as full_date, 
            description, 
            tag, 
            amount::numeric as amount
        FROM records_history 
        ORDER BY full_date ASC
    """)
    
    transactions = cursor.fetchall()
    
    # Group transactions by month
    monthly_transactions = []
    
    for month in sorted_months:
        month_data = {
            'year_month': month['year_month'],
            'month_name': month['month_name'],
            'month_num': month['month_num'],
            'year': month['year'],
            'transactions': [],
            'total': month['total'],
            'credits_total': month['credits_total'],
            'debits_total': month['debits_total']
        }
        
        # Get all transactions for this month and sort by day
        month_txs = []
        for tx in transactions:
            if tx[0] == month['year_month']:  # Match year_month
                month_txs.append({
                    'day': tx[3],
                    'date': tx[4],
                    'description': tx[5],
                    'tag': tx[6] or 'Untagged',
                    'amount': tx[7],
                    'formatted_amount': "${:,.2f}".format(abs(tx[7])) if tx[7] >= 0 else "-${:,.2f}".format(abs(tx[7]))
                })
        
        # Sort transactions by day
        month_data['transactions'] = sorted(month_txs, key=lambda x: int(x['day']))
        monthly_transactions.append(month_data)
    
    # Get transaction and tag counts
    cursor.execute("SELECT COUNT(*) FROM records_history")
    history_count = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(DISTINCT tag) FROM tags")
    tags_count = cursor.fetchone()[0]
    
    # Get build number
    build_number = get_build_number()
    
    conn.close()
    
    return render_template_string(
        MONTHLY_TEMPLATE,
        months=sorted_months,
        monthly_transactions=monthly_transactions,
        history_count=history_count,
        tags_count=tags_count,
        build_number=build_number
    )

@app.route('/tag_summary')
def tag_summary_view():
    """Show summary by tag"""
    try:
        # Get filter and sort parameters
        year = request.args.get('year', 'all')
        month = request.args.get('month', 'all')
        sort = request.args.get('sort', 'amount')
        sort_dir = request.args.get('dir', 'desc')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get build number
        build_number = get_build_number()
        
        # Get available years and months from the records_history table
        cur.execute("""
            SELECT DISTINCT EXTRACT(YEAR FROM date::date) as year
            FROM records_history
            WHERE date IS NOT NULL
            ORDER BY year DESC
        """)
        available_years = [int(row[0]) for row in cur.fetchall()]
        
        # Get available months
        cur.execute("""
            SELECT DISTINCT EXTRACT(MONTH FROM date::date) as month
            FROM records_history
            WHERE date IS NOT NULL
            ORDER BY month
        """)
        available_months = [int(row[0]) for row in cur.fetchall()]
        
        # Base query with optional year and month filtering
        query = """
            SELECT tag, SUM(
                CASE 
                    WHEN amount ~ '^-?[0-9.,$]+$' 
                    THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric 
                    ELSE 0 
                END
            ) as total_amount, COUNT(*) as transaction_count
            FROM records_history rh
            WHERE 1=1
        """
        params = []
        
        # Add year filter if specified
        if year != 'all':
            query += " AND EXTRACT(YEAR FROM date::date) = %s"
            params.append(int(year))
        
        # Add month filter if specified
        if month != 'all':
            query += " AND EXTRACT(MONTH FROM date::date) = %s"
            params.append(int(month))
        
        # Group by tag
        query += " GROUP BY tag"
        
        # Add sorting based on parameters
        if sort == 'tag':
            query += f" ORDER BY tag {sort_dir.upper()} NULLS LAST"
        elif sort == 'count':
            query += f" ORDER BY transaction_count {sort_dir.upper()}"
        else:  # Default to amount
            query += f" ORDER BY total_amount {sort_dir.upper()}"
        
        # Execute the query
        cur.execute(query, params)
        tag_data = cur.fetchall()
        
        # Format for display
        formatted_tags = []
        total_amount = 0
        
        for row in tag_data:
            tag, amount, count = row
            formatted_tags.append({
                'tag': tag or 'Untagged',
                'amount': amount,
                'count': count
            })
            total_amount += float(amount) if amount else 0
        
        # Get the count of transactions in history
        history_count = get_history_count()
        
        cur.close()
        conn.close()
        
        return render_template_string(TAG_SUMMARY_TEMPLATE,
                                     tags=formatted_tags,
                                     total_amount=total_amount,
                                     history_count=history_count,
                                     build_number=build_number,
                                     year=year,
                                     month=month,
                                     available_years=available_years,
                                     available_months=available_months,
                                     sort=sort,
                                     sort_dir=sort_dir)
    
    except Exception as e:
        return f"Error generating tag summary: {str(e)}"

@app.route('/tag_all_confirmation', methods=['POST'])
def tag_all_confirmation():
    """Check if confirmation is needed before tagging all matching transactions"""
    search_term = request.form.get('search', '')
    tag = request.form.get('tag', '').strip()
    filter_type = request.form.get('filter', 'all')
    from_page = request.form.get('from_page', 'index')
    sort = request.form.get('sort', 'count')
    sort_dir = request.form.get('sort_dir', 'desc')
    
    if not tag:
        if from_page == 'most_common':
            return redirect(url_for('most_common'))
        else:
            return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # First, find all matching descriptions
        query = """
            SELECT DISTINCT description 
            FROM records_imported 
            WHERE description ILIKE %s
        """
        params = ['%' + search_term + '%']
        
        # Add tag filtering if needed
        if filter_type == 'tagged':
            query += " AND description IN (SELECT description FROM tags)"
        elif filter_type == 'untagged':
            query += " AND description NOT IN (SELECT description FROM tags)"
        
        cur.execute(query, params)
        matching_descriptions = cur.fetchall()
        
        # Now count the total number of transactions that will be affected
        total_transactions_query = """
            SELECT COUNT(*) 
            FROM records_imported 
            WHERE description ILIKE %s
        """
        params = ['%' + search_term + '%']
        
        # Add tag filtering if needed
        if filter_type == 'tagged':
            total_transactions_query += " AND description IN (SELECT description FROM tags)"
        elif filter_type == 'untagged':
            total_transactions_query += " AND description NOT IN (SELECT description FROM tags)"
        
        cur.execute(total_transactions_query, params)
        total_transactions_count = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        # Show confirmation if either distinct descriptions OR total transactions exceed 10
        if len(matching_descriptions) <= 10 and total_transactions_count <= 10:
            return redirect(url_for('tag_all', 
                                    search=search_term, 
                                    tag=tag, 
                                    filter=filter_type, 
                                    from_page=from_page,
                                    sort=sort,
                                    sort_dir=sort_dir))
        
        # Otherwise, show confirmation page with both counts
        return render_template('confirm_tag_all.html', 
                               count=total_transactions_count,
                               distinct_count=len(matching_descriptions), 
                               search=search_term,
                               tag=tag,
                               filter=filter_type,
                               from_page=from_page,
                               sort=sort,
                               sort_dir=sort_dir)
        
    except Exception as e:
        return f"Error checking transactions count: {str(e)}"

# HTML template for monthly summary
MONTHLY_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Monthly Spending Summary</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        .container {
            width: 100%;
        }
        h1, h2, h3 {
            color: #333;
        }
        .month-card {
            margin-bottom: 30px;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
            background-color: #f9f9f9;
        }
        .month-header {
            display: flex;
            justify-content: space-between;
            border-bottom: 1px solid #ddd;
            padding-bottom: 10px;
            margin-bottom: 15px;
        }
        .month-total {
            font-weight: bold;
            font-size: 1.2em;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        th, td {
            text-align: left;
            padding: 8px;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        .negative {
            color: #d9534f;
        }
        .positive {
            color: #5cb85c;
        }
        .nav-links {
            margin-bottom: 20px;
        }
        .nav-links a {
            margin-right: 15px;
            text-decoration: none;
            color: #007bff;
        }
        .transaction {
            padding: 8px 0;
            border-bottom: 1px solid #f0f0f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .transaction:last-child {
            border-bottom: none;
        }
        .transaction-description {
            flex-grow: 1;
        }
        .transaction-tag {
            background-color: #e6f7ff;
            padding: 3px 8px;
            border-radius: 10px;
            font-size: 0.85em;
            margin-left: 10px;
            min-width: 100px;
            text-align: center;
        }
        .transaction-amount {
            font-weight: bold;
            margin-left: 20px;
            min-width: 100px;
            text-align: right;
        }
        .transaction-day {
            min-width: 40px;
            text-align: center;
            font-weight: bold;
            color: #666;
        }
        .tag-summary {
            margin-top: 20px;
        }
        .month-summary {
            display: flex;
            justify-content: flex-end;
            margin-top: 20px;
            padding-top: 15px;
            border-top: 2px solid #ddd;
        }
        .summary-box {
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 10px 15px;
            margin-left: 15px;
            background-color: #f5f5f5;
            min-width: 150px;
        }
        .summary-label {
            font-weight: bold;
            margin-bottom: 5px;
        }
        .summary-value {
            font-size: 1.1em;
        }
        .build-info {
            position: absolute;
            top: 10px;
            right: 20px;
            padding: 5px 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
            font-size: 12px;
            color: #6c757d;
            border: 1px solid #dee2e6;
        }
        .transactions-list {
            margin-top: 20px;
        }
        .month-subtitle {
            margin-top: 15px;
            margin-bottom: 10px;
            padding-bottom: 5px;
            border-bottom: 1px solid #ddd;
            font-size: 1.2em;
        }
    </style>
</head>
<body>
    <div class="build-info">Build: {{ build_number }}</div>
    <div class="container">
        <h1>Monthly Spending Summary</h1>
        
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/data_import_tagging">Data Import and Tagging</a>
            <a href="/tag_summary">Tag Summary</a>
            <a href="/monthly_summary">Monthly Summary</a>
        </div>
        
        <div class="stats">
            <p>Total transactions in history: <strong>{{ history_count }}</strong></p>
            <p>Unique tags: <strong>{{ tags_count }}</strong></p>
        </div>
        
        {% for month_data in monthly_transactions %}
        <div class="month-card">
            <div class="month-header">
                <h2>{{ month_data.month_name }} {{ month_data.year }}</h2>
                <span class="month-total {% if month_data.total < 0 %}negative{% else %}positive{% endif %}">
                    Total: {% if month_data.total >= 0 %}${{ "%.2f"|format(month_data.total|float) }}{% else %}-${{ "%.2f"|format((month_data.total|float)|abs) }}{% endif %}
                </span>
            </div>
            
            <div class="transactions-list">
                <div class="month-subtitle">Transactions ({{ month_data.transactions|length }})</div>
                {% if month_data.transactions %}
                    {% for tx in month_data.transactions %}
                    <div class="transaction">
                        <div class="transaction-day">{{ tx.day }}</div>
                        <div class="transaction-description">{{ tx.description }}</div>
                        <div class="transaction-tag">{{ tx.tag }}</div>
                        <div class="transaction-amount {% if '-' in tx.formatted_amount %}negative{% else %}positive{% endif %}">
                            {{ tx.formatted_amount }}
                        </div>
                    </div>
                    {% endfor %}
                {% else %}
                    <p>No transactions found for this month.</p>
                {% endif %}
            </div>
            
            <div class="month-summary">
                <div class="summary-box">
                    <div class="summary-label">Credits</div>
                    <div class="summary-value positive">${{ "%.2f"|format(month_data.credits_total|float) }}</div>
                </div>
                <div class="summary-box">
                    <div class="summary-label">Debits</div>
                    <div class="summary-value negative">${{ "%.2f"|format(month_data.debits_total|float) }}</div>
                </div>
                <div class="summary-box">
                    <div class="summary-label">Net</div>
                    <div class="summary-value {% if month_data.total < 0 %}negative{% else %}positive{% endif %}">
                        {% if month_data.total >= 0 %}${{ "%.2f"|format(month_data.total|float) }}{% else %}-${{ "%.2f"|format((month_data.total|float)|abs) }}{% endif %}
                    </div>
                </div>
            </div>
            
            <div class="tag-summary">
                <h3>Totals by Tag</h3>
                <table>
                    <thead>
                        <tr>
                            <th>Tag</th>
                            <th>Amount</th>
                            <th>Transactions</th>
                        </tr>
                    </thead>
                    <tbody>
                        {% for month in months %}
                            {% if month.year_month == month_data.year_month %}
                                {% for entry in month.entries %}
                                <tr>
                                    <td>{{ entry.tag }}</td>
                                    <td {% if entry.amount < 0 %}class="negative"{% else %}class="positive"{% endif %}>
                                        {% if entry.amount >= 0 %}${{ "%.2f"|format(entry.amount|float) }}{% else %}-${{ "%.2f"|format((entry.amount|float)|abs) }}{% endif %}
                                    </td>
                                    <td>{{ entry.count }}</td>
                                </tr>
                                {% endfor %}
                            {% endif %}
                        {% endfor %}
                    </tbody>
                </table>
            </div>
        </div>
        {% endfor %}
    </div>
</body>
</html>
"""

# HTML template for tag summary
TAG_SUMMARY_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Tag Summary</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        .container {
            width: 100%;
        }
        h1, h2, h3 {
            color: #333;
        }
        .tag-container {
            margin-top: 20px;
        }
        .total-section {
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f2f2f2;
            border-radius: 5px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            text-align: left;
            padding: 12px 8px;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        th a {
            color: inherit;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .negative {
            color: #d9534f;
        }
        .positive {
            color: #5cb85c;
        }
        .nav-links {
            margin-bottom: 20px;
        }
        .nav-links a {
            margin-right: 15px;
            text-decoration: none;
            color: #007bff;
        }
        .build-info {
            position: absolute;
            top: 10px;
            right: 20px;
            padding: 5px 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
            font-size: 12px;
            color: #6c757d;
            border: 1px solid #dee2e6;
        }
        .filter-section {
            background-color: #e6ffe6;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
            border: 1px solid #99cc99;
            display: flex;
            align-items: center;
        }
        .filter-section label {
            font-weight: bold;
            margin-right: 10px;
        }
        .filter-section select {
            padding: 8px;
            margin-right: 15px;
            border-radius: 4px;
            border: 1px solid #ddd;
        }
        .filter-section button {
            padding: 8px 15px;
            background-color: #28a745;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
    </style>
</head>
<body>
    <div class="build-info">Build: {{ build_number }}</div>
    <div class="container">
        <h1>Tag Summary</h1>
        
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/data_import_tagging">Data Import and Tagging</a>
            <a href="/tag_summary">Tag Summary</a>
            <a href="/monthly_summary">Monthly Summary</a>
        </div>
        
        <div class="filter-section">
            <span style="font-weight: bold; margin-right: 10px;">FILTER:</span>
            <form method="GET" action="/tag_summary">
                <input type="hidden" name="sort" value="{{ sort }}">
                <input type="hidden" name="dir" value="{{ sort_dir }}">
                
                <label for="year">Year:</label>
                <select name="year" id="year">
                    <option value="all" {% if year == 'all' %}selected{% endif %}>All Years</option>
                    {% for y in available_years %}
                    <option value="{{ y }}" {% if year|string == y|string %}selected{% endif %}>{{ y }}</option>
                    {% endfor %}
                </select>
                
                <label for="month">Month:</label>
                <select name="month" id="month">
                    <option value="all" {% if month == 'all' %}selected{% endif %}>All Months</option>
                    <option value="1" {% if month|string == '1' %}selected{% endif %}>January</option>
                    <option value="2" {% if month|string == '2' %}selected{% endif %}>February</option>
                    <option value="3" {% if month|string == '3' %}selected{% endif %}>March</option>
                    <option value="4" {% if month|string == '4' %}selected{% endif %}>April</option>
                    <option value="5" {% if month|string == '5' %}selected{% endif %}>May</option>
                    <option value="6" {% if month|string == '6' %}selected{% endif %}>June</option>
                    <option value="7" {% if month|string == '7' %}selected{% endif %}>July</option>
                    <option value="8" {% if month|string == '8' %}selected{% endif %}>August</option>
                    <option value="9" {% if month|string == '9' %}selected{% endif %}>September</option>
                    <option value="10" {% if month|string == '10' %}selected{% endif %}>October</option>
                    <option value="11" {% if month|string == '11' %}selected{% endif %}>November</option>
                    <option value="12" {% if month|string == '12' %}selected{% endif %}>December</option>
                </select>
                
                <button type="submit">Apply Filter</button>
            </form>
        </div>
        
        <div class="total-section">
            <h3>Total: <span {% if total_amount < 0 %}class="negative"{% else %}class="positive"{% endif %}>
                ${{ '{:,.2f}'.format(total_amount|abs) }}
            </span></h3>
            <p>Total transactions in history: <strong>{{ history_count }}</strong></p>
            
            {% if year != 'all' or month != 'all' %}
            <p>
                Filtering: 
                {% if month != 'all' %}
                    {% set month_names = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'} %}
                    {{ month_names[month|int] }} 
                {% endif %}
                {% if year != 'all' %}
                    {{ year }}
                {% endif %}
                <a href="/tag_summary" style="font-size: 0.8em; margin-left: 10px;">[Clear Filters]</a>
            </p>
            {% endif %}
        </div>
        
        <div class="tag-container">
            <table>
                <thead>
                    <tr>
                        <th><a href="/tag_summary?sort=tag&dir={% if sort == 'tag' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}">Tag {% if sort == 'tag' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                        <th><a href="/tag_summary?sort=amount&dir={% if sort == 'amount' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}">Amount {% if sort == 'amount' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                        <th><a href="/tag_summary?sort=count&dir={% if sort == 'count' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}">Transactions {% if sort == 'count' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                    </tr>
                </thead>
                <tbody>
                    {% for tag in tags %}
                    <tr>
                        <td>{{ tag.tag }}</td>
                        <td {% if tag.amount < 0 %}class="negative"{% else %}class="positive"{% endif %}>
                            ${{ '{:,.2f}'.format(tag.amount|abs) }}
                        </td>
                        <td>{{ tag.count }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        
        {% if not tags %}
        <div style="margin-top: 20px; padding: 15px; background-color: #f9f9f9; border-radius: 5px;">
            <p>No tag data available. Import your transaction history to see spending patterns by tag.</p>
        </div>
        {% endif %}
    </div>
</body>
</html>
"""

@app.route('/historical_analysis')
def historical_analysis():
    """Show historical analysis with charts and data tables"""
    try:
        # Get filter parameters
        year = request.args.get('year', 'all')
        month = request.args.get('month', 'all')
        tag = request.args.get('tag', 'all')
        sort = request.args.get('sort', 'date')
        sort_dir = request.args.get('dir', 'desc')
        start_date = request.args.get('start_date', '')
        end_date = request.args.get('end_date', '')

        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get build number
        build_number = get_build_number()
        
        # Get available years from the records_history table
        cur.execute("""
            SELECT DISTINCT EXTRACT(YEAR FROM date::date) as year
            FROM records_history
            WHERE date IS NOT NULL
            ORDER BY year DESC
        """)
        available_years = [int(row[0]) for row in cur.fetchall()]
        
        # Get available tags
        cur.execute("""
            SELECT DISTINCT tag
            FROM records_history
            WHERE tag IS NOT NULL AND tag != ''
            ORDER BY tag
        """)
        available_tags = [row[0] for row in cur.fetchall()]

        # Base query for filtering based on selected parameters
        where_clauses = ["date IS NOT NULL"]
        params = []
        
        # Add date range filters
        if start_date and end_date:
            where_clauses.append("date::date BETWEEN %s AND %s")
            params.extend([start_date, end_date])
        else:
            # Add year filter if specified
            if year != 'all':
                where_clauses.append("EXTRACT(YEAR FROM date::date) = %s")
                params.append(int(year))
            
            # Add month filter if specified
            if month != 'all':
                where_clauses.append("EXTRACT(MONTH FROM date::date) = %s")
                params.append(int(month))
        
        # Add tag filter if specified
        if tag != 'all':
            where_clauses.append("tag = %s")
            params.append(tag)
        
        # Build where clause
        where_clause = " AND ".join(where_clauses)
        
        # Get chart data based on selected filters
        chart_data = get_chart_data(conn, where_clause, params, year, month)
        
        # Get summary statistics
        summary_stats = get_summary_stats(conn, where_clause, params)
        
        # Get transactions for the selected filters with sorting
        transactions_query = f"""
            SELECT date, description, amount, tag,
                   EXTRACT(MONTH FROM date::date) as month_num,
                   EXTRACT(DAY FROM date::date) as day_num
            FROM records_history
            WHERE {where_clause}
        """
        
        # Add sorting
        if sort == 'date':
            # Sort by year, month, day numerically for chronological order
            transactions_query += f"""
                ORDER BY 
                    EXTRACT(YEAR FROM date::date) {sort_dir.upper()},
                    EXTRACT(MONTH FROM date::date) {sort_dir.upper()},
                    EXTRACT(DAY FROM date::date) {sort_dir.upper()}
            """
        elif sort == 'description':
            transactions_query += f" ORDER BY description {sort_dir.upper()}"
        elif sort == 'amount':
            transactions_query += f""" ORDER BY CASE 
                WHEN amount ~ '^-?[0-9.,$]+$' 
                THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric 
                ELSE 0 
                END {sort_dir.upper()}"""
        elif sort == 'tag':
            transactions_query += f" ORDER BY tag {sort_dir.upper()} NULLS LAST"
        
        cur.execute(transactions_query, params)
        transactions = []
        
        for row in cur.fetchall():
            date_str, description, amount, tx_tag, month_num, day_num = row
            # Fix the date formatting - check if date_str is already a string or a datetime object
            formatted_date = ''
            if date_str:
                if hasattr(date_str, 'strftime'):
                    # Format as MM/DD/YYYY for better readability
                    formatted_date = date_str.strftime('%m/%d/%Y')
                else:
                    # It's already a string, try to parse and reformat
                    try:
                        from datetime import datetime
                        date_obj = datetime.strptime(str(date_str), '%Y-%m-%d')
                        formatted_date = date_obj.strftime('%m/%d/%Y')
                    except:
                        # Use as is if parsing fails
                        formatted_date = str(date_str)
                    
            transactions.append({
                'date': formatted_date,
                'description': description,
                'amount': amount,
                'tag': tx_tag or '',
                'month_num': int(month_num) if month_num is not None else 0,
                'day_num': int(day_num) if day_num is not None else 0
            })
        
        cur.close()
        conn.close()
        
        return render_template_string(HISTORICAL_ANALYSIS_TEMPLATE,
                                     chart_data=chart_data,
                                     transactions=transactions,
                                     available_years=available_years,
                                     available_tags=available_tags,
                                     year=year,
                                     month=month,
                                     tag=tag,
                                     sort=sort,
                                     sort_dir=sort_dir,
                                     start_date=start_date,
                                     end_date=end_date,
                                     summary_stats=summary_stats,
                                     build_number=build_number)
    
    except Exception as e:
        return f"Error generating historical analysis: {str(e)}"

def get_chart_data(conn, where_clause, params, year, month):
    """Get chart data for the given filters"""
    cur = conn.cursor()
    
    # Determine time grouping (daily or weekly)
    group_by_day = month != 'all'
    
    if group_by_day:
        # Group by day
        chart_query = f"""
            SELECT date::date as period_date,
                   SUM(CASE WHEN amount ~ '^-?[0-9.,$]+$' AND REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric < 0 
                       THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric ELSE 0 END) as debits,
                   SUM(CASE WHEN amount ~ '^-?[0-9.,$]+$' AND REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric > 0 
                       THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric ELSE 0 END) as credits
            FROM records_history
            WHERE {where_clause}
            GROUP BY period_date
            ORDER BY period_date
        """
    else:
        # Group by week (each week starting on the 1st, 8th, 15th, 22nd of the month)
        chart_query = f"""
            SELECT 
                CASE 
                    WHEN EXTRACT(DAY FROM date::date) < 8 THEN date_trunc('month', date::date) + INTERVAL '0 days'
                    WHEN EXTRACT(DAY FROM date::date) < 15 THEN date_trunc('month', date::date) + INTERVAL '7 days'
                    WHEN EXTRACT(DAY FROM date::date) < 22 THEN date_trunc('month', date::date) + INTERVAL '14 days'
                    ELSE date_trunc('month', date::date) + INTERVAL '21 days'
                END as period_date,
                SUM(CASE WHEN amount ~ '^-?[0-9.,$]+$' AND REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric < 0 
                    THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric ELSE 0 END) as debits,
                SUM(CASE WHEN amount ~ '^-?[0-9.,$]+$' AND REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric > 0 
                    THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric ELSE 0 END) as credits
            FROM records_history
            WHERE {where_clause}
            GROUP BY period_date
            ORDER BY period_date
        """
    
    cur.execute(chart_query, params)
    results = cur.fetchall()
    
    # Format data for Chart.js
    dates = []
    debits = []
    credits = []
    income = []
    
    running_income = 0
    
    for row in results:
        period_date, debit_sum, credit_sum = row
        period_date_str = period_date.strftime('%Y-%m-%d')
        
        # Store period label (date)
        dates.append(period_date_str)
        
        # Store debit value (negative)
        debits.append(float(debit_sum or 0))
        
        # Store credit value (positive)
        credits.append(float(credit_sum or 0))
        
        # Calculate running total income
        period_income = float(credit_sum or 0) + float(debit_sum or 0)  # debit is already negative
        running_income += period_income
        income.append(running_income)
    
    # Prepare final chart data
    chart_data = {
        'labels': dates,
        'debits': debits,
        'credits': credits,
        'income': income
    }
    
    cur.close()
    return chart_data

def get_summary_stats(conn, where_clause, params):
    """Get summary statistics for the selected period"""
    cur = conn.cursor()
    
    stats_query = f"""
        SELECT 
            COUNT(*) as transaction_count,
            SUM(CASE WHEN amount ~ '^-?[0-9.,$]+$' AND REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric < 0 
                THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric ELSE 0 END) as total_debits,
            SUM(CASE WHEN amount ~ '^-?[0-9.,$]+$' AND REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric > 0 
                THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric ELSE 0 END) as total_credits,
            SUM(CASE WHEN amount ~ '^-?[0-9.,$]+$' 
                THEN REPLACE(REPLACE(amount, ',', ''), '$', '')::numeric ELSE 0 END) as net_income
        FROM records_history
        WHERE {where_clause}
    """
    
    cur.execute(stats_query, params)
    row = cur.fetchone()
    
    if row:
        transaction_count, total_debits, total_credits, net_income = row
        
        # Calculate net savings as a percentage of total credits
        net_savings_pct = 0
        if total_credits and float(total_credits) > 0:
            net_savings_pct = (float(net_income or 0) / float(total_credits or 1)) * 100
        
        summary_stats = {
            'transaction_count': transaction_count,
            'total_debits': "${:,.2f}".format(float(total_debits or 0)),
            'total_credits': "${:,.2f}".format(float(total_credits or 0)),
            'net_income': "${:,.2f}".format(float(net_income or 0)),
            'net_savings_pct': "{:.1f}%".format(net_savings_pct)
        }
    else:
        summary_stats = {
            'transaction_count': 0,
            'total_debits': "$0.00",
            'total_credits': "$0.00",
            'net_income': "$0.00",
            'net_savings_pct': "0.0%"
        }
    
    cur.close()
    return summary_stats

# HTML template for historical analysis
HISTORICAL_ANALYSIS_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Gotham Engineering: Financial Analyst</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {
            font-family: Arial, sans-serif;
            padding: 20px;
            max-width: 1200px;
            margin: 0 auto;
        }
        .container {
            width: 100%;
        }
        h1, h2, h3 {
            color: #333;
        }
        .section {
            margin-bottom: 30px;
            padding: 15px;
            border-radius: 5px;
        }
        .tools-section {
            background-color: #e6ffe6;
            border: 1px solid #99cc99;
        }
        .chart-section {
            background-color: #f0f8ff;
            border: 1px solid #b8daff;
        }
        .summary-section {
            background-color: #fff9e6;
            border: 1px solid #ffe0b2;
        }
        .transactions-section {
            background-color: #f9f9f9;
            border: 1px solid #ddd;
        }
        .filter-group {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            gap: 15px;
            margin-bottom: 15px;
        }
        .filter-group label {
            font-weight: bold;
            margin-right: 5px;
        }
        .filter-group select, .filter-group input[type="date"] {
            padding: 8px;
            border-radius: 4px;
            border: 1px solid #ddd;
        }
        .filter-group button {
            padding: 8px 15px;
            background-color: #28a745;
            color: white;
            border: none;
            border-radius: 4px;
            cursor: pointer;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 15px;
        }
        th, td {
            padding: 10px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        th a {
            color: inherit;
            text-decoration: none;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .summary-card {
            background-color: #fff;
            border: 1px solid #ddd;
            border-radius: 5px;
            padding: 15px;
            margin-bottom: 15px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .summary-row {
            display: flex;
            justify-content: space-between;
            margin-bottom: 10px;
        }
        .summary-label {
            font-weight: bold;
        }
        .negative {
            color: #d9534f;
        }
        .positive {
            color: #5cb85c;
        }
        .nav-links {
            margin-bottom: 20px;
        }
        .nav-links a {
            margin-right: 15px;
            text-decoration: none;
            color: #007bff;
        }
        .chart-container {
            width: 95%;
            height: 300px;
            margin: 0 auto;
        }
        .build-info {
            position: absolute;
            top: 10px;
            right: 20px;
            padding: 5px 10px;
            background-color: #f8f9fa;
            border-radius: 4px;
            font-size: 12px;
            color: #6c757d;
            border: 1px solid #dee2e6;
        }
    </style>
</head>
<body>
    <div class="build-info">Build: {{ build_number }}</div>
    <div class="container">
        <h1>Gotham Engineering: Financial Analyst</h1>
        
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/data_import_tagging">Data Import and Tagging</a>
            <a href="/tag_summary">Tag Summary</a>
            <a href="/monthly_summary">Monthly Summary</a>
        </div>
        
        <!-- Section 1: Tools -->
        <div class="section tools-section">
            <h2>Analysis Tools</h2>
            <form method="GET" action="/historical_analysis">
                <input type="hidden" name="sort" value="{{ sort }}">
                <input type="hidden" name="dir" value="{{ sort_dir }}">
                
                <div class="filter-group">
                    <label for="year">Year:</label>
                    <select name="year" id="year">
                        <option value="all" {% if year == 'all' %}selected{% endif %}>All Years</option>
                        {% for y in available_years %}
                        <option value="{{ y }}" {% if year|string == y|string %}selected{% endif %}>{{ y }}</option>
                        {% endfor %}
                    </select>
                    
                    <label for="month">Month:</label>
                    <select name="month" id="month">
                        <option value="all" {% if month == 'all' %}selected{% endif %}>All Months</option>
                        <option value="1" {% if month|string == '1' %}selected{% endif %}>January</option>
                        <option value="2" {% if month|string == '2' %}selected{% endif %}>February</option>
                        <option value="3" {% if month|string == '3' %}selected{% endif %}>March</option>
                        <option value="4" {% if month|string == '4' %}selected{% endif %}>April</option>
                        <option value="5" {% if month|string == '5' %}selected{% endif %}>May</option>
                        <option value="6" {% if month|string == '6' %}selected{% endif %}>June</option>
                        <option value="7" {% if month|string == '7' %}selected{% endif %}>July</option>
                        <option value="8" {% if month|string == '8' %}selected{% endif %}>August</option>
                        <option value="9" {% if month|string == '9' %}selected{% endif %}>September</option>
                        <option value="10" {% if month|string == '10' %}selected{% endif %}>October</option>
                        <option value="11" {% if month|string == '11' %}selected{% endif %}>November</option>
                        <option value="12" {% if month|string == '12' %}selected{% endif %}>December</option>
                    </select>
                    
                    <label for="tag">Tag:</label>
                    <select name="tag" id="tag">
                        <option value="all" {% if tag == 'all' %}selected{% endif %}>All Tags</option>
                        {% for t in available_tags %}
                        <option value="{{ t }}" {% if tag == t %}selected{% endif %}>{{ t }}</option>
                        {% endfor %}
                    </select>
                </div>
                
                <div class="filter-group">
                    <label for="start_date">Start Date:</label>
                    <input type="date" id="start_date" name="start_date" value="{{ start_date }}">
                    
                    <label for="end_date">End Date:</label>
                    <input type="date" id="end_date" name="end_date" value="{{ end_date }}">
                    
                    <button type="submit">Apply Filters</button>
                    <button type="button" onclick="clearFilters()">Clear Filters</button>
                    <button type="button" onclick="window.location.reload()">Refresh</button>
                </div>
            </form>
        </div>
        
        <!-- Section 2: Chart -->
        <div class="section chart-section">
            <h2>Financial Trends</h2>
            <div class="chart-container">
                <canvas id="financialChart"></canvas>
            </div>
        </div>
        
        <!-- Section 3: Summary Stats -->
        <div class="section summary-section">
            <h2>Transaction Summary</h2>
            <div class="summary-card">
                <div class="summary-row">
                    <span class="summary-label">Total Transactions:</span>
                    <span>{{ summary_stats.transaction_count }}</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Total Credits:</span>
                    <span class="positive">{{ summary_stats.total_credits }}</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Total Debits:</span>
                    <span class="negative">{{ summary_stats.total_debits }}</span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Net Income:</span>
                    <span class="{% if '-' in summary_stats.net_income %}negative{% else %}positive{% endif %}">
                        {{ summary_stats.net_income }}
                    </span>
                </div>
                <div class="summary-row">
                    <span class="summary-label">Net Savings:</span>
                    <span class="{% if '-' in summary_stats.net_income %}negative{% else %}positive{% endif %}">
                        {{ summary_stats.net_savings_pct }}
                    </span>
                </div>
            </div>
        </div>
        
        <!-- Section 4: Transactions Table -->
        <div class="section transactions-section">
            <h2>Transaction Details</h2>
            <table>
                <thead>
                    <tr>
                        <th>
                            <a href="/historical_analysis?sort=date&dir={% if sort == 'date' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}&tag={{ tag }}&start_date={{ start_date }}&end_date={{ end_date }}">
                                Date {% if sort == 'date' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}
                            </a>
                        </th>
                        <th>
                            <a href="/historical_analysis?sort=description&dir={% if sort == 'description' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}&tag={{ tag }}&start_date={{ start_date }}&end_date={{ end_date }}">
                                Description {% if sort == 'description' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}
                            </a>
                        </th>
                        <th>
                            <a href="/historical_analysis?sort=amount&dir={% if sort == 'amount' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}&tag={{ tag }}&start_date={{ start_date }}&end_date={{ end_date }}">
                                Amount {% if sort == 'amount' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}
                            </a>
                        </th>
                        <th>
                            <a href="/historical_analysis?sort=tag&dir={% if sort == 'tag' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}&tag={{ tag }}&start_date={{ start_date }}&end_date={{ end_date }}">
                                Tag {% if sort == 'tag' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}
                            </a>
                        </th>
                    </tr>
                </thead>
                <tbody>
                    {% for transaction in transactions %}
                    <tr>
                        <td>{{ transaction.date }}</td>
                        <td>{{ transaction.description }}</td>
                        <td {% if '-' in transaction.amount %}class="negative"{% else %}class="positive"{% endif %}>
                            {{ transaction.amount }}
                        </td>
                        <td>{{ transaction.tag }}</td>
                    </tr>
                    {% endfor %}
                    {% if transactions|length == 0 %}
                    <tr>
                        <td colspan="4" style="text-align: center;">No transactions found for the selected filters.</td>
                    </tr>
                    {% endif %}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        // Initialize chart when DOM is ready
        document.addEventListener('DOMContentLoaded', function() {
            // Chart data from backend
            const chartData = {{ chart_data|tojson }};
            
            if (chartData.labels.length > 0) {
                const ctx = document.getElementById('financialChart').getContext('2d');
                
                new Chart(ctx, {
                    type: 'line',
                    data: {
                        labels: chartData.labels,
                        datasets: [
                            {
                                label: 'X-Axis',
                                data: Array(chartData.labels.length).fill(0),
                                borderColor: 'black',
                                borderWidth: 1,
                                fill: false,
                                pointRadius: 0,
                                borderDash: [5, 5]
                            },
                            {
                                label: 'Debits',
                                data: chartData.debits,
                                borderColor: 'orange',
                                backgroundColor: 'rgba(255, 165, 0, 0.2)',
                                borderWidth: 2,
                                fill: 'origin'
                            },
                            {
                                label: 'Credits',
                                data: chartData.credits,
                                borderColor: 'blue',
                                backgroundColor: 'rgba(0, 0, 255, 0.2)',
                                borderWidth: 2,
                                fill: 'origin'
                            },
                            {
                                label: 'Income',
                                data: chartData.income,
                                borderColor: 'green',
                                backgroundColor: 'rgba(0, 128, 0, 0.2)',
                                borderWidth: 2,
                                fill: 'origin'
                            }
                        ]
                    },
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Time Period'
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Amount ($)'
                                },
                                beginAtZero: false
                            }
                        },
                        plugins: {
                            title: {
                                display: true,
                                text: 'Financial History'
                            },
                            tooltip: {
                                callbacks: {
                                    label: function(context) {
                                        let label = context.dataset.label || '';
                                        if (label) {
                                            label += ': ';
                                        }
                                        if (context.parsed.y !== null) {
                                            label += new Intl.NumberFormat('en-US', {
                                                style: 'currency',
                                                currency: 'USD'
                                            }).format(context.parsed.y);
                                        }
                                        return label;
                                    }
                                }
                            }
                        }
                    }
                });
            } else {
                document.getElementById('financialChart').innerHTML = 'No data available for the selected period.';
            }
        });
        
        function clearFilters() {
            window.location.href = '/historical_analysis';
        }
    </script>
</body>
</html>
"""

@app.route('/')
def home():
    return historical_analysis()

if __name__ == '__main__':
    # Initialize database tables
    initialize_database()
    
    print("Starting web service on port 5001...")
    print("Open your browser to: http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=True) 