import pyotp, qrcode, secrets, argparse, mysql.connector, sys, colorama, os
from colorama import Fore
from mysql.connector import Error

colorama.init()

def create_connection():
    connection = None
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='username',
            password='password',
            database='asmara'
        )
        print(Fore.YELLOW + "Connection to MariaDB successful" + Fore.WHITE)
    except Error as e:
        print(Fore.RED + f"The error '{e}' occurred" + Fore.WHITE)

    return connection


def initialize_database(connection):
    cursor = connection.cursor()
    # Create the asmara database if it doesn't exist
    cursor.execute("CREATE DATABASE IF NOT EXISTS asmara")
    # Select the asmara database
    cursor.execute("USE asmara")
    # Create the users table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50),
            password VARCHAR(50),
            secret VARCHAR(100)
        )
    """)
    connection.commit()
    print(Fore.GREEN + "Database and table initialized successfully." + Fore.WHITE)

def list_users(connection, show_pass):
    cursor = connection.cursor()
    query = "SELECT id, username, password FROM users"
    cursor.execute(query)
    result = cursor.fetchall()
    for row in result:
        id, username, password = row
        if show_pass:
            print(f"{id}/{username} Password:{password}")
        else:
            print(f"{id}/{username} Password:N/A")

    if not show_pass:
        print("Notice: Due to Security Reasons, Password is not shown unless passing --show-pass")        

def remove_user(connection, user_id=None, username=None):
    cursor = connection.cursor()
    if user_id:
        query = "DELETE FROM users WHERE id = %s"
        params = (user_id,)
    elif username:
        query = "DELETE FROM users WHERE username = %s"
        params = (username,)
    else:
        raise ValueError("Either user ID or username must be provided.")
    cursor.execute(query, params)
    affected_rows = cursor.rowcount
    connection.commit()
    if affected_rows >  0:
        print(Fore.GREEN + f"User {'with ID/Username ' + str(user_id) if user_id else 'named ' + username} removed successfully from users table." + Fore.WHITE)
    else:
        print(Fore.RED + f"No user found with {'ID ' + str(user_id) if user_id else 'username ' + username}." + Fore.WHITE)

def make2fa(username):
    # Generate a secret key
    secret = pyotp.random_base32()

    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name="ASMARA", issuer_name="MSNGTXTURES")

    # Generate a QR code from the TOTP URI
    qr_img = qrcode.make(totp_uri)

    # Ensure the qrcodes directory exists
    qr_dir = "qrcodes"
    if not os.path.exists(qr_dir):
        print(Fore.YELLOW + "qrcodes folder does not exist! Making.." + Fore.WHITE)
        os.makedirs(qr_dir)

    # Save the QR code
    qr_img.save(f"{qr_dir}/totp_qrcode-{username}.png")
    print(Fore.GREEN + "2FA Successfully Generated" + Fore.WHITE)

    return secret

def insert_user(connection, username, password):
    secret = secrets.token_hex(16)  # Generate a random secret
    cursor = connection.cursor()
    secret = make2fa(username)
    query = """INSERT INTO users (username, password, secret) VALUES (%s, %s, %s)"""
    cursor.execute(query, (username, password, secret))
    connection.commit()
    print(Fore.GREEN + f"User {username} inserted successfully into users table with generated secret." + Fore.WHITE)

def close_connection(connection):
    if connection.is_connected():
        cursor = connection.cursor()
        cursor.close()
        connection.close()
        print(Fore.YELLOW + "MySQL connection is closed" + Fore.WHITE)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Manage users in the database.')
    subparsers = parser.add_subparsers(dest='command')

    # Subcommand for inserting a user
    insert_parser = subparsers.add_parser('add', help='Insert a new user into the database.')
    insert_parser.add_argument('-u', '--username', required=True, help='Username to insert.')
    insert_parser.add_argument('-p', '--password', required=True, help='Password to insert.')

    # Subcommand for removing a user
    remove_parser = subparsers.add_parser('del', help='Remove a user from the database by ID or username.')
    remove_parser.add_argument('-i', '--id', type=int, help='ID of the user to remove.')
    remove_parser.add_argument('-u', '--username', help='Username of the user to remove.')

    # Subcommand for listing users..
    list_users_parser = subparsers.add_parser('list', help='List all users in the database.')
    list_users_parser.add_argument('--show-pass', action='store_true', help='Show passwords for listed users.')

    init_parser = subparsers.add_parser('init', help='Initialize the database and create the users table.')

    args = parser.parse_args()

    # Check if any arguments were provided
    if len(sys.argv) <=  1:
        parser.print_help()
        sys.exit(1)

    connection = create_connection()

    if args.command == 'add':
        insert_user(connection, args.username, args.password)
    elif args.command == 'del':
        if args.id:
            remove_user(connection, user_id=args.id)
        elif args.username:
            remove_user(connection, username=args.username)
        else:
            print(Fore.RED + "Please provide either a user ID or a username." + Fore.WHITE)
    elif args.command == 'list':
        list_users(connection, args.show_pass)
    elif args.command == 'init':
        initialize_database(connection)

    close_connection(connection)