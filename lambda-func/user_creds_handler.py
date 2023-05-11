import base64


def encrypt_key(client, key_id, provided_key):
    # Encrypt the password with the KMS key
    response = client.encrypt(KeyId=key_id, Plaintext=provided_key)

    # Encode the encrypted password as a base64 string
    encrypted_password_b64 = base64.b64encode(response['CiphertextBlob'])
    return encrypted_password_b64.decode('utf-8')


def decrypt_key(client, key_id, retrieved_key_64):
    # Decode the encrypted password from base64
    retrieved_key = base64.b64decode(retrieved_key_64)

    # Decrypt the password using the KMS key ID and the encrypted password
    decrypted_password = client.decrypt(CiphertextBlob=retrieved_key, KeyId=key_id)['Plaintext']

    # Convert the decrypted password from bytes to a string
    return decrypted_password.decode('utf-8')
