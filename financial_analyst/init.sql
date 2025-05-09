-- Simple SQL setup script for importing CSV data with extra-robust parsing

-- First, create a staging table with a single TEXT column
CREATE TABLE csv_raw (
    line TEXT
);

-- Import the entire CSV file as raw text
\echo 'Importing CSV data as raw text...'
COPY csv_raw FROM '/app/transactions.csv';

-- Show the raw contents for debugging
\echo 'First few rows of raw data:'
SELECT * FROM csv_raw LIMIT 5;

-- Create the final transactions table based on the CSV header
DO $$
DECLARE
    header_row TEXT;
    column_array TEXT[];
    column_name TEXT;
    column_def TEXT := '';
    sql_create TEXT;
    i INTEGER;
BEGIN
    -- Get the first row of the CSV (should be the header)
    SELECT line INTO header_row FROM csv_raw LIMIT 1;
    
    -- Parse the header into column names
    column_array := string_to_array(header_row, ',');
    
    -- Generate column definitions
    FOR i IN 1..array_length(column_array, 1) LOOP
        -- Clean and normalize column name
        column_name := regexp_replace(trim(column_array[i]), '[^a-zA-Z0-9_]', '_', 'g');
        
        -- Make column name lowercase to avoid case sensitivity issues
        column_name := lower(column_name);
        
        -- Add column to the definition
        IF i > 1 THEN
            column_def := column_def || ', ';
        END IF;
        column_def := column_def || quote_ident(column_name) || ' TEXT';
    END LOOP;
    
    -- Create the transactions table with proper names
    sql_create := 'CREATE TABLE transactions (id SERIAL PRIMARY KEY, ' || column_def || ')';
    EXECUTE sql_create;
    
    RAISE NOTICE 'Created transactions table with columns: %', column_def;
END $$;

-- Import the data from the raw table to the structured table
DO $$
DECLARE
    header_row TEXT;
    data_row TEXT;
    column_array TEXT[];
    column_names TEXT := '';
    column_values TEXT[];
    sql_insert TEXT;
    row_record RECORD;
    i INTEGER;
    column_name TEXT;
    error_count INTEGER := 0;
    success_count INTEGER := 0;
    mismatched_count INTEGER := 0;
BEGIN
    -- Get the header row
    SELECT line INTO header_row FROM csv_raw LIMIT 1;
    column_array := string_to_array(header_row, ',');
    
    -- Prepare column names for the INSERT statement (lowercase)
    FOR i IN 1..array_length(column_array, 1) LOOP
        -- Clean and normalize column name
        column_name := lower(regexp_replace(trim(column_array[i]), '[^a-zA-Z0-9_]', '_', 'g'));
        
        IF i > 1 THEN
            column_names := column_names || ', ';
        END IF;
        column_names := column_names || quote_ident(column_name);
    END LOOP;
    
    -- Process each data row (skip the header)
    FOR row_record IN SELECT line FROM csv_raw OFFSET 1 LOOP
        -- Split the row into values
        column_values := string_to_array(row_record.line, ',');
        
        -- Handle mismatched column counts by extending the array if needed
        IF array_length(column_values, 1) <> array_length(column_array, 1) THEN
            RAISE NOTICE 'Row with mismatched column count: %. Attempting to adjust...', row_record.line;
            mismatched_count := mismatched_count + 1;
            
            IF array_length(column_values, 1) < array_length(column_array, 1) THEN
                -- Extend the array with empty values
                FOR i IN array_length(column_values, 1)+1..array_length(column_array, 1) LOOP
                    column_values := array_append(column_values, '');
                END LOOP;
            END IF;
            -- If there are too many columns, we'll just use the ones we need
        END IF;
        
        -- Limit column_values to the expected number of columns
        IF array_length(column_values, 1) > array_length(column_array, 1) THEN
            -- Trim the array to match expected columns
            column_values := column_values[1:array_length(column_array, 1)];
        END IF;
        
        -- Handle empty fields and escape values
        FOR i IN 1..array_length(column_values, 1) LOOP
            column_values[i] := COALESCE(column_values[i], '');
            -- Escape single quotes
            column_values[i] := replace(column_values[i], '''', '''''');
        END LOOP;
        
        -- Construct the INSERT statement with properly quoted values
        sql_insert := 'INSERT INTO transactions (' || column_names || ') VALUES (';
        FOR i IN 1..array_length(column_values, 1) LOOP
            IF i > 1 THEN
                sql_insert := sql_insert || ', ';
            END IF;
            sql_insert := sql_insert || '''' || column_values[i] || '''';
        END LOOP;
        sql_insert := sql_insert || ')';
        
        -- Execute the insert
        BEGIN
            EXECUTE sql_insert;
            success_count := success_count + 1;
        EXCEPTION WHEN OTHERS THEN
            error_count := error_count + 1;
            RAISE NOTICE 'Error inserting row: % - %', row_record.line, SQLERRM;
        END;
    END LOOP;
    
    -- Report completion with detailed counts
    RAISE NOTICE 'Data import completed:';
    RAISE NOTICE '  Success: % rows', success_count;
    RAISE NOTICE '  Errors: % rows', error_count;
    RAISE NOTICE '  Rows with mismatched columns (adjusted): % rows', mismatched_count;
    RAISE NOTICE '  Total processed: % rows', success_count + error_count;
END $$;

-- Print out sample data
\echo 'Sample data from transactions table:'
SELECT * FROM transactions LIMIT 10;

-- Count rows
\echo 'Total rows imported:'
SELECT COUNT(*) FROM transactions;

-- Clean up the raw table
DROP TABLE csv_raw;

-- Help message
\echo '';
\echo 'IMPORT COMPLETE - CSV data has been imported into the transactions table';
\echo '';
\echo 'Useful commands:';
\echo '- SELECT * FROM transactions LIMIT 10;         -- View first 10 transactions';
\echo '- SELECT DISTINCT vendor FROM transactions;    -- View unique values in a column';
\echo '- SELECT * FROM transactions WHERE description ILIKE ''%payment%''; -- Search transactions';
\echo '- \d transactions                              -- View table structure';
\echo '';
\echo 'Search example (use lowercase column names):';
\echo '- SELECT * FROM transactions WHERE description ILIKE ''%golf%'';'; 