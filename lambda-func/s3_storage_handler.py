import os

bucket_name = os.environ['BUCKET_NAME']


def upload_file_to_s3(client, file_path, item_id, folder):

    key = f'{folder}/{item_id}/{file_path.split("/")[-1]}'  # Construct the key with the video_id folder
    client.upload_file(file_path, bucket_name, key)
    print(f'The file {file_path} was uploaded to s3 bucket: {key}')


def download_file_from_s3(client, item_id, file_name, folder):
    destination_path = f'/tmp/{file_name}'
    key = f'{folder}/{item_id}/{file_name}'  # Construct the key with the video_id folder
    client.download_file(bucket_name, key, destination_path)
    print(f'The file {key} was downloaded to path: {destination_path}')

    return destination_path

