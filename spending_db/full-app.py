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
    
    # Create transaction_tags table if it doesn't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transaction_tags (
            id SERIAL PRIMARY KEY,
            description TEXT UNIQUE,
            tag TEXT
        )
    """)
    
    # Create transaction_history table if it doesn't exist
    cur.execute("""
        CREATE TABLE IF NOT EXISTS transaction_history (
            id SERIAL PRIMARY KEY,
            date TEXT,
            description TEXT,
            vendor TEXT,
            amount TEXT,
            tag TEXT,
            imported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
    cur.execute("SELECT description, tag FROM transaction_tags")
    existing_tags = cur.fetchall()
    
    tags_applied = 0
    
    # Get all unique descriptions that don't have tags yet
    cur.execute("""
        SELECT DISTINCT t.description
        FROM transactions t
        LEFT JOIN transaction_tags tt ON t.description = tt.description
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
                    INSERT INTO transaction_tags (description, tag)
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
        FROM transactions t
        LEFT JOIN transaction_tags tt ON t.description = tt.description
        WHERE tt.id IS NULL
    """)
    
    still_untagged = cur.fetchall()
    partial_matches = 0
    
    for untagged in still_untagged:
        description = untagged[0]
        
        # Find most commonly used tag for similar descriptions
        cur.execute("""
            SELECT tag, COUNT(*) AS count
            FROM transaction_tags
            WHERE %s ILIKE '%' || description || '%' OR description ILIKE '%' || %s || '%'
            GROUP BY tag
            ORDER BY count DESC
            LIMIT 1
        """, (description, description))
        
        matches = cur.fetchone()
        if matches:
            # Apply the most common tag
            cur.execute("""
                INSERT INTO transaction_tags (description, tag)
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
    """Get the count of transactions in the transaction_history table"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(*) FROM transaction_history")
    count = cur.fetchone()[0]
    
    cur.close()
    conn.close()
    
    return count

def get_tags_count():
    """Get the count of unique tags in the transaction_history table"""
    conn = get_db_connection()
    cur = conn.cursor()
    
    cur.execute("SELECT COUNT(DISTINCT tag) FROM transaction_history")
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
</head>
<body>
    <div class="container">
        <h1>Transaction Tagger</h1>
        <p>Tag your transactions to categorize spending patterns.</p>
        
        <div class="search-section">
            <form method="GET" action="/">
                <input type="text" name="search" value="{{ search }}" placeholder="Search transactions..." autofocus>
                <select name="filter">
                    <option value="all" {% if filter == 'all' %}selected{% endif %}>All Transactions</option>
                    <option value="untagged" {% if filter == 'untagged' %}selected{% endif %}>Untagged Only</option>
                    <option value="tagged" {% if filter == 'tagged' %}selected{% endif %}>Tagged Only</option>
                </select>
                <button type="submit">Search</button>
                <a href="/most_common" class="button" style="background-color: #4CAF50; color: white; text-decoration: none; padding: 8px; border-radius: 3px; margin-left: 10px;">Most Common</a>
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
                        <td>{% if pair.total_amount < 0 %}-{% endif %}${{ '{:.2f}'.format(pair.total_amount|abs) }}</td>
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
    cleared = request.args.get('cleared', '')
    page = request.args.get('page', 1, type=int)
    items_per_page = 100
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Get total transaction count (only from transactions table, not history)
        cur.execute("SELECT COUNT(*) FROM transactions")
        total_transactions = cur.fetchone()[0]
        
        # Get count of total tagged transactions (only from current transactions)
        cur.execute("""
            SELECT COUNT(*) FROM transactions t
            JOIN transaction_tags tt ON t.description = tt.description
        """)
        total_tagged_transactions = cur.fetchone()[0]
        
        # Get count of unique descriptions
        cur.execute("SELECT COUNT(DISTINCT description) FROM transactions")
        total_unique_descriptions = cur.fetchone()[0]
        
        # Base query to get unique descriptions
        query = """
        SELECT 
            t.description, 
            COUNT(*)::INTEGER as count, 
            SUM(CASE WHEN t.amount ~ '^-?[0-9.,]+$' THEN CAST(REPLACE(REPLACE(t.amount, ',', ''), '$', '') AS NUMERIC) ELSE 0 END) as total_amount
        FROM transactions t
        """
        
        # Add join for filtering by tag status
        if filter_type in ['tagged', 'untagged']:
            query += """
            LEFT JOIN transaction_tags tt ON t.description = tt.description
            """
            
            if filter_type == 'tagged':
                query += "WHERE tt.id IS NOT NULL "
            else:  # untagged
                query += "WHERE tt.id IS NULL "
            
            # Add search filter if provided
            if search:
                query += "AND t.description ILIKE %s "
                params = [f"%{search}%"]
        else:
            # Just filter by search if provided
            if search:
                query += "WHERE t.description ILIKE %s "
                params = [f"%{search}%"]
            else:
                params = []
                
        query += """
        GROUP BY t.description
        ORDER BY t.description ASC
        """
        
        # Count total rows for pagination
        count_query = """
        SELECT COUNT(*) FROM (
        """ + query + """) AS subquery
        """
        
        # Execute count query with search parameters
        if 'params' in locals():
            cur.execute(count_query, params)
        else:
            cur.execute(count_query)
            
        total_count = cur.fetchone()[0]
        total_pages = (total_count + items_per_page - 1) // items_per_page
        
        # Add pagination
        query += """
        LIMIT %s OFFSET %s
        """
        
        # Add pagination parameters
        if 'params' in locals():
            params.extend([items_per_page, (page - 1) * items_per_page])
        else:
            params = [items_per_page, (page - 1) * items_per_page]
        
        # Execute the main query with all parameters
        cur.execute(query, params)
        transaction_pairs = cur.fetchall()
        
        # Debug and format the results
        formatted_pairs = []
        for pair in transaction_pairs:
            formatted_pair = {
                'description': pair['description'],
                'count': int(pair['count']),
                'total_amount': float(pair['total_amount'] or 0)
            }
            formatted_pairs.append(formatted_pair)
        
        # Get existing tags for current transactions only
        cur.execute("""
            SELECT tt.description, tt.tag 
            FROM transaction_tags tt
            JOIN transactions t ON tt.description = t.description
        """)
        existing_tags = {row['description']: row['tag'] for row in cur.fetchall()}
        
        # Get count of tagged descriptions in current transactions
        cur.execute("""
            SELECT COUNT(DISTINCT tt.description) 
            FROM transaction_tags tt
            JOIN transactions t ON tt.description = t.description
        """)
        tagged_count = cur.fetchone()[0]
        
        # Get count of untagged descriptions in current transactions
        cur.execute("""
            SELECT COUNT(DISTINCT description) 
            FROM transactions 
            WHERE description NOT IN (SELECT description FROM transaction_tags)
        """)
        total_untagged_descriptions = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        # Set remaining to tag to 0 only if there are no records to tag
        # otherwise set it to the actual number of untagged descriptions
        remaining_to_tag = 0 if total_transactions == 0 else total_untagged_descriptions
        
        # Get count of transactions in history
        history_count = get_history_count()
        
        # Get count of unique tags in history
        tags_count = get_tags_count()
        
        return render_template_string(HTML_TEMPLATE, 
                                    transaction_pairs=formatted_pairs,
                                    existing_tags=existing_tags,
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
                                    cleared=cleared,
                                    remaining_to_tag=remaining_to_tag)
              
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
            INSERT INTO transaction_tags (description, tag)
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
            FROM transaction_tags 
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
    """Tag all matching transactions with the same tag"""
    search = request.form.get('search', '')
    filter_type = request.form.get('filter', 'all')
    tag = request.form.get('tag', '')
    
    # Debug logging
    print(f"Tag All received - search: '{search}', filter: '{filter_type}', tag: '{tag}'")
    
    # If no search term is provided but there's a searchbox value in the form or referrer
    if not search and request.referrer and 'search=' in request.referrer:
        # Extract search from referrer URL
        parsed_url = urlparse(request.referrer)
        params = parse_qs(parsed_url.query)
        if 'search' in params:
            search = params['search'][0]
            print(f"Extracted search from referrer: '{search}'")
    
    if not tag:
        return redirect(url_for('index'))
    
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Build query to find ALL matching transactions (without DISTINCT)
        query = """
        SELECT description
        FROM transactions
        """
        
        params = []
        
        # Add search condition
        if search:
            query += "WHERE description ILIKE %s "
            params = [f"%{search}%"]
        
        # Add filter condition if needed
        if filter_type in ['tagged', 'untagged']:
            # Check if we already have WHERE clause
            if search:
                query += "AND "
            else:
                query += "WHERE "
                
            if filter_type == 'tagged':
                query += "description IN (SELECT description FROM transaction_tags) "
            else:  # untagged
                query += "description NOT IN (SELECT description FROM transaction_tags) "
        
        # Execute query to get ALL matching transactions
        print(f"Executing query: {query} with params: {params}")
        cur.execute(query, params)
        matching_transactions = cur.fetchall()
        
        # Count total transactions (doesn't need to be distinct)
        total_affected = len(matching_transactions)
        print(f"Total transactions found: {total_affected}")
        
        # Get unique descriptions to tag (we still need to do this for the tagging part)
        unique_descriptions = set()
        for trans in matching_transactions:
            unique_descriptions.add(trans[0])
        
        unique_tags_applied = len(unique_descriptions)
        print(f"Unique descriptions to tag: {unique_tags_applied}")
        
        # Apply tag to each unique description
        for desc in unique_descriptions:
            cur.execute("""
                INSERT INTO transaction_tags (description, tag)
                VALUES (%s, %s)
                ON CONFLICT (description) 
                DO UPDATE SET tag = EXCLUDED.tag
            """, (desc, tag))
        
        conn.commit()
        cur.close()
        conn.close()
        
        # Redirect back with appropriate parameters
        redirect_url = url_for('index', search=search, 
                             filter=filter_type, 
                             auto_tagged=total_affected,
                             unique_tags_applied=unique_tags_applied)
        print(f"Redirecting to: {redirect_url}")
        return redirect(redirect_url)
        
    except Exception as e:
        print(f"Error in tag_all: {str(e)}")
        return f"Error tagging transactions: {str(e)}"

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
    items_per_page = 100
    
    try:
        conn = get_db_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # Get total transaction count (only from transactions table, not history)
        cur.execute("SELECT COUNT(*) FROM transactions")
        total_transactions = cur.fetchone()[0]
        
        # Get count of total tagged transactions (only from current transactions)
        cur.execute("""
            SELECT COUNT(*) FROM transactions t
            JOIN transaction_tags tt ON t.description = tt.description
        """)
        total_tagged_transactions = cur.fetchone()[0]
        
        # Get count of unique descriptions
        cur.execute("SELECT COUNT(DISTINCT description) FROM transactions")
        total_unique_descriptions = cur.fetchone()[0]
        
        # Base query to get unique descriptions ordered by count
        query = """
        SELECT 
            t.description, 
            COUNT(*)::INTEGER as count, 
            SUM(CASE WHEN t.amount ~ '^-?[0-9.,]+$' THEN CAST(REPLACE(REPLACE(t.amount, ',', ''), '$', '') AS NUMERIC) ELSE 0 END) as total_amount
        FROM transactions t
        LEFT JOIN transaction_tags tt ON t.description = tt.description
        WHERE tt.id IS NULL
        """
        
        params = []
                
        query += """
        GROUP BY t.description
        ORDER BY count DESC
        """
        
        # Count total rows for pagination
        count_query = """
        SELECT COUNT(*) FROM (
        """ + query + """) AS subquery
        """
        
        # Execute count query
        cur.execute(count_query, params)
        total_count = cur.fetchone()[0]
        total_pages = (total_count + items_per_page - 1) // items_per_page
        
        # Add pagination
        query += """
        LIMIT %s OFFSET %s
        """
        
        # Add pagination parameters
        params.extend([items_per_page, (page - 1) * items_per_page])
        
        # Execute the main query with all parameters
        cur.execute(query, params)
        transaction_pairs = cur.fetchall()
        
        # Format the results
        formatted_pairs = []
        for pair in transaction_pairs:
            formatted_pair = {
                'description': pair['description'],
                'count': int(pair['count']),
                'total_amount': float(pair['total_amount'] or 0)
            }
            formatted_pairs.append(formatted_pair)
        
        # Get existing tags for current transactions only
        cur.execute("""
            SELECT tt.description, tt.tag 
            FROM transaction_tags tt
            JOIN transactions t ON tt.description = t.description
        """)
        existing_tags = {row['description']: row['tag'] for row in cur.fetchall()}
        
        # Get count of tagged descriptions in current transactions
        cur.execute("""
            SELECT COUNT(DISTINCT tt.description) 
            FROM transaction_tags tt
            JOIN transactions t ON tt.description = t.description
        """)
        tagged_count = cur.fetchone()[0]
        
        # Get count of untagged descriptions in current transactions
        cur.execute("""
            SELECT COUNT(DISTINCT description) 
            FROM transactions 
            WHERE description NOT IN (SELECT description FROM transaction_tags)
        """)
        total_untagged_descriptions = cur.fetchone()[0]
        
        cur.close()
        conn.close()
        
        # Set remaining to tag to 0 only if there are no records to tag
        # otherwise set it to the actual number of untagged descriptions
        remaining_to_tag = 0 if total_transactions == 0 else total_untagged_descriptions
        
        # Get count of transactions in history
        history_count = get_history_count()
        
        # Get count of unique tags in history
        tags_count = get_tags_count()
        
        return render_template_string(HTML_TEMPLATE, 
                                    transaction_pairs=formatted_pairs,
                                    existing_tags=existing_tags,
                                    page=page,
                                    total_pages=total_pages,
                                    search="",
                                    filter=filter_type,
                                    auto_tagged=0,
                                    unique_tags_applied=0,
                                    total_transactions=total_transactions,
                                    tagged_count=tagged_count,
                                    total_tagged_transactions=total_tagged_transactions,
                                    total_untagged_descriptions=total_untagged_descriptions,
                                    history_count=history_count,
                                    tags_count=tags_count,
                                    total_unique_descriptions=total_unique_descriptions,
                                    moved_count=moved_count,
                                    remaining_to_tag=remaining_to_tag)
              
    except Exception as e:
        return f"Error: {str(e)}"

@app.route('/push_to_history', methods=['POST'])
def push_to_history():
    """Move all tagged transactions to the transaction_history table and remove them from transactions"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # First, insert all tagged transactions into transaction_history
        cur.execute("""
            INSERT INTO transaction_history (date, description, vendor, amount, tag)
            SELECT t._date, t.description, t.vendor, t.amount, tt.tag
            FROM transactions t
            JOIN transaction_tags tt ON t.description = tt.description
            WHERE NOT EXISTS (
                SELECT 1 FROM transaction_history h 
                WHERE h.date = t._date AND h.description = t.description AND 
                      h.vendor = t.vendor AND h.amount = t.amount
            )
        """)
        
        # Get the count of transactions moved
        moved_count = cur.rowcount
        
        # Delete all tagged transactions from the transactions table
        cur.execute("""
            DELETE FROM transactions
            WHERE description IN (SELECT description FROM transaction_tags)
        """)
        
        # We no longer clear the transaction_tags table, keeping the tags for future matching
        
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('index', moved_count=moved_count))
        
    except Exception as e:
        return f"Error pushing to history: {str(e)}"

@app.route('/export_history')
def export_history():
    """Export all transactions from transaction_history as CSV file"""
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        
        # Get all transactions from history
        cur.execute("""
            SELECT date, description, vendor, amount, tag, imported_date
            FROM transaction_history 
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
            headers={"Content-disposition": "attachment; filename=transaction_history.csv"}
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
                    cur.execute("TRUNCATE transaction_tags")
                
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
                            INSERT INTO transaction_tags (description, tag)
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
                    cur.execute("TRUNCATE transaction_history")
                
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
                            INSERT INTO transaction_history (date, description, vendor, amount, tag)
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

@app.route('/clear_database', methods=['POST'])
def clear_database():
    """Clear database tables"""
    try:
        tables_to_clear = request.form.getlist('tables')
        
        conn = get_db_connection()
        cur = conn.cursor()
        
        for table in tables_to_clear:
            if table in ['transactions', 'transaction_tags', 'transaction_history']:
                cur.execute(f"TRUNCATE {table}")
        
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('index', cleared=','.join(tables_to_clear)))
        
    except Exception as e:
        return f"Error clearing tables: {str(e)}"

if __name__ == '__main__':
    # Initialize database tables
    initialize_database()
    
    print("Starting web service on port 5001...")
    print("Open your browser to: http://localhost:5001")
    app.run(host='0.0.0.0', port=5001, debug=True) 