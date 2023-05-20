import os

users_table = os.environ['USERS_NAME']
videos_table = os.environ['VIDEOS_NAME']


def retrieve_user_videos(client, chat_id):
    videos_resp = client.get_item(
        TableName=users_table,
        Key={
            'chat_id': {'N': str(chat_id)},
        },
        AttributesToGet=['videos']
    )
    if not videos_resp['Item']:
        videos_list = []
        return videos_list
    else:
        videos_list = videos_resp['Item']['videos']
        
    print(videos_list)
    user_videos = []
    for vid in videos_list['L']:
        vid_id = vid['S']
        vid_info_resp = client.get_item(
            TableName=videos_table,
            Key={
                'video_id': {'S': str(vid_id)},
            }
        )
        vid_info = {}
        for attr, val_dict in vid_info_resp['Item'].items():
            vid_info[attr] = list(val_dict.values())[0]
        user_videos.append(vid_info)
        
    return user_videos


def retrieve_user_openai_creds(client, chat_id):
    openai_key_resp = client.get_item(
        TableName=users_table,
        Key={
            'chat_id': {'N': str(chat_id)},
        },
        AttributesToGet=['openai_key']
    )
    if not openai_key_resp['Item']:
        return None
    else:
        return openai_key_resp['Item']['openai_key']['S']


def add_video_to_user(client, chat_id, video_id):
    """Adds video_id into videos list if it is not there yet."""
    videos_resp = client.get_item(
        TableName=users_table,
        Key={
            'chat_id': {'N': str(chat_id)},
        },
        AttributesToGet=['videos']
    )
    if not videos_resp['Item']:
        data = client.update_item(
            TableName=users_table,
            Key={
                'chat_id': {'N': str(chat_id)},
            },
            UpdateExpression = f"SET videos = :i",
            ExpressionAttributeValues={
                ':i': {'L': []},
            },
            ReturnValues="UPDATED_NEW"
        )
        print(data)

        videos_list = []
    else:
        videos_list = videos_resp['Item']['videos']

    if {'S': video_id} not in videos_list['L']:
        data = client.update_item(
            TableName=users_table,
            Key={
                'chat_id': {'N': str(chat_id)},
            },
            UpdateExpression="SET videos = list_append(videos, :i)",
            ExpressionAttributeValues={
                ':i': {'L': [{'S': video_id}]}
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
        print(key, value)
        data = client.update_item(
            TableName=videos_table,
            Key={
                'video_id': {'S': str(video_id)},
            },
            UpdateExpression = f"SET {key} = :i",
            ExpressionAttributeValues={
                ':i': {'S': str(value)},
            },
            ReturnValues="UPDATED_NEW"
        )
        print(data)

    return 1

