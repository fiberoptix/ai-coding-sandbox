from flask import Flask, render_template_string, request, redirect, url_for
import psycopg2
import psycopg2.extras
import os
import time
from urllib.parse import urlparse, parse_qs

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
            WHERE %s ILIKE '%' || description || '%' OR description ILIKE '%' || %s || '%'
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 1
        """, (description, description))
        
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
    <title>Transaction Tagger</title>
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
        <h1>Transaction Tagger</h1>
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
        
        <div class="search-section">
            <form method="GET" action="/">
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
        
        {% if search %}
        <div class="tag-all-section" style="background-color: #f0f8ff; padding: 15px; border-radius: 5px; margin-bottom: 20px; border: 1px solid #b8daff;">
            <form method="POST" action="/tag_all">
                <input type="hidden" name="search" value="{{ search }}">
                <input type="hidden" name="filter" value="{{ filter }}">
                <input type="text" name="tag" placeholder="Enter tag for all results" required style="width: 250px; padding: 8px; margin-right: 5px;">
                <button type="submit" style="padding: 8px; background-color: #007BFF; color: white; border: none; cursor: pointer;">Tag All Matching Transactions</button>
            </form>
        </div>
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
                        <th>Description</th>
                        <th>Count</th>
                        <th>Amount</th>
                        <th>Tag</th>
                    </tr>
                </thead>
                <tbody>
                    {% for pair in transaction_pairs %}
                    <tr>
                        <td>{{ pair.description }}</td>
                        <td>{{ pair.count }}</td>
                        <td>{{ pair.total }}</td>
                        <td>
                            <form class="tag-form" action="/update_tag" method="post">
                                <input type="hidden" name="description" value="{{ pair.description }}">
                                <input type="hidden" name="page" value="{{ page }}">
                                <input type="hidden" name="search" value="{{ search }}">
                                <input type="hidden" name="filter" value="{{ filter }}">
                                <input type="hidden" name="from_page" value="{% if request.path == '/most_common' %}most_common{% else %}index{% endif %}">
                                <input type="text" name="tag" class="tag-input" 
                                      value="{{ existing_tags[pair.description] if pair.description in existing_tags else '' }}" 
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
                        <input type="checkbox" id="clear_transactions" name="tables" value="transactions">
                        <label for="clear_transactions">Current Transactions</label>
                    </div>
                    <div style="margin-bottom: 10px;">
                        <input type="checkbox" id="clear_tags" name="tables" value="transaction_tags">
                        <label for="clear_tags">Transaction Tags</label>
                    </div>
                    <div style="margin-bottom: 10px;">
                        <input type="checkbox" id="clear_history" name="tables" value="transaction_history">
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

@app.route('/')
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
        
        # Base query for unique description:vendor pairs and their counts
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
        
        # Group by and order
        query += """
            GROUP BY t.description, t.vendor, tt.tag
            ORDER BY COUNT(*) DESC
        """
        
        # Execute count query for pagination
        count_query = "SELECT COUNT(*) FROM (" + query + ") as subquery"
        cur.execute(count_query, params)
        total_pairs = cur.fetchone()[0]
        total_pages = (total_pairs + items_per_page - 1) // items_per_page
        
        # Add pagination
        query += " LIMIT %s OFFSET %s"
        offset = (page - 1) * items_per_page
        params.extend([items_per_page, offset])
        
        # Execute final query
        cur.execute(query, params)
        transaction_pairs = cur.fetchall()
        
        # Format the results for display
        formatted_pairs = []
        for pair in transaction_pairs:
            description, vendor, count, total, tag = pair
            formatted_pairs.append({
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
                                    transaction_pairs=formatted_pairs,
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
                                    build_number=build_number)
                
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
            return redirect(url_for('most_common', page=page, filter=filter_type))
        
        # Otherwise, redirect back to the index page as before
        redirect_url = url_for('index', page=page)
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

@app.route('/tag_all', methods=['POST'])
def tag_all():
    """Tag all matching descriptions"""
    search_term = request.form.get('search_term', '')
    tag = request.form.get('tag', '').strip()
    
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
        cur.execute(query, ['%' + search_term + '%'])
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
        return redirect(url_for('index', unique_tags_applied=unique_tags_applied))
        
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
    filter_type = request.args.get('filter', 'all')
    page = request.args.get('page', 1, type=int)
    moved_count = request.args.get('moved_count', 0, type=int)
    records_imported = request.args.get('records_imported', 0, type=int)
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
        
        # Group and order by count
        query += " GROUP BY t.description, t.vendor, tt.tag ORDER BY count DESC"
        
        # Count total results for pagination
        count_query = "SELECT COUNT(*) FROM (" + query + ") as subquery"
        cur.execute(count_query, params)
        total_pairs = cur.fetchone()[0]
        total_pages = (total_pairs + items_per_page - 1) // items_per_page
        
        # Add pagination
        query += " LIMIT %s OFFSET %s"
        offset = (page - 1) * items_per_page
        params.extend([items_per_page, offset])
        
        # Execute query
        cur.execute(query, params)
        transaction_pairs = cur.fetchall()
        
        # Format for display
        formatted_pairs = []
        for pair in transaction_pairs:
            description, vendor, count, total, tag = pair
            formatted_pairs.append({
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
                                    transaction_pairs=formatted_pairs,
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
                                    build_number=build_number)
                
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
                    auto_tagged = auto_apply_tags()
                    return redirect(url_for('index', records_imported=records_imported, auto_tagged=auto_tagged))
                
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
    """Show monthly spending summary"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get build number
        build_number = get_build_number()
        
        # Get monthly spending data
        cur.execute("""
            SELECT month, tag, total_amount, transaction_count 
            FROM monthly_spending 
            ORDER BY month DESC, total_amount
        """)
        monthly_data = cur.fetchall()
        
        # Format for display
        formatted_months = []
        current_month = None
        month_group = None
        
        for row in monthly_data:
            month, tag, total_amount, transaction_count = row
            
            if month != current_month:
                if month_group:
                    formatted_months.append(month_group)
                month_group = {
                    'month': month,
                    'entries': [],
                    'total': 0
                }
                current_month = month
            
            month_group['entries'].append({
                'tag': tag or 'Untagged',
                'amount': total_amount,
                'count': transaction_count
            })
            month_group['total'] += float(total_amount) if total_amount else 0
        
        # Add the last month group
        if month_group:
            formatted_months.append(month_group)
        
        # Get the count of transactions in history
        history_count = get_history_count()
        
        # Get count of unique tags
        tags_count = get_tags_count()
        
        cur.close()
        conn.close()
        
        return render_template_string(MONTHLY_TEMPLATE,
                                     months=formatted_months,
                                     history_count=history_count,
                                     tags_count=tags_count,
                                     build_number=build_number)
    
    except Exception as e:
        return f"Error generating monthly summary: {str(e)}"

