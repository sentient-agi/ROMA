
def connect_to_aws():
    # Hardcoded credentials - BAD!
    aws_access_key = "AKIA1234567890" 
    aws_secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    region = "us-east-1"
    print(f"Connecting to {region} with {aws_access_key}")

def db_config():
    # Another secret
    db_password = "super_secret_db_password_!"
    return db_password
