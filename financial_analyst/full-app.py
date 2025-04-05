from flask import Flask, render_template_string, request, redirect, url_for, render_template
import psycopg2
import psycopg2.extras
import os
import time
from urllib.parse import urlparse, parse_qs
import sqlite3
from datetime import datetime

app = Flask(__name__)

# Database configuration
db_config = {
    "host": "localhost",
    "user": "postgres",
    "password": "postgres",
    "dbname": "financial_analyst",
    "port": "5432"
}

def get_build_number():
    """Get the current build number from environment variable"""
    try:
        return os.environ.get('BUILD_NUMBER', '1')
    except Exception:
        return "?"  # Return a placeholder if any error occurs

def get_db_connection():
    """Get a database connection with retry logic"""
    max_retries = 5
    retry_count = 0
    retry_delay = 1  # seconds
    
    while retry_count < max_retries:
        try:
            conn = psycopg2.connect(**db_config)
            conn.autocommit = True
            return conn
        except psycopg2.OperationalError as e:
            retry_count += 1
            print(f"Database connection attempt {retry_count} failed: {e}")
            
            if retry_count >= max_retries:
                break
                
            print(f"Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            retry_delay *= 2  # Exponential backoff
    
    raise Exception("Failed to connect to the database after multiple attempts")

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
    
    # Create budgets table for the new budget tracking feature
    cur.execute("""
        CREATE TABLE IF NOT EXISTS budgets (
            id SERIAL PRIMARY KEY,
            tag TEXT UNIQUE,
            monthly_amount NUMERIC(10,2),
            created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        .dataset-info {
            text-align: right;
            margin-top: 10px;
            font-weight: bold;
            font-style: italic;
            padding-right: 15px;
            color: #1e7e34;
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
            <a href="/monthly_summary"><button>Monthly Statements</button></a>
            <a href="/transaction_summary"><button>Transaction Summary</button></a>
            <a href="/budgets"><button>Budget Settings</button></a>
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
        
        {% if cleared and 'tags' in cleared %}
        <div class="alert" style="background-color: #d4edda; color: #155724; padding: 15px; margin-bottom: 15px; border-radius: 4px;">
            <strong>Success!</strong> Transaction tags table cleared.
            <p><small>All transaction tags have been removed. Current tag count: {{ tags_count }}</small></p>
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
    
    # Get the tags_count from URL parameter if provided (from clear_database redirect)
    tags_count_param = request.args.get('tags_count', None, type=int)
    
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
        
        # Get count of unique tags - use the parameter value if provided (after clear_database)
        if tags_count_param is not None:
            tags_count = tags_count_param
        else:
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
                
                # Keep track of old tag to new tag mappings for history updates
                tag_mappings = {}
                
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
                        
                        # Get current tag (if any) for this description
                        cur.execute("SELECT tag FROM tags WHERE description = %s", (description,))
                        result = cur.fetchone()
                        
                        if result and result[0] != tag:
                            # If the description already has a tag and it's different from the new one,
                            # record this mapping for updating the history table
                            tag_mappings[result[0]] = tag
                        
                        # Insert or update tag
                        cur.execute("""
                            INSERT INTO tags (description, tag)
                            VALUES (%s, %s)
                            ON CONFLICT (description) 
                            DO UPDATE SET tag = EXCLUDED.tag
                        """, (description, tag))
                        tags_imported += 1
                
                # Now update the records_history table based on our tag mappings
                for old_tag, new_tag in tag_mappings.items():
                    # If old_tag is None/NULL (untagged), we need a special WHERE clause
                    if old_tag is None:
                        cur.execute("""
                            UPDATE records_history
                            SET tag = %s
                            WHERE tag IS NULL
                        """, (new_tag,))
                    else:
                        cur.execute("""
                            UPDATE records_history
                            SET tag = %s
                            WHERE tag = %s
                        """, (new_tag, old_tag))
                
                # Also update records_history based on descriptions
                # This ensures all descriptions use their most current tag
                cur.execute("""
                    UPDATE records_history rh
                    SET tag = t.tag
                    FROM tags t
                    WHERE rh.description = t.description
                """)
                
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
        
        # Get updated counts after clearing
        tag_count = 0
        if 'tags' in tables_to_clear:
            cur.execute("SELECT COUNT(*) FROM tags")
            tag_count = cur.fetchone()[0]
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Include the tag_count in the redirect parameters
        if 'tags' in tables_to_clear:
            return redirect(url_for('index', cleared=','.join(tables_to_clear), tags_count=tag_count))
        else:
            return redirect(url_for('index', cleared=','.join(tables_to_clear)))
        
    except Exception as e:
        return f"Error clearing tables: {str(e)}"

@app.route('/monthly_summary')
def monthly_summary():
    """Show Monthly Statements with transactions by month"""
    
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

@app.route('/transaction_summary')
def transaction_summary_view():
    """
    View function for the tag summary page.
    """
    try:
        # Get query parameters
        sort = request.args.get('sort', 'amount')
        sort_dir = request.args.get('dir', 'desc')
        tag_filter = request.args.get('tag', 'all')
        
        # Get optional year and month filters
        year = request.args.get('year', 'all')
        month = request.args.get('month', 'all')
        
        # Connect to the database
        conn = get_db_connection()
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # First, check the database structure to handle potential column differences
        try:
            cursor.execute("""
                SELECT column_name FROM information_schema.columns 
                WHERE table_name = 'records_history'
            """)
            columns = [row['column_name'] for row in cursor.fetchall()]
            print(f"Found columns in records_history: {columns}")
            
            # Determine date column name (could be 'date' or 'entry_date')
            date_column = 'date'
            if 'entry_date' in columns:
                date_column = 'entry_date'
            
            # Check if we have any records
            cursor.execute(f"SELECT COUNT(*) FROM records_history")
            record_count = cursor.fetchone()[0]
            if record_count == 0:
                return render_template_string(
                    TRANSACTION_SUMMARY_TEMPLATE,
                    tags=[],
                    total_amount=0,
                    monthly_income=0,
                    monthly_spending=0,
                    history_count=0,
                    months_count=0,
                    year='all',
                    month='all',
                    tag='all',
                    available_years=[],
                    available_tags=[],
                    sort=sort,
                    sort_dir=sort_dir,
                    build_number=get_build_number(),
                    chart_data={'labels': [], 'datasets': []}
                )
                
            # Get available years for dropdown
            cursor.execute(f"SELECT DISTINCT EXTRACT(YEAR FROM {date_column}::date) AS year FROM records_history ORDER BY year")
            available_years = [int(row['year']) for row in cursor.fetchall()]
            
            # Get available tags for dropdown
            cursor.execute("SELECT DISTINCT tag FROM records_history WHERE tag IS NOT NULL AND tag != '' ORDER BY tag")
            available_tags = [row['tag'] for row in cursor.fetchall()]
            
            # Base query for calculating monthly income and spending
            base_query = f"""
            SELECT 
                EXTRACT(YEAR FROM {date_column}::date) AS year,
                EXTRACT(MONTH FROM {date_column}::date) AS month,
                SUM(CASE WHEN amount::numeric > 0 THEN amount::numeric ELSE 0 END) AS income,
                SUM(CASE WHEN amount::numeric < 0 THEN ABS(amount::numeric) ELSE 0 END) AS spending
            FROM records_history
            WHERE 1=1
        """
        
            # Apply filters for the base query
            query_params = []
            if year != 'all':
                base_query += f" AND EXTRACT(YEAR FROM {date_column}::date) = %s"
                query_params.append(int(year))
            
            if month != 'all':
                base_query += f" AND EXTRACT(MONTH FROM {date_column}::date) = %s"
                query_params.append(int(month))
                
            if tag_filter != 'all':
                base_query += " AND tag = %s"
                query_params.append(tag_filter)
                
            base_query += " GROUP BY year, month ORDER BY year, month"
            
            # Execute query
            cursor.execute(base_query, query_params)
            monthly_data = cursor.fetchall()
            
            # Calculate monthly income and spending
            total_income = sum(row['income'] for row in monthly_data) if monthly_data else 0
            total_spending = sum(row['spending'] for row in monthly_data) if monthly_data else 0
            months_count = len(monthly_data) if monthly_data else 1
            
            monthly_income = total_income / months_count if months_count > 0 else 0
            monthly_spending = total_spending / months_count if months_count > 0 else 0
            
            # Build the query for tag data
            query = f"""
            SELECT 
                tag,
                SUM(amount::numeric) AS amount,
                COUNT(*)::integer AS num_transactions,
                SUM(amount::numeric) / %s AS monthly_avg
            FROM records_history
            WHERE tag IS NOT NULL AND tag != ''
            """
            
            # Apply the same filters as above
            params = [months_count]
            if year != 'all':
                query += f" AND EXTRACT(YEAR FROM {date_column}::date) = %s"
                params.append(int(year))
            
            if month != 'all':
                query += f" AND EXTRACT(MONTH FROM {date_column}::date) = %s"
                params.append(int(month))
            
            if tag_filter != 'all':
                query += " AND tag = %s"
                params.append(tag_filter)
                
            query += " GROUP BY tag"
            
            # Add sorting
            if sort == 'tag':
                query += " ORDER BY tag " + ('ASC' if sort_dir == 'asc' else 'DESC')
            elif sort == 'amount':
                query += " ORDER BY amount " + ('ASC' if sort_dir == 'asc' else 'DESC')
            elif sort == 'count':
                query += " ORDER BY num_transactions " + ('ASC' if sort_dir == 'asc' else 'DESC')
            elif sort == 'monthly_avg':
                query += " ORDER BY monthly_avg " + ('ASC' if sort_dir == 'asc' else 'DESC')
                
            # Execute query
            cursor.execute(query, params)
            tags_raw = cursor.fetchall()
            
            # Convert DictRow objects to plain dictionaries
            tags = []
            print("DEBUG: Converting DictRow objects to plain dictionaries")
            for tag_item in tags_raw:
                # Print the original tag_item
                print(f"DEBUG: Original tag_item = {tag_item}, type = {type(tag_item)}")
                
                # Create a brand new dictionary with only the fields we need
                tag_dict = {
                    'tag': tag_item['tag'],
                    'amount': float(tag_item['amount']) if tag_item['amount'] is not None else 0,
                    'num_transactions': int(tag_item['num_transactions']),
                    'monthly_avg': float(tag_item['monthly_avg']) if tag_item['monthly_avg'] is not None else 0
                }
                
                # Print the new dictionary
                print(f"DEBUG: Created tag_dict = {tag_dict}, type = {type(tag_dict)}")
                
                tags.append(tag_dict)
            
            # Print the final tags list
            print(f"DEBUG: Final tags list length = {len(tags)}")
            if tags:
                print(f"DEBUG: First tag in list = {tags[0]}, type = {type(tags[0])}")
            
            # Query for total number of transactions in history
            cursor.execute("SELECT COUNT(*) FROM records_history")
            history_count = cursor.fetchone()[0]
            
            # Calculate total amount
            total_amount = sum(tag['amount'] for tag in tags) if tags else 0
            
            # Query for chart data - monthly spending by tag over time
            chart_query = f"""
            SELECT 
                to_char({date_column}::date, 'YYYY-MM') as month_year,
                tag,
                SUM(amount::numeric) as amount
            FROM records_history
            WHERE tag IS NOT NULL AND tag != '' AND amount::numeric < 0
            """
            
            # Apply filters for the chart query
            chart_params = []
            if year != 'all':
                chart_query += f" AND EXTRACT(YEAR FROM {date_column}::date) = %s"
                chart_params.append(int(year))
                
            if tag_filter != 'all':
                chart_query += " AND tag = %s"
                chart_params.append(tag_filter)
                
            # Group and order by month and tag
            chart_query += " GROUP BY month_year, tag ORDER BY month_year, tag"
            
            # Execute chart query
            cursor.execute(chart_query, chart_params)
            chart_data_raw_rows = cursor.fetchall()
            
            # Convert DictRow objects to plain dictionaries for chart data
            chart_data_raw = []
            for row in chart_data_raw_rows:
                chart_data_raw.append({
                    'month_year': row['month_year'],
                    'tag': row['tag'],
                    'amount': float(row['amount']) if row['amount'] is not None else 0
                })
            
            # Process chart data for Chart.js
            months = []
            tags_data = {}
            
            for row in chart_data_raw:
                month_year = row['month_year']
                tag = row['tag']
                amount = abs(float(row['amount']))  # Convert to positive for display
                
                if month_year not in months:
                    months.append(month_year)
                    
                if tag not in tags_data:
                    tags_data[tag] = {}
                    
                tags_data[tag][month_year] = amount
            
            # Sort months chronologically
            months.sort()
            
            # Prepare datasets for Chart.js
            datasets = []
            colors = [
                'rgba(255, 99, 132, 0.7)',   # Red
                'rgba(54, 162, 235, 0.7)',   # Blue
                'rgba(255, 206, 86, 0.7)',   # Yellow
                'rgba(75, 192, 192, 0.7)',   # Green
                'rgba(153, 102, 255, 0.7)',  # Purple
                'rgba(255, 159, 64, 0.7)',   # Orange
                'rgba(199, 199, 199, 0.7)',  # Gray
                'rgba(83, 102, 255, 0.7)',   # Indigo
                'rgba(255, 99, 255, 0.7)',   # Pink
                'rgba(24, 132, 132, 0.7)',   # Teal
            ]
            
            color_index = 0
            for tag in tags_data:
                data = []
                for month in months:
                    data.append(tags_data[tag].get(month, 0))
                    
                color = colors[color_index % len(colors)]
                border_color = color.replace('0.7', '1.0')
                
                datasets.append({
                    'label': tag,
                    'data': data,
                    'backgroundColor': color,
                    'borderColor': border_color,
                    'borderWidth': 1,
                    'fill': False
                })
                
                color_index += 1
            
            # Final chart data structure for Chart.js
            chart_data = {
                'labels': months,
                'datasets': datasets
            }
            
            # Close database connection
            cursor.close()
            conn.close()
            
            # Render template with data
            return render_template_string(
                TRANSACTION_SUMMARY_TEMPLATE,
                tags=tags,
                total_amount=total_amount,
                monthly_income=monthly_income,
                monthly_spending=monthly_spending,
                history_count=history_count,
                months_count=months_count,
                year=year,
                month=month,
                tag=tag_filter,
                available_years=available_years,
                available_tags=available_tags,
                sort=sort,
                sort_dir=sort_dir,
                build_number=get_build_number(),
                chart_data=chart_data
            )
            
        except Exception as db_error:
            return f"Database error in transaction_summary_view: {str(db_error)}"
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        return f"Error in transaction_summary_view: {str(e)}<br><pre>{error_details}</pre>"

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
    <title>Monthly Statements</title>
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
        <h1>Monthly Statements</h1>
        
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/data_import_tagging">Data Import and Tagging</a>
            <a href="/transaction_summary">Transaction Summary</a>
            <a href="/monthly_summary">Monthly Statements</a>
            <a href="/budgets">Budget Settings</a>
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
TRANSACTION_SUMMARY_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Transaction Summary</title>
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
        .tag-container {
            margin-top: 20px;
        }
        .total-section {
            margin-bottom: 20px;
            padding: 15px;
            background-color: #f2f2f2;
            border-radius: 5px;
            display: flex;
            justify-content: space-between;
        }
        .total-left {
            flex: 1;
        }
        .total-right {
            flex: 1;
            text-align: right;
        }
        .total-value {
            font-size: 1.1em;
            font-weight: bold;
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
        }
        .filter-row {
            display: flex;
            align-items: center;
            flex-wrap: wrap;
            margin-bottom: 10px;
            justify-content: space-between;
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
        .checkbox-col {
            width: 30px;
            text-align: center;
        }
        .toggle-all {
            margin-left: 5px;
            cursor: pointer;
            color: #007bff;
            font-size: 0.9em;
        }
        .toggle-all:hover {
            text-decoration: underline;
        }
        .chart-section {
            background-color: #f0f8ff;
            border: 1px solid #b8daff;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .chart-container {
            width: 100%;
            height: 300px;
            margin: 0 auto;
        }
        .filter-controls {
            display: flex;
            align-items: center;
        }
        .filter-dropdowns {
            display: flex;
            align-items: center;
            flex-grow: 1;
        }
    </style>
</head>
<body>
    <div class="build-info">Build: {{ build_number }}</div>
    <div class="container">
        <h1>Transaction Summary</h1>
        
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/data_import_tagging">Data Import and Tagging</a>
            <a href="/transaction_summary">Transaction Summary</a>
            <a href="/monthly_summary">Monthly Statements</a>
            <a href="/budgets">Budget Settings</a>
        </div>
        
        <div class="filter-section">
            <h2>Filters</h2>
            <form method="GET" action="/transaction_summary">
                <input type="hidden" name="sort" value="{{ sort }}">
                <input type="hidden" name="dir" value="{{ sort_dir }}">
                
                <div class="filter-row">
                    <div class="filter-dropdowns">
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
                    
                    <div class="filter-controls">
                        <button type="submit">Apply Filters</button>
                        <button type="button" onclick="window.location.href='/transaction_summary'" style="margin-left: 10px; background-color: #6c757d;">Clear Filters</button>
                    </div>
                </div>
            </form>
        </div>
        
        <!-- New Chart Section -->
        <div class="chart-section">
            <h2>Monthly Spending by Tag</h2>
            <div class="chart-container">
                <canvas id="spendingChart"></canvas>
            </div>
        </div>
        
        <div class="total-section">
            <div class="total-left">
                <h3>Total: <span {% if total_amount < 0 %}class="negative"{% else %}class="positive"{% endif %}>
                    ${{ '{:,.2f}'.format(total_amount|abs) }}
                </span></h3>
                <p>Total transactions in history: <strong>{{ history_count }}</strong></p>
                <p>Months in selection: <strong>{{ months_count }}</strong></p>
                
                {% if year != 'all' or month != 'all' or tag != 'all' %}
                <p>
                    Filtering: 
                    {% if month != 'all' %}
                        {% set month_names = {1: 'January', 2: 'February', 3: 'March', 4: 'April', 5: 'May', 6: 'June', 7: 'July', 8: 'August', 9: 'September', 10: 'October', 11: 'November', 12: 'December'} %}
                        {{ month_names[month|int] }} 
                    {% endif %}
                    {% if year != 'all' %}
                        {{ year }}
                    {% endif %}
                    {% if tag != 'all' %}
                        - Tag: {{ tag }}
                    {% endif %}
                    <a href="/transaction_summary" style="font-size: 0.8em; margin-left: 10px;">[Clear Filters]</a>
                </p>
                {% endif %}
            </div>
            <div class="total-right">
                <p>Monthly Income: <span class="positive">${{ '{:,.2f}'.format(monthly_income) }}</span></p>
                <p>Monthly Spending: <span class="negative">${{ '{:,.2f}'.format(monthly_spending) }}</span></p>
                <p>Monthly Net: <span class="{% if (monthly_income - monthly_spending) < 0 %}negative{% else %}positive{% endif %}">
                    ${{ '{:,.2f}'.format((monthly_income - monthly_spending)|abs) }}
                    {% if (monthly_income - monthly_spending) < 0 %}deficit{% else %}surplus{% endif %}
                </span></p>
                {% if monthly_income > 0 %}
                <p>Savings Rate: <span class="{% if (monthly_income - monthly_spending) / monthly_income < 0 %}negative{% else %}positive{% endif %}">
                    {{ '{:.1f}%'.format(((monthly_income - monthly_spending) / monthly_income * 100) if monthly_income > 0 else 0) }}
                </span></p>
                {% endif %}
            </div>
        </div>
        
        <div class="tag-container">
            <h2>Spending by Category</h2>
            <table>
                <thead>
                    <tr>
                        <th class="checkbox-col">
                            <input type="checkbox" id="toggle-all-tags" checked>
                            <span class="toggle-all" onclick="toggleAllTags()">All</span>
                        </th>
                        <th><a href="/transaction_summary?sort=tag&dir={% if sort == 'tag' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}&tag={{ tag }}">Tag {% if sort == 'tag' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                        <th><a href="/transaction_summary?sort=amount&dir={% if sort == 'amount' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}&tag={{ tag }}">Amount {% if sort == 'amount' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                        <th><a href="/transaction_summary?sort=count&dir={% if sort == 'count' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}&tag={{ tag }}">Transactions {% if sort == 'count' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                        <th><a href="/transaction_summary?sort=monthly_avg&dir={% if sort == 'monthly_avg' and sort_dir == 'asc' %}desc{% else %}asc{% endif %}&year={{ year }}&month={{ month }}&tag={{ tag }}">Monthly Average {% if sort == 'monthly_avg' %}{% if sort_dir == 'asc' %}▲{% else %}▼{% endif %}{% endif %}</a></th>
                    </tr>
                </thead>
                <tbody>
                    {% for tag_item in tags %}
                    <tr>
                        <td class="checkbox-col">
                            <input type="checkbox" class="tag-toggle" data-tag="{{ tag_item['tag'] }}" checked>
                        </td>
                        <td>{{ tag_item['tag'] }}</td>
                        <td {% if tag_item['amount'] < 0 %}class="negative"{% else %}class="positive"{% endif %}>
                            ${{ '{:,.2f}'.format(tag_item['amount']|abs) }}
                        </td>
                        <td>
                            {{ tag_item['num_transactions'] }}
                        </td>
                        <td {% if tag_item['monthly_avg'] < 0 %}class="negative"{% else %}class="positive"{% endif %}>
                            ${{ '{:,.2f}'.format(tag_item['monthly_avg']|abs) }}/month
                        </td>
                    </tr>
                    {% endfor %}
                    {% if tags|length == 0 %}
                    <tr>
                        <td colspan="5" style="text-align: center;">No data found for the selected filters.</td>
                    </tr>
                    {% endif %}
                </tbody>
            </table>
        </div>
    </div>
    
    <script>
        // Initialize the chart with the data
        document.addEventListener('DOMContentLoaded', function() {
            const ctx = document.getElementById('spendingChart').getContext('2d');
            const chartData = {{ chart_data|tojson }};
            
            const chart = new Chart(ctx, {
                type: 'line',
                data: chartData,
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: {
                            position: 'top',
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
                    },
                    scales: {
                        y: {
                            ticks: {
                                callback: function(value) {
                                    return '$' + value.toFixed(2);
                                }
                            },
                            title: {
                                display: true,
                                text: 'Spending Amount ($)'
                            }
                        },
                        x: {
                            title: {
                                display: true,
                                text: 'Month'
                            }
                        }
                    }
                }
            });
            
            // Handle tag checkboxes to show/hide datasets
            const checkboxes = document.querySelectorAll('.tag-toggle');
            checkboxes.forEach(checkbox => {
                checkbox.addEventListener('change', function() {
                    const tagName = this.getAttribute('data-tag');
                    
                    // Find the dataset with this tag name
                    const datasetIndex = chartData.datasets.findIndex(ds => ds.label === tagName);
                    if (datasetIndex >= 0) {
                        // Toggle visibility
                        const isHidden = chart.isDatasetHidden(datasetIndex);
                        chart.setDatasetVisibility(datasetIndex, isHidden);
                        chart.update();
                    }
                });
            });
            
            // Toggle all tags
            document.getElementById('toggle-all-tags').addEventListener('change', function() {
                const checked = this.checked;
                
                // Update all checkboxes
            checkboxes.forEach(checkbox => {
                    checkbox.checked = checked;
                });
                
                // Update chart visibility
                for (let i = 0; i < chartData.datasets.length; i++) {
                    chart.setDatasetVisibility(i, checked);
                }
                
                chart.update();
            });
        });
        
        // Helper function to toggle all tag checkboxes
        function toggleAllTags() {
            const toggleAllCheckbox = document.getElementById('toggle-all-tags');
            toggleAllCheckbox.checked = !toggleAllCheckbox.checked;
            toggleAllCheckbox.dispatchEvent(new Event('change'));
        }
    </script>
</body>
</html>
"""

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
        .dataset-info {
            text-align: right;
            margin-top: 10px;
            font-weight: bold;
            font-style: italic;
            padding-right: 15px;
            color: #1e7e34;
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
            <a href="/transaction_summary">Transaction Summary</a>
            <a href="/monthly_summary">Monthly Statements</a>
            <a href="/budgets">Budget Settings</a>
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
            
            <!-- Dataset Date Range Info -->
            <div class="dataset-info">Dataset: {{ earliest_date }} - {{ latest_date }}</div>
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
                    data: chartData,
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        scales: {
                            x: {
                                title: {
                                    display: true,
                                    text: 'Time Period'
                                },
                                grid: {
                                    color: function(context) {
                                        // Use the firstOfMonthFlags array to determine if it's the first of the month
                                        if (context.tick && context.tick.value !== undefined && 
                                            chartData.firstOfMonthFlags[context.tick.value]) {
                                            return 'rgba(0, 0, 0, 0.3)'; // Dark grey for 1st of month
                                        }
                                        return 'rgba(0, 0, 0, 0.1)'; // Light grey for other days
                                    }
                                }
                            },
                            y: {
                                title: {
                                    display: true,
                                    text: 'Amount ($)'
                                },
                                beginAtZero: false,
                                grid: {
                                    color: 'rgba(0, 0, 0, 0.1)' // Light grey
                                }
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
        
        # Get dataset date range (earliest and latest dates in the database)
        cur.execute("""
            SELECT 
                MIN(date::date) as earliest_date,
                MAX(date::date) as latest_date
            FROM records_history
            WHERE date IS NOT NULL
        """)
        date_range = cur.fetchone()
        earliest_date = date_range[0] if date_range and date_range[0] else None
        latest_date = date_range[1] if date_range and date_range[1] else None
        
        # Format dates for display
        earliest_date_str = ""
        latest_date_str = ""
        if earliest_date:
            if hasattr(earliest_date, 'strftime'):
                earliest_date_str = earliest_date.strftime('%B %d, %Y')
            else:
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(str(earliest_date), '%Y-%m-%d')
                    earliest_date_str = date_obj.strftime('%B %d, %Y')
                except:
                    earliest_date_str = str(earliest_date)
        
        if latest_date:
            if hasattr(latest_date, 'strftime'):
                latest_date_str = latest_date.strftime('%B %d, %Y')
            else:
                try:
                    from datetime import datetime
                    date_obj = datetime.strptime(str(latest_date), '%Y-%m-%d')
                    latest_date_str = date_obj.strftime('%B %d, %Y')
                except:
                    latest_date_str = str(latest_date)
        
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
                                     build_number=build_number,
                                     earliest_date=earliest_date_str,
                                     latest_date=latest_date_str)
    
    except Exception as e:
        return f"Error generating historical analysis: {str(e)}"

def get_chart_data(conn, where_clause, params, year, month):
    """Get data for financial charts"""
    cur = conn.cursor()
    
    # Group by day for narrower date ranges
    if year != 'all' and month != 'all':
        chart_query = f"""
            SELECT 
                date::date as period_date,
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
    date_flags = []
    
    running_income = 0
    
    for row in results:
        period_date, debit_sum, credit_sum = row
        period_date_str = period_date.strftime('%Y-%m-%d')
        
        # Store period label (date)
        dates.append(period_date_str)
        
        # Mark if date is first of month
        is_first_of_month = period_date.day == 1
        date_flags.append(is_first_of_month)
        
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
        'firstOfMonthFlags': date_flags,
        'datasets': [
            {
                'label': 'Debits',
                'data': debits,
                'backgroundColor': 'rgba(255, 99, 132, 0.2)',
                'borderColor': 'rgba(255, 99, 132, 1)',
                'borderWidth': 1,
                'fill': False
            },
            {
                'label': 'Credits',
                'data': credits,
                'backgroundColor': 'rgba(75, 192, 192, 0.2)',
                'borderColor': 'rgba(75, 192, 192, 1)',
                'borderWidth': 1,
                'fill': False
            },
            {
                'label': 'Net Income',
                'data': income,
                'backgroundColor': 'rgba(54, 162, 235, 0.2)',
                'borderColor': 'rgba(54, 162, 235, 1)',
                'borderWidth': 1,
                'fill': False
            }
        ]
    }
    
    cur.close()
    return chart_data

def get_summary_stats(conn, where_clause, params):
    """Get summary statistics for the selected period"""
    cur = conn.cursor()
    
    stats_query = f"""
        SELECT 
            COUNT(*)::integer as transaction_count,
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

# HTML template for budget settings
BUDGET_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Budget Settings</title>
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
        .budget-container {
            margin-top: 20px;
        }
        .budget-form {
            background-color: #f8f9fa;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            padding: 12px 8px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        .section-header {
            padding: 10px;
            margin-top: 30px;
            margin-bottom: 10px;
            font-weight: bold;
            font-size: 1.2em;
        }
        .budget-header {
            background-color: #90ee90; /* Light green */
        }
        .spending-header {
            background-color: #ffcc80; /* Light orange */
        }
        .positive {
            color: #28a745; /* Green */
        }
        .negative {
            color: #dc3545; /* Red */
        }
        .neutral {
            color: #000000; /* Black */
        }
        .budget-actions {
            display: flex;
            gap: 10px;
        }
        .edit-btn {
            background-color: #007bff;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
        }
        .delete-btn {
            background-color: #dc3545;
            color: white;
            border: none;
            padding: 5px 10px;
            border-radius: 3px;
            cursor: pointer;
        }
        .budget-form input, .budget-form select {
            padding: 8px;
            margin-right: 10px;
            border: 1px solid #ddd;
            border-radius: 3px;
        }
        .budget-form button {
            padding: 8px 15px;
            background-color: #28a745;
            color: white;
            border: none;
            border-radius: 3px;
            cursor: pointer;
        }
        .alert {
            padding: 15px;
            margin-bottom: 20px;
            border-radius: 5px;
        }
        .alert-success {
            background-color: #d4edda;
            color: #155724;
        }
        .alert-warning {
            background-color: #fff3cd;
            color: #856404;
        }
        .alert-danger {
            background-color: #f8d7da;
            color: #721c24;
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
        .sortable {
            cursor: pointer;
            position: relative;
            padding-right: 18px !important;
        }
        .sortable:hover {
            background-color: #e9ecef;
        }
        .sortable:after {
            content: '⇕';
            position: absolute;
            right: 5px;
            color: #999;
        }
        .sortable.asc:after {
            content: '↑';
            color: #333;
        }
        .sortable.desc:after {
            content: '↓';
            color: #333;
        }
        table.sortable-table {
            margin-bottom: 30px;
        }
    </style>
</head>
<body>
    <div class="build-info">Build: {{ build_number }}</div>
    <div class="container">
        <h1>Budget Settings</h1>
        
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/data_import_tagging">Data Import and Tagging</a>
            <a href="/transaction_summary">Transaction Summary</a>
            <a href="/monthly_summary">Monthly Statements</a>
            <a href="/budgets">Budget Settings</a>
        </div>
        
        {% if updated_tag %}
        <div class="alert alert-success">
            <strong>Success!</strong> Budget for "{{ updated_tag }}" has been updated.
        </div>
        {% endif %}
        
        {% if deleted_tag %}
        <div class="alert alert-danger">
            <strong>Success!</strong> Budget for "{{ deleted_tag }}" has been removed.
        </div>
        {% endif %}
        
        {% if auto_filled %}
        <div class="alert alert-success">
            <strong>Success!</strong> Empty budgets have been automatically filled with last year's averages.
        </div>
        {% endif %}
        
        {% if has_empty_budgets %}
        <div class="alert alert-warning">
            <strong>Notice:</strong> Some categories don't have budgets set. 
            <form method="POST" action="/budgets" style="display: inline;">
                <input type="hidden" name="action" value="auto_fill">
                <button type="submit" style="background-color: #ffc107; color: #212529; border: none; padding: 5px 10px; border-radius: 3px; cursor: pointer; margin-left: 10px;">
                    Auto-fill with {{ last_year }} averages
                </button>
            </form>
                </div>
        {% endif %}
        
        <div class="budget-form">
            <h3>Add or Update Budget</h3>
            <form method="POST" action="/budgets">
                <input type="hidden" name="action" value="update">
                
                <label for="tag">Category:</label>
                <select name="tag" id="tag" required>
                    <option value="">Select a category...</option>
                    {% for tag in available_tags %}
                    <option value="{{ tag }}">{{ tag }}</option>
                    {% endfor %}
                </select>
                
                <label for="monthly_amount">Monthly Budget:</label>
                <input type="text" name="monthly_amount" id="monthly_amount" placeholder="$0.00" required>
                
                <button type="submit">Save Budget</button>
            </form>
        </div>
        
        <!-- Green section - Current Budget -->
        <div class="section-header budget-header">Current Budget: {{ current_year }}</div>
        <table class="sortable-table" id="budget-table">
                <thead>
                    <tr>
                    <th class="sortable" data-sort="string">Category</th>
                    <th class="sortable" data-sort="number">Budget</th>
                    <th class="sortable" data-sort="number">Average {{ last_year }}</th>
                    <th class="sortable" data-sort="number">Average {{ current_year }}</th>
                    <th class="sortable" data-sort="number">Difference</th>
                    <th>Actions</th>
                    </tr>
                </thead>
                <tbody>
                {% for budget in budget_data %}
                <tr>
                    <td>{{ budget.tag }}</td>
                    <td data-value="{{ budget.monthly_budget }}">${{ "%.2f"|format(budget.monthly_budget) }}</td>
                    <td data-value="{{ budget.last_year_avg }}">${{ "%.2f"|format(budget.last_year_avg) }}</td>
                    <td data-value="{{ budget.current_year_avg }}">${{ "%.2f"|format(budget.current_year_avg) }}</td>
                    <td class="{% if budget.difference > 0 %}positive{% elif budget.difference < 0 %}negative{% else %}neutral{% endif %}" 
                        data-value="{{ budget.difference }}">
                        {% if budget.difference > 0 %}
                            ${{ "%.2f"|format(budget.difference) }}
                        {% elif budget.difference < 0 %}
                            -${{ "%.2f"|format(budget.difference|abs) }}
                        {% else %}
                            $0.00
                        {% endif %}
                        </td>
                    <td class="budget-actions">
                        <form method="POST" action="/budgets" onsubmit="return confirm('Are you sure you want to delete this budget?');">
                            <input type="hidden" name="action" value="delete">
                            <input type="hidden" name="tag" value="{{ budget.tag }}">
                            <button type="submit" class="delete-btn">Delete</button>
                        </form>
                    </td>
                    </tr>
                    {% endfor %}
            </tbody>
        </table>
        
        <!-- Orange section - Monthly Spending -->
        <div class="section-header spending-header">Spending: {{ current_year }}</div>
        <table class="sortable-table" id="spending-table">
            <thead>
                <tr>
                    <th class="sortable" data-sort="string">Category</th>
                    <th class="sortable" data-sort="number">January</th>
                    <th class="sortable" data-sort="number">February</th>
                    <th class="sortable" data-sort="number">March</th>
                    <th class="sortable" data-sort="number">April</th>
                    </tr>
            </thead>
            <tbody>
                {% for budget in budget_data %}
                <tr>
                    <td>{{ budget.tag }}</td>
                    <td data-value="{{ budget.monthly_data.get(1, 0) }}">${{ "%.2f"|format(budget.monthly_data.get(1, 0)) }}</td>
                    <td data-value="{{ budget.monthly_data.get(2, 0) }}">${{ "%.2f"|format(budget.monthly_data.get(2, 0)) }}</td>
                    <td data-value="{{ budget.monthly_data.get(3, 0) }}">${{ "%.2f"|format(budget.monthly_data.get(3, 0)) }}</td>
                    <td data-value="{{ budget.monthly_data.get(4, 0) }}">${{ "%.2f"|format(budget.monthly_data.get(4, 0)) }}</td>
                </tr>
                {% endfor %}
                </tbody>
            </table>
    </div>
    
    <script>
        function setTagInForm(tag) {
            document.getElementById('tag').value = tag;
            document.getElementById('monthly_amount').focus();
        }
        
        // Check if we need to show auto-fill prompt
        window.onload = function() {
            {% if has_empty_budgets and not auto_filled and not updated_tag and not deleted_tag %}
            if (confirm('Some categories don\\'t have budgets set. Would you like to automatically fill them with {{ last_year }} averages?')) {
                document.querySelector('form input[name="action"][value="auto_fill"]').parentNode.submit();
            }
            {% endif %}
            
            // Initialize table sorting
            initTableSorting();
        };
        
        // Function to handle table sorting
        function initTableSorting() {
            document.querySelectorAll('.sortable-table th.sortable').forEach(headerCell => {
                headerCell.addEventListener('click', () => {
                    const tableElement = headerCell.closest('table');
                    const headerIndex = Array.prototype.indexOf.call(headerCell.parentElement.children, headerCell);
                    const currentIsAscending = headerCell.classList.contains('asc');
                    
                    // Remove sort classes from all headers in this table
                    tableElement.querySelectorAll('th.sortable').forEach(th => {
                        th.classList.remove('asc', 'desc');
                    });
                    
                    // Set new sort class
                    headerCell.classList.add(currentIsAscending ? 'desc' : 'asc');
                    
                    // Get the type of sort (string or number)
                    const sortType = headerCell.getAttribute('data-sort');
                    
                    // Get all rows except the header
                    const tableBody = tableElement.querySelector('tbody');
                    const rowsArray = Array.from(tableBody.querySelectorAll('tr'));
                    
                    // Sort the array of rows
                    const sortedRows = rowsArray.sort((a, b) => {
                        const aValue = getCellValue(a, headerIndex, sortType);
                        const bValue = getCellValue(b, headerIndex, sortType);
                        
                        if (sortType === 'number') {
                            return currentIsAscending 
                                ? bValue - aValue 
                                : aValue - bValue;
            } else {
                            return currentIsAscending 
                                ? bValue.localeCompare(aValue) 
                                : aValue.localeCompare(bValue);
                        }
                    });
                    
                    // Remove all existing rows
                    while (tableBody.firstChild) {
                        tableBody.removeChild(tableBody.firstChild);
                    }
                    
                    // Re-add the newly sorted rows
                    tableBody.append(...sortedRows);
                });
            });
        }
        
        // Helper function to get cell value based on type
        function getCellValue(row, index, type) {
            const cell = row.querySelectorAll('td')[index];
            if (!cell) return '';
            
            // Check if the cell has a data-value attribute
            if (cell.hasAttribute('data-value')) {
                const dataValue = cell.getAttribute('data-value');
                return type === 'number' ? Number(dataValue) : dataValue;
            }
            
            // Fallback to text content
            const value = cell.textContent.trim();
            if (type === 'number') {
                // Handle currency format ($123.45 or -$123.45)
                return Number(value.replace(/[^-0-9.]/g, ''));
            }
            return value;
        }
    </script>
</body>
</html>
"""

def tables_exist():
    """Check if the required tables already exist"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    # Check if the main tables exist
    cur.execute("""
        SELECT EXISTS (
            SELECT FROM information_schema.tables 
            WHERE table_name = 'records_history'
        )
    """)
    tables_exist = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    return tables_exist

# Initialize database tables
if not tables_exist():
    print("Tables don't exist. Initializing database...")
    initialize_database()
else:
    print("Tables already exist. Skipping initialization.")

@app.route('/tag_summary')
def tag_summary_redirect():
    # Get all query parameters
    query_params = request.args.to_dict()
    
    # Build the redirect URL with the same query parameters
    redirect_url = url_for('transaction_summary_view', **query_params)
    
    return redirect(redirect_url)

@app.route('/budgets', methods=['GET', 'POST'])
def budget_settings():
    """Budget settings page to manage monthly spending allocations"""
    try:
        build_number = get_build_number()
        
        # Get current and last year
        current_year = 2024  # Hardcoded for demo
        last_year = current_year - 1
        
        # Handle POST requests (form submissions)
        if request.method == 'POST':
            action = request.form.get('action')
            
            if action == 'update':
                tag = request.form.get('tag')
                monthly_amount = request.form.get('monthly_amount', '0')
                
                # Clean the amount string (remove $ and commas)
                monthly_amount = monthly_amount.replace('$', '').replace(',', '')
                try:
                    monthly_amount = float(monthly_amount)
                except ValueError:
                    monthly_amount = 0
                
                conn = get_db_connection()
                cur = conn.cursor()
                
                # Check if budget already exists for this tag
                cur.execute("SELECT id FROM budgets WHERE tag = %s", (tag,))
                existing = cur.fetchone()
                
                if existing:
                    # Update existing budget
                    cur.execute("""
                        UPDATE budgets 
                        SET monthly_amount = %s, modified_date = CURRENT_TIMESTAMP 
                        WHERE tag = %s
                    """, (monthly_amount, tag))
                else:
                    # Insert new budget
                    cur.execute("""
                        INSERT INTO budgets (tag, monthly_amount)
                        VALUES (%s, %s)
                    """, (tag, monthly_amount))
                
                conn.commit()
                cur.close()
                conn.close()
                
                return redirect(url_for('budget_settings', updated=tag))
            
            elif action == 'delete':
                tag = request.form.get('tag')
                
                conn = get_db_connection()
                cur = conn.cursor()
                
                # Delete budget for this tag
                cur.execute("DELETE FROM budgets WHERE tag = %s", (tag,))
                
                conn.commit()
                cur.close()
                conn.close()
                
                return redirect(url_for('budget_settings', deleted=tag))
            
            elif action == 'auto_fill':
                conn = get_db_connection()
                cur = conn.cursor()
                
                # Auto-fill budgets with last year's averages for any tags that don't have budgets
                # First, get all unique tags
                cur.execute("""
                    SELECT DISTINCT tag 
                    FROM records_history 
                    WHERE tag IS NOT NULL AND tag != '' 
                    ORDER BY tag
                """)
                all_tags = [row[0] for row in cur.fetchall()]
                
                # For each tag, check if it has a budget
                for tag in all_tags:
                    cur.execute("SELECT monthly_amount FROM budgets WHERE tag = %s", (tag,))
                    existing_budget = cur.fetchone()
                    
                    # If no budget exists, set it to last year's average
                    if not existing_budget or existing_budget[0] == 0:
                        # Calculate last year's average for this tag
                        cur.execute("""
                            SELECT ABS(AVG(amount::numeric)) as avg_amount
                            FROM records_history
                            WHERE 
                                EXTRACT(YEAR FROM date::date) = %s AND
                                tag = %s
                        """, (last_year, tag))
                        
                        avg_amount = cur.fetchone()[0] or 0
                        
                        # Insert or update budget
                        if existing_budget:
                            cur.execute("""
                                UPDATE budgets 
                                SET monthly_amount = %s, modified_date = CURRENT_TIMESTAMP 
                                WHERE tag = %s
                            """, (avg_amount, tag))
                        else:
                            cur.execute("""
                                INSERT INTO budgets (tag, monthly_amount)
                                VALUES (%s, %s)
                            """, (tag, avg_amount))
                
                conn.commit()
                cur.close()
                conn.close()
                
                return redirect(url_for('budget_settings', auto_filled=True))
        
        # GET request - display the budget settings page
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all available tags
        cur.execute("""
            SELECT DISTINCT tag 
            FROM records_history 
            WHERE tag IS NOT NULL AND tag != '' 
            ORDER BY tag
        """)
        available_tags = [row[0] for row in cur.fetchall()]
        
        # Get all current budgets
        cur.execute("SELECT tag, monthly_amount FROM budgets")
        budgets = {row[0]: row[1] for row in cur.fetchall()}
        
        # Get last year's average monthly spending by tag
        cur.execute("""
            SELECT tag, ABS(AVG(amount::numeric)) as avg_amount
            FROM records_history
            WHERE 
                EXTRACT(YEAR FROM date::date) = %s AND
                tag IS NOT NULL AND tag != ''
            GROUP BY tag
            ORDER BY tag
        """, (last_year,))
        
        last_year_averages = {row[0]: row[1] for row in cur.fetchall()}
        
        # Get current year's average monthly spending by tag
        cur.execute("""
            SELECT tag, ABS(AVG(amount::numeric)) as avg_amount
            FROM records_history
            WHERE 
                EXTRACT(YEAR FROM date::date) = %s AND
                tag IS NOT NULL AND tag != ''
            GROUP BY tag
            ORDER BY tag
        """, (current_year,))
        
        current_year_averages = {row[0]: row[1] for row in cur.fetchall()}
        
        # Get monthly spending data for each tag
        monthly_spending = {}
        for month in range(1, 5):  # January to April
            cur.execute("""
                SELECT tag, ABS(AVG(amount::numeric)) as month_amount
                FROM records_history
                WHERE 
                    EXTRACT(YEAR FROM date::date) = %s AND
                    EXTRACT(MONTH FROM date::date) = %s AND
                    tag IS NOT NULL AND tag != ''
                GROUP BY tag
                ORDER BY tag
            """, (current_year, month))
            
            monthly_spending[month] = {row[0]: row[1] for row in cur.fetchall()}
        
        # Check if there are any tags without budgets
        has_empty_budgets = False
        for tag in available_tags:
            if tag not in budgets or budgets[tag] == 0:
                has_empty_budgets = True
                break
        
        # Prepare data for template
        budget_data = []
        for tag in available_tags:
            monthly_budget = budgets.get(tag, 0)
            last_year_avg = last_year_averages.get(tag, 0)
            current_year_avg = current_year_averages.get(tag, 0)
            
            # Calculate difference between budget and current year average
            if monthly_budget > 0 and current_year_avg > 0:
                difference = monthly_budget - current_year_avg
            else:
                difference = 0
            
            # Get monthly spending data
            monthly_data = {}
            for month in range(1, 5):
                monthly_data[month] = monthly_spending.get(month, {}).get(tag, 0)
            
            budget_data.append({
                'tag': tag,
                'monthly_budget': monthly_budget,
                'last_year_avg': last_year_avg,
                'current_year_avg': current_year_avg,
                'difference': difference,
                'monthly_data': monthly_data
            })
        
        cur.close()
        conn.close()
        
        # Render the budget template
        return render_template_string(BUDGET_TEMPLATE,
                                     budget_data=budget_data,
                                     available_tags=available_tags,
                                     has_empty_budgets=has_empty_budgets,
                                     updated_tag=request.args.get('updated'),
                                     deleted_tag=request.args.get('deleted'),
                                     auto_filled=request.args.get('auto_filled'),
                                     build_number=build_number,
                                     current_month=datetime.now().strftime('%B'),
                                     current_year=current_year,
                                     last_year=last_year)
    
    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Error managing budgets: {str(e)}"

@app.route('/test_database')
def test_database():
    """Debug route to check database structure"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Get column information for records_history table
        cursor.execute("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'records_history'
        """)
        
        columns = cursor.fetchall()
        
        # Get a sample row
        cursor.execute("SELECT * FROM records_history LIMIT 1")
        sample = cursor.fetchone()
        
        # Close connection
        cursor.close()
        conn.close()
        
        result = "<h1>Database Structure</h1>"
        result += "<h2>Table: records_history</h2>"
        result += "<h3>Columns:</h3><ul>"
        
        for col in columns:
            result += f"<li>{col[0]} - {col[1]}</li>"
        
        result += "</ul>"
        
        if sample:
            result += "<h3>Sample Data:</h3><pre>"
            result += str(sample)
            result += "</pre>"
        else:
            result += "<p>No data in table</p>"
            
        return result
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/')
def home():
    """Redirect to the historical analysis page for the home route"""
    return redirect(url_for('historical_analysis'))

if __name__ == '__main__':
    # Tables initialization happens before this point
    
    print("Starting web service on port 5002...")
    print("Open your browser to: http://localhost:5002")
    app.run(host='0.0.0.0', port=5002, debug=True) 