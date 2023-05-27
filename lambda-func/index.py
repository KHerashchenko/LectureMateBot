import json
import boto3
import telebot
from telebot import types, formatting
import re
import openai
import asyncio
import os
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
from youtube_video_handler import generate_transcript, retrieve_metadata
from user_creds_handler import encrypt_key, decrypt_key
from s3_storage_handler import upload_file_to_s3, download_file_from_s3
from dynamodb_handler import update_video_item, update_user_item, add_video_to_user, retrieve_user_openai_creds, retrieve_user_videos, add_note_to_user, retrieve_user_notes
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
    
    message_type = None
    if('message' in request_body_dict):
        message_type = 'message'
    elif('edited_message' in request_body_dict):
        message_type = 'edited_message'

    print(request_body_dict)
    try:
        if message_type == None:
            return
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
    print(event)
    # Process event from aws and respond
    process_event(event)

    return {
        'statusCode': 200
    }


# Handle '/start'
@bot.message_handler(commands=['start'])
def send_welcome(message):
    start_message = """
Hi there! I'm LectureMate, your helpful bot.

🔑 Please provide your OpenAI key, otherwise we will go broke.

You can transcribe, summarize, and chat about YouTube videos here. You have your own library of videos. First, you should provide a YouTube video link to add a video to your library using the /add_video command.

Once you have a video in the library, you can request the video transcript, summary, or ask questions about the video content.

Use the /help command to get a list of all available commands and their descriptions.

Let's get started! If you have any questions, feel free to ask.
"""
    bot.reply_to(message, start_message)


# Handle '/help'
@bot.message_handler(commands=['help'])
def send_help(message):
    help_message = """
Hi there! I'm LectureMate, your helpful bot. Here's how you can make the most out of me:

📚 Library Commands:
- /add_video: Add a YouTube video to your library.
- /add_note: Add a Note to your library.
- /show_my_library: View the list of videos in your library.
- /show_my_notes: View the list of notes in your library.

🎥 Video Commands:
- /get_summary: Get a summary of a video from your library.
- /get_transcript: Get the transcript of a video from your library.
- /get_note: Get the note from your library.

💬 Chat Commands:
- /start_chat: Start a conversation about the content of a video from your library.

🔧 Utility Commands:
- /provide_openai_key: Provide your own OpenAI key.
- /help: Read the bot guide.
- /exit: Exit the current command.

Please note that some commands require you to have videos in your library. To add a video, use the /add_video command.

Enjoy using LectureMate! If you have any questions, feel free to ask.
"""
    bot.reply_to(message, help_message)


def return_videos_list_keyboard(message, next_step_func):
    user_videos = retrieve_user_videos(dynamodb_client, message.chat.id)
    if not user_videos:
        bot.reply_to(message, "You haven't added any video yet. Please call /add_video first.")
        return

    markup = types.ReplyKeyboardMarkup()
    for ind, vid_dict in reversed(list(enumerate(user_videos))):
        video_info = f"\"{vid_dict['title']}\" by {vid_dict['author']} ({vid_dict['video_id']})"
        itembtn = types.KeyboardButton(video_info)
        markup.row(itembtn)
    bot.send_message(message.chat.id, "List of your videos:", reply_markup=markup)
    # Set the next step handler to handle the user's selection
    bot.register_next_step_handler_by_chat_id(message.chat.id, next_step_func)


def return_notes_list_keyboard(message, next_step_func):
    user_notes = retrieve_user_notes(dynamodb_client, message.chat.id)
    if not user_notes:
        bot.reply_to(message, "You haven't added any note yet. Please call /add_note first.")
        return

    markup = types.ReplyKeyboardMarkup()
    for note in user_notes:
        itembtn = types.KeyboardButton(note)
        markup.row(itembtn)
    bot.send_message(message.chat.id, "List of your notes:", reply_markup=markup)
    # Set the next step handler to handle the user's selection
    bot.register_next_step_handler_by_chat_id(message.chat.id, next_step_func)

# Handle '/show_my_library'
@bot.message_handler(commands=['show_my_library'])
def send_list_my_videos(message):
    user_videos = retrieve_user_videos(dynamodb_client, message.chat.id)
    if not user_videos:
        bot.reply_to(message, "You haven't requested any video yet.")
    else:
        rendered_user_videos = '*List of videos you have provided earlier:*\n\n'
        for ind, vid_dict in reversed(list(enumerate(user_videos))):
            title = formatting.escape_markdown(vid_dict['title'])
            author = formatting.escape_markdown(vid_dict['author'])
            video_info = f"[URL]({vid_dict['url_link']}) \"{title}\" by {author}\n"
            rendered_user_videos += video_info
        bot.send_message(message.chat.id, rendered_user_videos, parse_mode='MarkdownV2')


