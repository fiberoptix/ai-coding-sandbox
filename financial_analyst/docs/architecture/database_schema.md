# Database Schema Documentation

## Overview

The Financial Analyst application uses PostgreSQL as its primary database. The database schema is designed to support:
- Transaction data storage and retrieval
- Transaction categorization
- Budget management
- Historical analysis
- Data import processing

## Database Configuration

### Connection Details
- **Host**: localhost
- **Port**: 5432
- **Database**: financial_analyst
- **User**: postgres
- **Password**: postgres

### Connection Management
- Connection pooling enabled
- Automatic retry on connection failure
- Connection timeout handling
- Transaction management

## Tables

### 1. records_history

Primary table for storing all processed financial transactions.

```sql
CREATE TABLE records_history (
    id SERIAL PRIMARY KEY,
    date TEXT,
    description TEXT,
    vendor TEXT,
    amount TEXT,
    tag TEXT,
    imported_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Columns
- `id`: Unique identifier for each transaction
- `date`: Transaction date
- `description`: Transaction description
- `vendor`: Vendor or merchant name
- `amount`: Transaction amount
- `tag`: Category tag for the transaction
- `imported_date`: Timestamp of when the record was imported

#### Usage
- Primary storage for all processed transactions
- Source for historical analysis
- Used in budget tracking
- Basis for spending pattern analysis

### 2. tags

Maps transaction descriptions to category tags.

```sql
CREATE TABLE tags (
    id SERIAL PRIMARY KEY,
    description TEXT UNIQUE,
    tag TEXT
);
```

#### Columns
- `id`: Unique identifier for each tag mapping
- `description`: Transaction description (unique)
- `tag`: Category tag assigned to the description

#### Usage
- Maintains consistent categorization
- Supports automatic tagging
- Enables pattern matching
- Reference for budget categories

### 3. records_imported

Temporary storage for newly imported transactions.

```sql
CREATE TABLE records_imported (
    id SERIAL PRIMARY KEY,
    date TEXT,
    description TEXT,
    vendor TEXT,
    amount TEXT
);
```

#### Columns
- `id`: Unique identifier for each imported record
- `date`: Transaction date
- `description`: Transaction description
- `vendor`: Vendor or merchant name
- `amount`: Transaction amount

#### Usage
- Staging area for new imports
- Temporary storage during processing
- Source for tag matching
- Data validation checkpoint

### 4. budgets

Stores budget settings for different categories.

```sql
CREATE TABLE budgets (
    id SERIAL PRIMARY KEY,
    tag TEXT UNIQUE,
    monthly_amount NUMERIC(10,2),
    created_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    modified_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

#### Columns
- `id`: Unique identifier for each budget
- `tag`: Category tag (unique)
- `monthly_amount`: Monthly budget allocation
- `created_date`: When the budget was created
- `modified_date`: Last modification timestamp

#### Usage
- Budget tracking by category
- Monthly spending limits
- Historical budget data
- Budget vs. actual analysis

## Indexes

### Primary Keys
- `records_history.id`
- `tags.id`
- `records_imported.id`
- `budgets.id`

### Unique Constraints
- `tags.description`
- `budgets.tag`

## Data Flow

### Import Process
1. CSV data → `records_imported`
2. Processing and validation
3. Tag matching from `tags`
4. Final storage in `records_history`

### Tagging Process
1. Check `tags` for existing matches
2. Apply automatic tagging rules
3. Update `records_history` with tags
4. Update `tags` with new mappings

### Budget Processing
1. Monthly reset of tracking
2. Transaction categorization using `tags`
3. Aggregation against `budgets`
4. Variance calculation and reporting

## Data Types

### Text Fields
- Used for flexible storage of varying content
- Supports pattern matching
- Allows for future format changes
- Handles special characters

### Numeric Fields
- Used for precise financial calculations
- Supports two decimal places
- Prevents rounding errors
- Enables accurate aggregation

### Timestamps
- Tracks record creation and modification
- Enables temporal analysis
- Supports audit trails
- Facilitates data cleanup

## Maintenance

### Backup Procedures
1. Daily full database dumps
2. Transaction log backups
3. Point-in-time recovery capability
4. Backup verification process

### Data Cleanup
- Periodic review of `records_imported`
- Orphaned tag cleanup
- Duplicate detection
- Data quality checks

### Performance Optimization
- Regular index maintenance
- Query optimization
- Table statistics updates
- Performance monitoring

## Security

### Access Control
- Limited network access
- User authentication
- Role-based permissions
- Connection encryption

### Data Protection
- Sensitive data handling
- Audit logging
- Error tracking
- Backup encryption

## Future Enhancements

### Planned Improvements
- Additional indexes for performance
- Enhanced audit trailing
- Data archiving strategy
- Advanced categorization

### Schema Evolution
- Support for multiple accounts
- Enhanced budget tracking
- Additional metadata fields
- Historical trend analysis 