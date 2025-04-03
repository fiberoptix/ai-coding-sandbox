import csv
import statistics

def read_csv_file(file_path):
    """Read CSV file and return its contents as a list of dictionaries."""
    data = []
    try:
        with open(file_path, 'r') as csv_file:
            csv_reader = csv.DictReader(csv_file)
            for row in csv_reader:
                # Convert salary to integer for calculations
                row['SALARY'] = int(row['SALARY'])
                data.append(row)
        return data
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        return None

def calculate_statistics(data):
    """Calculate salary statistics from the data."""
    if not data:
        return None
    
    # Extract salaries
    salaries = [row['SALARY'] for row in data]
    
    # Calculate statistics
    stats = {
        'count': len(salaries),
        'min': min(salaries),
        'max': max(salaries),
        'average': round(sum(salaries) / len(salaries), 2),
        'median': statistics.median(salaries)
    }
    return stats

def group_by_city(data):
    """Group data by city and calculate average salary per city."""
    if not data:
        return None
    
    city_data = {}
    for row in data:
        city = row['CITY']
        if city not in city_data:
            city_data[city] = {'count': 0, 'total_salary': 0}
        
        city_data[city]['count'] += 1
        city_data[city]['total_salary'] += row['SALARY']
    
    # Calculate average salary per city
    for city in city_data:
        city_data[city]['average_salary'] = round(
            city_data[city]['total_salary'] / city_data[city]['count'], 2
        )
    
    return city_data

def main():
    file_path = 'employee_data.csv'
    data = read_csv_file(file_path)
    
    if data:
        print(f"Successfully read {len(data)} records from {file_path}")
        
        # Calculate and display overall statistics
        stats = calculate_statistics(data)
        print("\nSalary Statistics:")
        print(f"Count: {stats['count']}")
        print(f"Minimum: ${stats['min']:,}")
        print(f"Maximum: ${stats['max']:,}")
        print(f"Average: ${stats['average']:,}")
        print(f"Median: ${stats['median']:,}")
        
        # Calculate and display city statistics
        city_data = group_by_city(data)
        print("\nCity Statistics:")
        for city, stats in city_data.items():
            print(f"{city}: {stats['count']} employees, Average Salary: ${stats['average_salary']:,}")

if __name__ == "__main__":
    main() 