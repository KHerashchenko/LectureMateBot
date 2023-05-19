import json
import boto3
import telebot
import re
import openai
import asyncio
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
from youtube_video_handler import generate_transcript, retrieve_metadata
from user_creds_handler import encrypt_key, decrypt_key
from s3_storage_handler import upload_file_to_s3, download_file_from_s3
from dynamodb_handler import update_video_item, update_user_item, add_video_to_user, retrieve_user_openai_creds, retrieve_user_videos
from summary import generate_summary_pdf
from chat_utils import ask, upsert


tg_bot_token_secret_name = "TelegramBotToken"
openai_key_secret_name = "OpenAISecretKey"
region_name = "eu-north-1"
kms_key_id = 'da85dd30-85cc-4a75-986f-b62fefb4a55b'
youtube_video_id_regexp = "^.*(?:(?:youtu\.be\/|v\/|vi\/|u\/\w\/|embed\/|shorts\/)|(?:(?:watch)?\?v(?:i)?=|\&v(?:i)?=))([^#\&\?]*).*"

session = boto3.session.Session()  # create a session object
dynamodb_client = session.client('dynamodb')  # create a client for dynamodb
secrets_manager_client = session.client('secretsmanager')  # create a client for secrets manager
kms_client = boto3.client('kms')  # create a client for kms
s3_client = boto3.client('s3')  # create a client for s3

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
    
    if('message' in request_body_dict):
        message_type = 'message'
    elif('edited_message' in request_body_dict):
        message_type = 'edited_message'
    
    print(request_body_dict)
    try:
        update_user_item(dynamodb_client, chat_id=request_body_dict[message_type]['chat']['id'], username=request_body_dict[message_type]['chat']['username'])
    except:
        update_user_item(dynamodb_client, chat_id=request_body_dict[message_type]['chat']['id'])
    encrypted_openai_creds = retrieve_user_openai_creds(dynamodb_client, request_body_dict[message_type]['chat']['id'])
    
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

    try:
        file_path = download_file_from_s3(s3_client, video_id, f'transcript_{video_id}.txt')
        print(f'File transcript_{video_id}.txt found in bucket. Skip generating.')
    except Exception as e:
        print(e)
        print(f'No file transcript_{video_id}.txt found in bucket. Start generating.')
        transcript_result = generate_transcript(video_id)
        if not transcript_result:
            print(f"Transcript could not be retrieved from provided link.")
            return
        else:
            file_path = transcript_result
        upload_file_to_s3(s3_client, file_path, video_id)

    update_video_item(dynamodb_client, video_id=video_id, title=title, author=author, url_link=url)
    add_video_to_user(dynamodb_client, message.chat.id, video_id)

    doc = open(file_path, 'rb')
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

    try:
        pdf_path = download_file_from_s3(s3_client, video_id, f'summary_{video_id}.pdf')
        print(f'File summary_{video_id}.pdf found in bucket. Skip generating.')
    except Exception as e:
        print(f'No file summary_{video_id}.pdf found in bucket. Start generating.')
        try:
            file_path = download_file_from_s3(s3_client, video_id, f'transcript_{video_id}.txt')
        except Exception as e:
            print(e)
            print(f'No file transcript_{video_id}.txt found in bucket. Start generating.')
            transcript_result = generate_transcript(video_id)
            if not transcript_result:
                print(f"Transcript could not be retrieved from provided link.")
                return
            else:
                file_path = transcript_result
            upload_file_to_s3(s3_client, file_path, video_id)

        print('START PDF SUMMARY')
        bot.send_message(message.chat.id, f"Summarization may take some time, please bear with us.")
        with open(file_path, "r") as file:
            transcript = file.read()
        pdf_path = generate_summary_pdf(transcript, video_id)
        upload_file_to_s3(s3_client, pdf_path, video_id)

    update_video_item(dynamodb_client, video_id=video_id, title=title, author=author, url_link=url)
    add_video_to_user(dynamodb_client, message.chat.id, video_id)

    doc = open(pdf_path, 'rb')
    bot.send_document(message.chat.id, doc)


# Handle '/ask_question'
@bot.message_handler(commands=['ask_question'])
def ask_question(message):
    bot.reply_to(message, "What is your question from the lecture?")
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_question)


def process_question(message):
    try:
        loop_ask = asyncio.get_event_loop()
        response = loop_ask.run_until_complete(ask(message.text))
        bot.reply_to(message, response)
    except Exception as e:
        print(f"Couldn't connect to database.\nError: {e}")
        bot.reply_to(message, "You broke the bot.")
        return


# Handle '/upsert_text'
@bot.message_handler(commands=['upsert_text'])
def upsert_text(message):
    bot.reply_to(message, "What text do you want to upsert?")
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_text)


def process_text(message):
    try:
        loop_ask = asyncio.get_event_loop()
        response = loop_ask.run_until_complete(upsert(message.text.split()[0], message.text))
        bot.reply_to(message, "Text starting with: " + str(response) + " upserted")
    except Exception as e:
        print(f"Couldn't connect to database.\nError: {e}")
        bot.reply_to(message, "You broke the bot.")
        return


# Handle all other messages
@bot.message_handler(func=lambda message: not re.match(youtube_video_id_regexp, message.text), content_types=['text'])
def send_response_from_openapi(message):
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": message.text}])
    bot.reply_to(message, response.choices[0].message.content)
