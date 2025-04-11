from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
import os

def generate_dek():
    return os.urandom(32)
def encrypt_dek(plaintext_dek, alias, context=None):
    encrypted_dek = plaintext_dek
    return encrypted_dek
    # kms = boto3.client('kms')
    # encrypted = kms.encrypt(
    #     KeyId=alias,
    #     Plaintext=decrypted.encode(),
    #     EncryptionContext=context or {}
    # )["CiphertextBlob"]
    # return encrypted
def encrypt_data(plaintext_dek, data):
    iv = os.urandom(12)
    encryptor = Cipher(algorithms.AES(plaintext_dek), modes.GCM(iv)).encryptor()
    ciphertext = encryptor.update(data) + encryptor.finalize()
    data_blob = iv + encryptor.tag + ciphertext
    return data_blob
def encrypt(model_instance, value, field_name, dek_field_name,
            context_fields=[], alias=None):
    # import pdb
    # breakpoint()
    dek = generate_dek()
    data_blob = encrypt_data(dek, value)
    model_instance.__dict__[f"_{field_name}"] = data_blob
    encrypted_dek = encrypt_dek(dek, alias)
    model_instance.__dict__[dek_field_name] = encrypted_dek

def parse_data_blob(data_blob):
    iv = data_blob[:12]
    tag = data_blob[12:28]
    data_ciphertext = data_blob[28:]
    return iv, tag, data_ciphertext
def decrypt_dek(encrypted_dek, context=None):
    decrypted_dek = encrypted_dek
    return decrypted_dek
    # kms = boto3.client('kms')
    # return kms.decrypt(
    #     CiphertextBlob=encrypted,
    #     EncryptionContext=context or {}
    # )["Plaintext"].decode()
def decrypt_data(dek, iv, tag, data_ciphertext):
    decryptor = Cipher(algorithms.AES(dek), modes.GCM(iv, tag)).decryptor()
    data = decryptor.update(data_ciphertext) + decryptor.finalize()
    return data
def decrypt(model_instance, field_name, dek_field_name, 
            context_fields=[], alias=None):
    # import pdb
    # breakpoint()
    data_blob = model_instance.__dict__[f"_{field_name}"]
    iv, tag, data_ciphertext = parse_data_blob(data_blob)
    dek = decrypt_dek(model_instance[dek_field_name])
    data = decrypt_data(dek, iv, tag, data_ciphertext)
    return data.decode("utf-8")





