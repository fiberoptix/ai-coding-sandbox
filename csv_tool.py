# Import the csv module which provides functionality to read and write CSV files
import csv
# Import the statistics module which provides functions for calculating mathematical statistics
import statistics

# Define a function that reads a CSV file and returns its data
def read_csv_file(file_path):
    """Read CSV file and return its contents as a list of dictionaries."""
    # Create an empty list to store our data
    data = []
    # Start a try/except block for error handling
    # 'try' lets us attempt risky operations (like file operations) that might fail
    # If an error occurs in the try block, Python will jump to the 'except' block
    # instead of crashing the program
    try:
        # Open the file at file_path in read mode and assign it to variable csv_file
        with open(file_path, 'r') as csv_file:
            # Create a DictReader object that will read each row as a dictionary where column names are the keys
            csv_reader = csv.DictReader(csv_file)
            # Loop through each row in the CSV file
            for row in csv_reader:
                # Convert the SALARY value from a string to an integer so we can perform calculations
                row['SALARY'] = int(row['SALARY'])
                # Add the current row to our data list
                data.append(row)
        # Return the list of dictionaries when the function is done
        return data
    # Handle any errors that might occur when opening or reading the file
    except Exception as e:
        # Print an error message if something goes wrong
        print(f"Error reading CSV file: {e}")
        # Return None to indicate that the operation failed
        return None

# Define a function to calculate salary statistics from our data
def calculate_statistics(data):
    """Calculate salary statistics from the data."""
    # Check if data is empty or None, and return None if it is
    if not data:
        return None
    
    # Create a list containing only the salary values from each row
    salaries = [row['SALARY'] for row in data]
    
    # Create a dictionary to store our statistical results
    stats = {
        # Count how many salary entries we have
        'count': len(salaries),
        # Find the minimum salary
        'min': min(salaries),
        # Find the maximum salary
        'max': max(salaries),
        # Calculate the average salary and round to 2 decimal places
        'average': round(sum(salaries) / len(salaries), 2),
        # Calculate the median (middle value) of the salaries
        'median': statistics.median(salaries)
    }
    # Return the dictionary containing all the statistics
    return stats

# Define a function to group employees by city and calculate statistics per city
def group_by_city(data):
    """Group data by city and calculate average salary per city."""
    # Check if data is empty or None, and return None if it is
    if not data:
        return None
    
    # Create an empty dictionary to store information about each city
    city_data = {}
    # Loop through each employee's data
    for row in data:
        # Get the city name from the current row
        city = row['CITY']
        # If this is the first time we've seen this city, initialize its data structure
        if city not in city_data:
            city_data[city] = {'count': 0, 'total_salary': 0}
        
        # Increment the count of employees in this city
        city_data[city]['count'] += 1
        # Add this employee's salary to the city's total salary
        city_data[city]['total_salary'] += row['SALARY']
    
    # Calculate the average salary for each city
    for city in city_data:
        # Divide total salary by count of employees and round to 2 decimal places
        city_data[city]['average_salary'] = round(
            city_data[city]['total_salary'] / city_data[city]['count'], 2
        )
    
    # Return the dictionary with city statistics
    return city_data

# Define the main function that will run when the script is executed
def main():
    # Set the path to our CSV file
    file_path = 'employee_data.csv'
    # Call the read_csv_file function to load our data
    data = read_csv_file(file_path)
    
    # Check if we successfully loaded data
    if data:
        # Print a message confirming the number of records read
        print(f"Successfully read {len(data)} records from {file_path}")
        
        # Calculate overall salary statistics
        stats = calculate_statistics(data)
        # Print a header for the statistics section
        print("\nSalary Statistics:")
        # Print the count of employees
        print(f"Count: {stats['count']}")
        # Print the minimum salary, formatted with commas as thousand separators
        print(f"Minimum: ${stats['min']:,}")
        # Print the maximum salary, formatted with commas
        print(f"Maximum: ${stats['max']:,}")
        # Print the average salary, formatted with commas
        print(f"Average: ${stats['average']:,}")
        # Print the median salary, formatted with commas
        print(f"Median: ${stats['median']:,}")
        
        # Calculate statistics grouped by city
        city_data = group_by_city(data)
        # Print a header for the city statistics section
        print("\nCity Statistics:")
        # Loop through each city and its statistics
        for city, stats in city_data.items():
            # Print information about employee count and average salary for this city
            print(f"{city}: {stats['count']} employees, Average Salary: ${stats['average_salary']:,}")

# This is a special Python condition that checks if this script is being run directly
# (as opposed to being imported by another script)
if __name__ == "__main__":
    # If the script is run directly, call the main function
    main() 