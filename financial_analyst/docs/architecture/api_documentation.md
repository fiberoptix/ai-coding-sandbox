# API Documentation

## Overview

The Financial Analyst application provides a web-based API through Flask routes. These endpoints handle various aspects of financial data management, analysis, and visualization.

## Base URL

All endpoints are relative to: `http://localhost:5002`

## Endpoints

### Main Pages

#### 1. Historical Analysis (Home)
```
GET /
```
- **Description**: Main dashboard showing historical financial analysis
- **Response**: HTML page with charts and analysis
- **Redirects**: From `/` to `/historical_analysis`

#### 2. Data Import and Tagging
```
GET /data_import_tagging
POST /data_import_tagging
```
- **Description**: Interface for importing and tagging transactions
- **Methods**:
  - GET: Display import form
  - POST: Process file upload
- **Parameters** (POST):
  - `file`: CSV file upload
  - `action`: Import action type

#### 3. Monthly Summary
```
GET /monthly_summary
```
- **Description**: Monthly financial reports and analysis
- **Query Parameters**:
  - `year`: Filter by year (optional)
  - `month`: Filter by month (optional)
  - `tag`: Filter by category (optional)

#### 4. Transaction Summary
```
GET /transaction_summary
```
- **Description**: Detailed transaction listing and analysis
- **Query Parameters**:
  - `sort`: Sort field
  - `dir`: Sort direction
  - `tag`: Filter by category
  - `start_date`: Start date filter
  - `end_date`: End date filter

#### 5. Budget Settings
```
GET /budgets
POST /budgets
```
- **Description**: Budget management interface
- **Methods**:
  - GET: Display budget settings
  - POST: Update budget settings
- **Parameters** (POST):
  - `tag`: Category tag
  - `amount`: Monthly budget amount
  - `action`: Budget action (add/update/delete)

### Utility Endpoints

#### 1. Test Database
```
GET /test_database
```
- **Description**: Check database connectivity
- **Response**: Connection status and build number

#### 2. Row Count
```
GET /row_count
```
- **Description**: Get table row counts
- **Response**: JSON with table statistics

#### 3. Check Duplicates
```
GET /check_duplicates
```
- **Description**: Check for duplicate transactions
- **Response**: List of potential duplicates

#### 4. Auto Tag
```
GET /auto_tag
POST /auto_tag
```
- **Description**: Automatic transaction tagging
- **Methods**:
  - GET: Status of auto-tagging
  - POST: Trigger auto-tagging process

#### 5. Export Data
```
GET /export_tags
GET /export_history
```
- **Description**: Export data in CSV format
- **Endpoints**:
  - `/export_tags`: Export tag mappings
  - `/export_history`: Export transaction history

## Response Formats

### HTML Pages
- Content-Type: text/html
- Template-based rendering
- Bootstrap styling
- Interactive elements

### JSON Responses
- Content-Type: application/json
- Standard format:
  ```json
  {
    "status": "success|error",
    "message": "Status message",
    "data": {
      // Response data
    }
  }
  ```

### CSV Exports
- Content-Type: text/csv
- File download headers
- UTF-8 encoding

## Error Handling

### HTTP Status Codes
- 200: Success
- 302: Redirect
- 400: Bad Request
- 404: Not Found
- 500: Server Error

### Error Response Format
```json
{
  "status": "error",
  "message": "Error description",
  "error_code": "ERROR_TYPE"
}
```

## Data Processing

### File Import
1. File validation
2. CSV parsing
3. Data cleaning
4. Database insertion
5. Auto-tagging
6. Response generation

### Data Export
1. Query execution
2. Data formatting
3. CSV generation
4. File streaming

## Security

### Input Validation
- File type checking
- Size limitations
- Content validation
- SQL injection prevention

### Error Handling
- Graceful error recovery
- User-friendly messages
- Detailed logging
- Security headers

## Rate Limiting

### Limits
- File uploads: 10MB max
- API calls: 100/minute
- Export size: 1000 rows/request
- Session timeout: 30 minutes

## Future Enhancements

### Planned Features
- REST API endpoints
- Authentication system
- Rate limiting
- API versioning

### API Improvements
- GraphQL support
- Webhook notifications
- Batch operations
- Enhanced filtering

## Usage Examples

### Import Data
```bash
curl -X POST http://localhost:5002/data_import_tagging \
  -F "file=@transactions.csv" \
  -F "action=import"
```

### Export Tags
```bash
curl -O http://localhost:5002/export_tags
```

### Update Budget
```bash
curl -X POST http://localhost:5002/budgets \
  -d "tag=Groceries" \
  -d "amount=500.00" \
  -d "action=update"
```

### Auto-Tag Transactions
```bash
curl -X POST http://localhost:5002/auto_tag
```

## Testing

### Endpoint Tests
```bash
# Test database connection
curl http://localhost:5002/test_database

# Check row counts
curl http://localhost:5002/row_count

# Verify duplicates check
curl http://localhost:5002/check_duplicates
```

### Health Checks
```bash
# Basic health check
curl -I http://localhost:5002/

# Database health
curl http://localhost:5002/test_database
``` 