import json

import boto3
import telebot
import re
import openai
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
from youtube_video_handler import generate_transcript, retrieve_metadata
from user_creds_handler import encrypt_key, decrypt_key
from dynamodb_handler import update_video_item, update_user_item, add_video_to_user, retrieve_user_openai_creds, retrieve_user_videos
from summary import summarize

tg_bot_token_secret_name = "TelegramBotToken"
openai_key_secret_name = "OpenAISecretKey"
region_name = "eu-north-1"
kms_key_id = 'da85dd30-85cc-4a75-986f-b62fefb4a55b'
youtube_video_id_regexp = "^.*(?:(?:youtu\.be\/|v\/|vi\/|u\/\w\/|embed\/|shorts\/)|(?:(?:watch)?\?v(?:i)?=|\&v(?:i)?=))([^#\&\?]*).*"

session = boto3.session.Session()  # create a session object
dynamodb_client = session.client('dynamodb')  # create a client for dynamodb
secrets_manager_client = session.client('secretsmanager')  # create a client for secrets manager
kms_client = boto3.client('kms')  # create a client for kms

cache_config = SecretCacheConfig()
cache = SecretCache(config=cache_config, client=secrets_manager_client)

tg_bot_secret = cache.get_secret_string(tg_bot_token_secret_name)
default_openai_key = cache.get_secret_string(openai_key_secret_name)

bot = telebot.TeleBot(tg_bot_secret, threaded=False)


def process_event(event):
    # Get telegram webhook json from event
    request_body_dict = json.loads(event['body'])
    # Parse updates from json
    update = telebot.types.Update.de_json(request_body_dict)
    update_user_item(dynamodb_client, chat_id=request_body_dict['message']['chat']['id'], username=request_body_dict['message']['chat']['username'])
    encrypted_openai_creds = retrieve_user_openai_creds(dynamodb_client, request_body_dict['message']['chat']['id'])
    if encrypted_openai_creds:
        openai_creds = decrypt_key(kms_client, kms_key_id, encrypted_openai_creds)
    else:
        openai_creds = default_openai_key
    openai.api_key = openai_creds

    # Run handlers and etc for updates
    bot.process_new_updates([update])


def handler(event, context):
    # Process event from aws and respond
    process_event(event)
    return {
        'statusCode': 200
    }


# Handle '/start' and '/help'
@bot.message_handler(commands=['help', 'start'])
def send_welcome(message):
    bot.reply_to(message,
                 ("Hi there, I am LectureMate bot.\n"
                  "Please provide your OpenAI key, otherwise we will go broke."))

# Handle '/list_my_videos'
@bot.message_handler(commands=['list_my_videos'])
def send_welcome(message):
    user_videos = retrieve_user_videos(dynamodb_client, message.chat.id)
    if not user_videos:
        bot.reply_to(message, "You haven't requested any video yet.")
    else:
        rendered_user_videos = 'List of videos you have provided earlier:\n'
        for ind, vid_dict in enumerate(user_videos):
            rendered_user_videos += str(ind + 1) + '. '
            for k, v in vid_dict.items():
                rendered_user_videos += f"{k}: {v}\n"
        bot.reply_to(message, rendered_user_videos)


# Handle '/provide_openai_key'
@bot.message_handler(commands=['provide_openai_key'])
def provide_openai_key(message):
    bot.reply_to(message, "Please provide your OpenAI key.")
    bot.register_next_step_handler_by_chat_id(message.chat.id, register_openai_user_key)


def register_openai_user_key(message):
    try:
        openai.api_key = message.text
        models = openai.Model.list()
    except openai.error.AuthenticationError:
        bot.reply_to(message, "Provided OpenAI key is invalid.")
        return

    encrypted_openai_key = encrypt_key(kms_client, kms_key_id, message.text)
    update_user_item(dynamodb_client, chat_id=message.chat.id, openai_key=encrypted_openai_key)
    bot.reply_to(message, "Your OpenAI key saved.")


# Handle '/get_transcript'
@bot.message_handler(commands=['get_transcript'])
def get_transcript(message):
    bot.reply_to(message, "Please provide youtube video link for transcription.")
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_transcript)


def process_transcript(message):
    url = message.text
    try:
        video_id = re.findall(youtube_video_id_regexp, url)[0]
    except Exception as e:
        bot.reply_to(message, f"Youtube video link could not be processed.\nError: {e}")
        return

    title, author = retrieve_metadata(video_id)
    transcript_result = generate_transcript(video_id)
    if not transcript_result:
        bot.send_message(message.chat.id, f"Transcript could not be retrieved from provided link.")
        return
    else:
        transcript, no_of_words, filename = transcript_result

    update_video_item(dynamodb_client, video_id=video_id, title=title, author=author, url_link=url)
    add_video_to_user(dynamodb_client, message.chat.id, video_id)

    doc = open(filename, 'rb')
    bot.send_message(message.chat.id, f"Title: {title}\nAuthor: {author}\nVideo transcript:")
    bot.send_document(message.chat.id, doc)


# Handle '/summarize_video'
@bot.message_handler(commands=['summarize_video'])
def summarize_video(message):
    bot.reply_to(message, "Please provide youtube video link for summarization.")
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_summarization)


def process_summarization(message):
    url = message.text
    try:
        video_id = re.findall(youtube_video_id_regexp, url)[0]
    except Exception as e:
        bot.reply_to(message, f"Youtube video link could not be processed.\nError: {e}")
        return

    title, author = retrieve_metadata(video_id)

    transcript_result = generate_transcript(video_id)
    if not transcript_result:
        bot.send_message(message.chat.id, f"Transcript could not be retrieved from provided link.")
        return
    else:
        transcript, no_of_words, filename = transcript_result

    try:
        summarization = summarize(transcript)
    except Exception as e:
        bot.send_message(message.chat.id, f"Summary could not be generated for given transcript.\nError:{e}")
        return

    update_video_item(dynamodb_client, video_id=video_id, title=title, author=author, url_link=url)
    add_video_to_user(message.chat.id, video_id)

    bot.send_message(message.chat.id, f"Title: {title}\nAuthor: {author}\nVideo summary:")
    bot.send_message(message.chat.id, summarization)


# Handle all other messages
@bot.message_handler(func=lambda message: True, content_types=['text'])
def send_response_from_openapi(message):
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": message.text}])
    bot.reply_to(message, response.choices[0].message.content)
