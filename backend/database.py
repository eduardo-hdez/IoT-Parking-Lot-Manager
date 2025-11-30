import mysql.connector
from mysql.connector import Error
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

DB_CONFIG = {
    'host': os.getenv('DB_HOST'),
    'port': os.getenv('DB_PORT'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD'),
    'database': os.getenv('DB_NAME')
}

def get_db_connection():
    """
    Create and return a MySQL database connection.
    Returns None if connection fails.
    """
    try:
        connection = mysql.connector.connect(**DB_CONFIG)
        if connection.is_connected():
            return connection
    except Error as error:
        print(f"Error connecting to MySQL: {error}")
        return None


def init_parking_spaces():
    """
    Initialize parking space records in the database if they don't exist.
    Creates records for spaces A1-A8 linked to section SEC-A.
    """
    connection = get_db_connection()

    if not connection:
        print("Failed to initialize parking spaces - no database connection")
        return False
    
    try:
        cursor = connection.cursor()
        
        # Define the parking spaces for section A
        parking_spaces = ['A1', 'A2', 'A3', 'A4', 'A5', 'A6', 'A7', 'A8']
        section_id = 'SEC-A'
        
        for space_code in parking_spaces:
            parking_space_id = f'PS-{space_code}'
            
            # Check if the parking space already exists
            check_query = """
                SELECT ParkingSpaceID FROM parkingspace 
                WHERE ParkingSpaceID = %s
            """
            cursor.execute(check_query, (parking_space_id,))
            existing = cursor.fetchone()
            
            if not existing:
                # Insert new parking space record (only current state)
                insert_query = """
                    INSERT INTO parkingspace 
                    (ParkingSpaceID, SectionID, SpaceCode, Status, CurrentOccupancyID)
                    VALUES (%s, %s, %s, %s, NULL)
                """
                cursor.execute(insert_query, (parking_space_id, section_id, space_code, 'available'))
                print(f"Created parking space: {space_code}")
            else:
                print(f"Parking space {space_code} already exists")
        
        connection.commit()
        print(f"Initialized {len(parking_spaces)} parking spaces")
        return True
        
    except Error as error:
        print(f"Error initializing parking spaces: {error}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()


def insert_parking_event(space_code, new_status, previous_status, is_car=None):
    """
    Insert a new parking event record when status changes.
    Updates ParkingSpace table with current status and inserts into OccupancyHistory.
    """
    connection = get_db_connection()
    
    if not connection:
        print(f"Failed to insert event for {space_code} - NO database connection")
        return False
    
    try:
        cursor = connection.cursor()
        current_time = datetime.now()
        parking_space_id = f"PS-{space_code}"
        
        # Handle different status transitions
        if previous_status == 'available' and new_status in ['occupied', 'obstacle']:
            # Vehicle/object entering: Create new occupancy record
            timestamp_str = current_time.strftime('%Y%m%d%H%M%S%f')
            occupancy_id = f"OCC-{space_code}-{timestamp_str}"
            
            # Insert into OccupancyHistory with TimeOfEntry
            insert_history_query = """
                INSERT INTO occupancyhistory 
                (OccupancyID, ParkingSpaceID, TimeOfEntry, TimeOfDeparture, CheckIfObjectIsCar, DurationMinutes)
                VALUES (%s, %s, %s, NULL, %s, NULL)
            """
            cursor.execute(insert_history_query, (occupancy_id, parking_space_id, current_time, is_car))
            
            # Update ParkingSpace with new status and current occupancy
            update_space_query = """
                UPDATE parkingspace 
                SET Status = %s, CurrentOccupancyID = %s
                WHERE ParkingSpaceID = %s
            """
            cursor.execute(update_space_query, (new_status, occupancy_id, parking_space_id))
            
            print(f"DB Event: {space_code} {previous_status}→{new_status} (Entry: {current_time.strftime('%H:%M:%S')})")
            
        elif previous_status in ['occupied', 'obstacle'] and new_status == 'available':
            # Vehicle/object leaving: Update existing occupancy record
            
            # Get current occupancy ID
            get_occupancy_query = """
                SELECT CurrentOccupancyID FROM parkingspace 
                WHERE ParkingSpaceID = %s
            """
            cursor.execute(get_occupancy_query, (parking_space_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                current_occupancy_id = result[0]
                
                # Get entry time to calculate duration
                get_entry_query = """
                    SELECT TimeOfEntry FROM occupancyhistory 
                    WHERE OccupancyID = %s
                """
                cursor.execute(get_entry_query, (current_occupancy_id,))
                entry_result = cursor.fetchone()
                
                duration_minutes = None
                if entry_result and entry_result[0]:
                    entry_time = entry_result[0]
                    duration = current_time - entry_time
                    duration_minutes = int(duration.total_seconds() / 60)
                
                # Update OccupancyHistory with departure time and duration
                update_history_query = """
                    UPDATE occupancyhistory 
                    SET TimeOfDeparture = %s, DurationMinutes = %s
                    WHERE OccupancyID = %s
                """
                cursor.execute(update_history_query, (current_time, duration_minutes, current_occupancy_id))
                
                print(f"DB Event: {space_code} {previous_status}→{new_status} (Departure: {current_time.strftime('%H:%M:%S')}, Duration: {duration_minutes}min)")
            
            # Update ParkingSpace to available and clear current occupancy
            update_space_query = """
                UPDATE parkingspace 
                SET Status = %s, CurrentOccupancyID = NULL
                WHERE ParkingSpaceID = %s
            """
            cursor.execute(update_space_query, (new_status, parking_space_id))
            
        else:
            # Status change without entry/departure (e.g., occupied → obstacle)
            # Just update the status
            update_space_query = """
                UPDATE parkingspace 
                SET Status = %s
                WHERE ParkingSpaceID = %s
            """
            cursor.execute(update_space_query, (new_status, parking_space_id))
            
            print(f"DB Event: {space_code} {previous_status}→{new_status}")
        
        connection.commit()
        return True
        
    except Error as error:
        print(f"Error inserting parking event for {space_code}: {error}")
        return False
    finally:
        if connection.is_connected():
            cursor.close()
            connection.close()