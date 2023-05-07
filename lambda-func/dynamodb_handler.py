import os

users_table = os.environ['USERS_NAME']
videos_table = os.environ['VIDEOS_NAME']

def add_video_to_user(client, chat_id, video_id):
    """Adds video_id into videos list if it is not there yet."""
    videos_list = client.get_item(
        TableName=users_table,
        Key={
            'chat_id': chat_id,
        },
        AttributesToGet=['videos']
    )['videos']

    if video_id not in videos_list:
        data = client.update_item(
            TableName=users_table,
            Key={
                'chat_id': {'N': str(chat_id)},
            },
            UpdateExpression="SET videos = list_append(videos, :i)",
            ExpressionAttributeValues={
                ':i': [video_id],
            },
            ReturnValues="UPDATED_NEW"
        )
        print(data)

    return 1


def update_user_item(client, chat_id, **kwargs):
    for key, value in kwargs.items():
        data = client.update_item(
            TableName=users_table,
            Key={
                'chat_id': {'N': str(chat_id)},
            },
            UpdateExpression = f"SET {key} = :i",
            ExpressionAttributeValues={
                ':i': {'S': str(value)},
            },
            ReturnValues="UPDATED_NEW"
        )
        print(data)

    return 1


def update_video_item(client, video_id, **kwargs):
    for key, value in kwargs.items():
        data = client.update_item(
            TableName=videos_table,
            Key={
                'video_id': {'N': str(video_id)},
            },
            UpdateExpression = f"SET {key} = :i",
            ExpressionAttributeValues={
                ':i': {'S': str(value)},
            },
            ReturnValues="UPDATED_NEW"
        )
        print(data)

    return 1