# Handle '/show_my_notes'
@bot.message_handler(commands=['show_my_notes'])
def send_list_my_notes(message):
    user_notes = retrieve_user_notes(dynamodb_client, message.chat.id)
    if not user_notes:
        bot.reply_to(message, "You haven't uploaded any note yet.")
    else:
        rendered_user_notes = "*List of notes you have provided earlier:*\n\n"
        for note in user_notes:
            note_esc = formatting.escape_markdown(note)
            note_info = f"  `- {note_esc}\n`"
            rendered_user_notes += note_info
        bot.send_message(message.chat.id, rendered_user_notes, parse_mode='MarkdownV2')


# Handle '/add_video'
@bot.message_handler(commands=['add_video'])
def provide_openai_key(message):
    bot.reply_to(message, "Please provide youtube video link.")
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_add_video)


def process_add_video(message):
    if message.text == "/exit":
        bot.reply_to(message, "You exited the current process, start a new one.")
        return
    url = message.text
    try:
        video_id = re.findall(youtube_video_id_regexp, url)[0]
    except Exception as e:
        bot.reply_to(message, f"Youtube video link could not be processed.\nError: {e}")
        return

    title, author = retrieve_metadata(video_id)

    update_video_item(dynamodb_client, video_id=video_id, title=title, author=author, url_link=url)
    add_video_to_user(dynamodb_client, message.chat.id, video_id)

    file_path = generate_transcript(video_id)
    with open(file_path, "r") as file:
        transcript = file.read()

    try:
        loop_ask = asyncio.get_event_loop()
        response = loop_ask.run_until_complete(upsert(video_id, transcript))
    except Exception as e:
        print(f"Couldn't connect to database.\nError: {e}")
        bot.reply_to(message, "You broke the bot.")
        return

    bot.reply_to(message, "Video added to your library.")


# Handle '/provide_openai_key'
@bot.message_handler(commands=['provide_openai_key'])
def provide_openai_key(message):
    bot.reply_to(message, "Please provide your OpenAI key.")
    bot.register_next_step_handler_by_chat_id(message.chat.id, register_openai_user_key)


def register_openai_user_key(message):
    if message.text == "/exit":
        bot.reply_to(message, "You exited the current process, start a new one.")
        return
    try:
        openai.api_key = message.text
        models = openai.Model.list()
    except openai.error.AuthenticationError:
        bot.reply_to(message, "Provided OpenAI key is invalid.")
        return
    encrypted_openai_key = encrypt_key(kms_client, kms_key_id, message.text)
    update_user_item(dynamodb_client, chat_id=message.chat.id, openai_key=encrypted_openai_key)
    bot.reply_to(message, "Your OpenAI key saved.")


# Handle '/get_note'
@bot.message_handler(commands=['get_note'])
def get_note(message):
    bot.reply_to(message, "Choose note to download.")
    return_notes_list_keyboard(message, process_get_note)


def process_get_note(message):
    if message.text == "/exit":
        bot.reply_to(message, "You exited the current process, start a new one.")
        return

    try:
        file_path = download_file_from_s3(s3_client, message.chat.id, message.text, 'users')
        print(f'File {message.text} found in bucket. Skip generating.')
    except Exception as e:
        bot.reply_to(message, "Note not found")

    doc = open(file_path, 'rb')
    markup = types.ReplyKeyboardRemove(selective=False)
    msg = f" Selected note:"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode='MarkdownV2')
    bot.send_document(message.chat.id, doc)


# Handle '/get_transcript'
@bot.message_handler(commands=['get_transcript'])
def get_transcript(message):
    bot.reply_to(message, "Choose video for transcription. If you want to transcribe another video, first add it in your library using /add_video command.")
    return_videos_list_keyboard(message, process_transcript)


def process_transcript(message):
    if message.text == "/exit":
        bot.reply_to(message, "You exited the current process, start a new one.")
        return
    try:
        pattern = r"\((.*?)\)"
        video_id = re.findall(pattern, message.text)[-1]
    except Exception as e:
        bot.reply_to(message, f"Video could not be processed.\nError: {e}")
        return
    title, author = retrieve_metadata(video_id)

    try:
        file_path = download_file_from_s3(s3_client, video_id, f'transcript_{video_id}.txt', 'videos')
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
        upload_file_to_s3(s3_client, file_path, video_id, 'videos')

    doc = open(file_path, 'rb')
    markup = types.ReplyKeyboardRemove(selective=False)
    title_esc = formatting.escape_markdown(title)
    author_esc = formatting.escape_markdown(author)
    msg = f"\"{title_esc}\" by {author_esc}\n*Video transcript:*"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode='MarkdownV2')
    bot.send_document(message.chat.id, doc)


