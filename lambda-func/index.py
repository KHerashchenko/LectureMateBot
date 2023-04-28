import json

import boto3
import telebot
import re
import openai
import botocore.session
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
from youtube_video_handler import generate_transcript, retrieve_metadata
from summary import summarize

tg_bot_token_secret_name = "TelegramBotToken"
openai_key_secret_name = "OpenAISecretKey"
region_name = "eu-north-1"
youtube_video_id_regexp = "^.*(?:(?:youtu\.be\/|v\/|vi\/|u\/\w\/|embed\/|shorts\/)|(?:(?:watch)?\?v(?:i)?=|\&v(?:i)?=))([^#\&\?]*).*"

session = boto3.session.Session()  # create a session object
dynamodb_client = session.client('dynamodb')  # create a client for dynamodb
secrets_manager_client = session.client('secretsmanager')  # create a client for secrets manager

cache_config = SecretCacheConfig()
cache = SecretCache(config=cache_config, client=secrets_manager_client)

tg_bot_secret = cache.get_secret_string(tg_bot_token_secret_name)
bot = telebot.TeleBot(tg_bot_secret, threaded=False)

openai.api_key = cache.get_secret_string(openai_key_secret_name)


def process_event(event):
    # Get telegram webhook json from event
    request_body_dict = json.loads(event['body'])
    # Parse updates from json
    update = telebot.types.Update.de_json(request_body_dict)
    # Run handlers and etc for updates
    bot.process_new_updates([update])


def handler(event, context):
    data = dynamodb_client.put_item(
        TableName='UsersTable',
        Item={
            'chat_id': {
                'N': '001'
            },
            'video_id': {
                'S': 'FE87YF8'
            },
            'username': {
                'S': 'my_user'
            }
        }
    )

    # Process event from aws and respond
    process_event(event)
    return {
        'statusCode': 200
    }


# Handle '/start' and '/help'
@bot.message_handler(commands=['help', 'start'])
def send_welcome(message):
    bot.reply_to(message,
                 ("Hi there, I am OpenAI bot.\n"
                  "I am here to burn your free tier credits."))


# Handle '/get_transcript'
@bot.message_handler(commands=['get_transcript'])
def send_transcript(message):
    bot.reply_to(message, "Please provide youtube video link for transcription.")
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_youtube_video_link)


# Handle '/summarize_video'
@bot.message_handler(commands=['summarize_video'])
def send_summarization(message):
    bot.reply_to(message, "Please provide youtube video link for summarization.")
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_summarization)


# Handle all other messages
@bot.message_handler(func=lambda message: True, content_types=['text'])
def send_response_from_openapi(message):
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": message.text}])
    bot.reply_to(message, response.choices[0].message.content)


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

    bot.send_message(message.chat.id, f"Title: {title}\nAuthor: {author}\nVideo summary:")
    bot.send_message(message.chat.id, summarization)


def process_youtube_video_link(message):
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

    doc = open(filename, 'rb')
    bot.send_message(message.chat.id, f"Title: {title}\nAuthor: {author}\nVideo transcript:")
    bot.send_document(message.chat.id, doc)
