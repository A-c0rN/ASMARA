import pyotp, qrcode, secrets, argparse, mysql.connector, sys, colorama, os
from datetime import datetime, timedelta
from mysql.connector import Error

from cryptography import x509
from cryptography.x509.oid import NameOID
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import Encoding
from cryptography.hazmat.primitives.serialization import PrivateFormat
from cryptography.hazmat.primitives.serialization import NoEncryption


USEQUERY = "USE asmara;"


def makeSSL():
    key_file = "ssl_key.key"
    cert_file = "ssl_cert.pem"
    cert_dir = "."

# Check if the key and certificate files exist
    if not os.path.exists(os.path.join(cert_dir, key_file)) or not os.path.exists(os.path.join(cert_dir, cert_file)):
        # Generate a new private key
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
        )

        # Define custom names for issuer and subject
        issuer_name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, u"ASMARA Endec"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"MSNGTXTRS SOFT."),
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        ])

        subject_name = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, u"ASMARA Endec"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"MSNGTXTRS SOFT."),
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"US"),
        ])

        # Generate a self-signed certificate
        cert = x509.CertificateBuilder().subject_name(
            subject_name
        ).issuer_name(
            issuer_name
        ).public_key(
            private_key.public_key()
        ).serial_number(
            x509.random_serial_number()
        ).not_valid_before(
            datetime.utcnow()
        ).not_valid_after(
            datetime.utcnow() + timedelta(days=365)
        ).add_extension(
            x509.SubjectAlternativeName([x509.DNSName(u"localhost")]),
            critical=False,
        # Sign the certificate with the private key
        ).sign(private_key, hashes.SHA256())


        # Save the private key
        with open(os.path.join(cert_dir, key_file), "wb") as f:
            f.write(private_key.private_bytes(
                encoding=Encoding.PEM,
                format=PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=NoEncryption()
            ))

        # Save the certificate
        with open(os.path.join(cert_dir, cert_file), "wb") as f:
            f.write(cert.public_bytes(Encoding.PEM))


        print("SSL key and certificate generated.")
    else:
        print("SSL key and certificate already exist.")

def create_connection():
    connection = None
    try:
        connection = mysql.connector.connect(
            host='localhost',
            user='username',
            password='password'
        )
        print("Connection to MariaDB successful")
    except Error as e:
        print(f"The error '{e}' occurred")

    return connection


def initialize_database(connection):
    cursor = connection.cursor()
    # Create the asmara database if it doesn't exist
    cursor.execute("CREATE DATABASE IF NOT EXISTS asmara")
    # Select the asmara database
    cursor.execute(USEQUERY)
    # Create the users table if it doesn't exist
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INT AUTO_INCREMENT PRIMARY KEY,
            username VARCHAR(50),
            password VARCHAR(50),
            secret VARCHAR(100),
            sudo BOOLEAN DEFAULT FALSE
        );
    """)
    cursor.execute("""
                      CREATE TABLE request (
       reindex INT AUTO_INCREMENT PRIMARY KEY,
       response_time FLOAT,
       date DATETIME,
       method VARCHAR(255),
       size INT,
       status_code INT,
       path VARCHAR(255),
       user_agent VARCHAR(255),
       remote_address VARCHAR(255),
       exception VARCHAR(255),
       referrer VARCHAR(255),
       browser VARCHAR(255),
       platform VARCHAR(255),
       mimetype VARCHAR(255)
   );""")
    connection.commit()
    print("Database and table initialized successfully.")

def list_users(connection, show_pass):
    cursor = connection.cursor()
    query = "SELECT id, username, password FROM users"
    cursor.execute(USEQUERY)
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
    cursor.execute(USEQUERY)
    cursor.execute(query, params)
    affected_rows = cursor.rowcount
    connection.commit()
    if affected_rows >  0:
        print(f"User {'with ID/Username ' + str(user_id) if user_id else 'named ' + username} removed successfully from users table.")
    else:
        print(f"No user found with {'ID ' + str(user_id) if user_id else 'username ' + username}.")

def make2fa(username):
    # Generate a secret key
    secret = pyotp.random_base32()

    totp_uri = pyotp.totp.TOTP(secret).provisioning_uri(name="ASMARA", issuer_name="MSNGTXTURES")

    # Generate a QR code from the TOTP URI
    qr_img = qrcode.make(totp_uri)

    # Ensure the qrcodes directory exists
    qr_dir = "qrcodes"
    if not os.path.exists(qr_dir):
        print("qrcodes folder does not exist! Making..")
        os.makedirs(qr_dir)

    # Save the QR code
    qr_img.save(f"{qr_dir}/totp_qrcode-{username}.png")
    print("2FA Successfully Generated")

    return secret

def insert_user(connection, username, password):
    secret = secrets.token_hex(16)  # Generate a random secret
    cursor = connection.cursor()
    secret = make2fa(username)
    cursor.execute(USEQUERY)
    query = """INSERT INTO users (username, password, secret) VALUES (%s, %s, %s)"""
    cursor.execute(query, (username, password, secret))
    connection.commit()
    print(f"User {username} inserted successfully into users table with generated secret.")

def close_connection(connection):
    if connection.is_connected():
        cursor = connection.cursor()
        cursor.close()
        connection.close()
        print("MySQL connection is closed")

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

    mkSSL_parser = subparsers.add_parser('mkSSL', help='Create The Files needed to run in HTTPS/SSL mode')

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
            print("Please provide either a user ID or a username.")
    elif args.command == 'list':
        list_users(connection, args.show_pass)
    elif args.command == 'init':
        initialize_database(connection)
    elif args.command == 'mkSSL':
        makeSSL()

    close_connection(connection)