@app.route('/tag_summary')
def tag_summary_view():
    """Show summary by tag"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get build number
        build_number = get_build_number()
        
        # Get tag summary data
        cur.execute("""
            SELECT tag, total_amount, transaction_count 
            FROM tag_summary 
            ORDER BY total_amount
        """)
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
                                     build_number=build_number)
    
    except Exception as e:
        return f"Error generating tag summary: {str(e)}"

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
        <h1>Monthly Spending Summary</h1>
        
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/tag_summary">Tag Summary</a>
            <a href="/monthly_summary">Monthly Summary</a>
        </div>
        
        <div>
            <p>Total transactions in history: <strong>{{ history_count }}</strong></p>
            <p>Total unique tags: <strong>{{ tags_count }}</strong></p>
        </div>
        
        {% for month in months %}
        <div class="month-card">
            <div class="month-header">
                <h2>{{ month.month }}</h2>
                <span class="month-total {% if month.total < 0 %}negative{% else %}positive{% endif %}">
                    Total: ${{ '{:,.2f}'.format(month.total|abs) }}
                </span>
            </div>
            
            <table>
                <thead>
                    <tr>
                        <th>Tag</th>
                        <th>Amount</th>
                        <th>Transactions</th>
                    </tr>
                </thead>
                <tbody>
                    {% for entry in month.entries %}
                    <tr>
                        <td>{{ entry.tag }}</td>
                        <td {% if entry.amount < 0 %}class="negative"{% else %}class="positive"{% endif %}>
                            ${{ '{:,.2f}'.format(entry.amount|abs) }}
                        </td>
                        <td>{{ entry.count }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
        </div>
        {% else %}
        <div class="month-card">
            <p>No monthly data available. Import your transaction history to see spending patterns by month.</p>
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
    </style>
</head>
<body>
    <div class="build-info">Build: {{ build_number }}</div>
    <div class="container">
        <h1>Tag Summary</h1>
        
        <div class="nav-links">
            <a href="/">Home</a>
            <a href="/tag_summary">Tag Summary</a>
            <a href="/monthly_summary">Monthly Summary</a>
        </div>
        
        <div class="total-section">
            <h3>Total: <span {% if total_amount < 0 %}class="negative"{% else %}class="positive"{% endif %}>
                ${{ '{:,.2f}'.format(total_amount|abs) }}
            </span></h3>
            <p>Total transactions in history: <strong>{{ history_count }}</strong></p>
        </div>
        
        <div class="tag-container">
            <table>
                <thead>
                    <tr>
                        <th>Tag</th>
                        <th>Amount</th>
                        <th>Transactions</th>
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

if __name__ == '__main__':
    # Initialize database tables
    initialize_database()
    
    print("Starting web service on port 5001...")
    print("Open your browser to: http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=True) 