# Handle '/get_summary'
@bot.message_handler(commands=['get_summary'])
def summarize_video(message):
    bot.reply_to(message, "Choose video for summarizing. If you want to summarize another video, first add it in your library using /add_video command.")
    return_videos_list_keyboard(message, process_summarization)


def process_summarization(message):
    if message.text == "/exit":
        bot.reply_to(message, "You exited the current process, start a new one.")
        return
    try:
        pattern = r"\((.*?)\)"
        video_id = re.findall(pattern, message.text)[-1]
    except Exception as e:
        bot.reply_to(message, f"Youtube video link could not be processed.\nError: {e}")
        return

    title, author = retrieve_metadata(video_id)

    try:
        pdf_path = download_file_from_s3(s3_client, video_id, f'summary_{video_id}.pdf', 'videos')
        print(f'File summary_{video_id}.pdf found in bucket. Skip generating.')
    except Exception as e:
        print(f'No file summary_{video_id}.pdf found in bucket. Start generating.')
        try:
            file_path = download_file_from_s3(s3_client, video_id, f'transcript_{video_id}.txt', 'videos')
        except Exception as e:
            print(e)
            print(f'No file transcript_{video_id}.txt found in bucket. Start generating.')
            transcript_result = generate_transcript(video_id)
            if not transcript_result:
                print(f"Transcript could not be retrieved from provided link.")
                return
            else:
                file_path = transcript_result
            upload_file_to_s3(s3_client, file_path, video_id, 'videos')

        print('START PDF SUMMARY')
        markup = types.ReplyKeyboardRemove(selective=False)
        bot.send_message(message.chat.id, f"Summarization may take some time, please bear with us.", reply_markup=markup)
        with open(file_path, "r") as file:
            transcript = file.read()
        pdf_path = generate_summary_pdf(transcript, video_id)
        upload_file_to_s3(s3_client, pdf_path, video_id, 'videos')

    doc = open(pdf_path, 'rb')
    markup = types.ReplyKeyboardRemove(selective=False)
    title_esc = formatting.escape_markdown(title)
    author_esc = formatting.escape_markdown(author)
    msg = f"\"{title_esc}\" by {author_esc}\n*Video summary:*"
    bot.send_message(message.chat.id, msg, reply_markup=markup, parse_mode='MarkdownV2')
    bot.send_document(message.chat.id, doc)


# Handle '/start_chat'
@bot.message_handler(commands=['start_chat'])
def ask_question(message):
    bot.reply_to(message, "From which lecture do you want to ask?")
    return_videos_list_keyboard(message, process_lecture_for_question)


def process_lecture_for_question(message):
    if message.text == "/exit":
        bot.reply_to(message, "You exited the current process, start a new one.")
        return
    try:
        pattern = r"\((.*?)\)"
        video_id = re.findall(pattern, message.text)[-1]
    except Exception as e:
        bot.reply_to(message, f"Video could not be processed.\nError: {e}")
        return

    markup = types.ReplyKeyboardRemove(selective=False)
    bot.reply_to(message, "What is your question from the lecture?", reply_markup=markup)
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_question, video_id=video_id)


def process_question(message, **kwargs):
    if message.text == "/exit":
        bot.reply_to(message, "You exited the current process, start a new one.")
        return
    for key, value in kwargs.items():
        try:
            loop_ask = asyncio.get_event_loop()
            response = loop_ask.run_until_complete(ask(message.text, value))
            bot.reply_to(message, response)
            bot.register_next_step_handler_by_chat_id(message.chat.id, process_question, **kwargs)
        except Exception as e:
            print(f"Couldn't connect to database.\nError: {e}")
            bot.reply_to(message, "You broke the bot.")
            return


# Handle /add_note
@bot.message_handler(commands=['add_note'])
def add_note(message):
    bot.reply_to(message, "Choose a note to upload.")
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_add_note)


def process_add_note(message):
    if message.text == "/exit":
        bot.reply_to(message, "You exited the current process, start a new one.")
        return
    file_name = message.document.file_name
    file_info = bot.get_file(message.document.file_id)
    downloaded_file = bot.download_file(file_info.file_path)
    file_path = f'/tmp/' + file_name
    with open(file_path, 'wb') as new_file:
        new_file.write(downloaded_file)
    if os.path.isfile(file_path):
        upload_file_to_s3(s3_client, file_path, message.chat.id, 'users')
        add_note_to_user(dynamodb_client, message.chat.id, file_name)
        bot.reply_to(message, "Note succesfully uploaded.")
    else:
        bot.reply_to(message, "You broke the bot.")


# Handle '/exit'
@bot.message_handler(commands=['exit'])
def exit(message):
    bot.reply_to(message, "You are currently not in a process you can't exit.")

# Handle other text
#@bot.message_handler(func=lambda message: True, content_types=['text'])
#def default_command(message):
#    bot.reply_to(message, "Please use the commands from the menu.")