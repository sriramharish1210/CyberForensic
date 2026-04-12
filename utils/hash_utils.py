import hashlib

def generate_file_hash(file_path):
    sha256 = hashlib.sha256()

    with open(file_path, "rb") as f:
        while chunk := f.read(4096):
            sha256.update(chunk)

    return sha256.hexdigest()

def generate_log_hash(data_string):
    return hashlib.sha256(data_string.encode()).hexdigest()
