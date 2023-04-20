import json
import telebot
import openai
import botocore.session
from aws_secretsmanager_caching import SecretCache, SecretCacheConfig
from youtube_video_handler import generate_transcript, retrieve_metadata

tg_bot_token_secret_name = "TelegramBotToken"
openai_key_secret_name = "OpenAISecretKey"
region_name = "eu-north-1"

client = botocore.session.get_session().create_client('secretsmanager')
cache_config = SecretCacheConfig()
cache = SecretCache( config = cache_config, client = client)

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
    bot.reply_to(message, "Please provide youtube video link")
    print('here 2')
    bot.register_next_step_handler_by_chat_id(message.chat.id, process_youtube_video_link)
    print('here 3')


def process_youtube_video_link(message):
    print('here 1')
    url = message.text
    try:
        title, author = retrieve_metadata(url)
    except:
        bot.reply_to(message, "Invalid youtube video link")
        return

    transcript, no_of_words, filename = generate_transcript(url)
    doc = open(filename, 'rb')
    bot.send_message(message.chat.id, f"Title: {title}\nAuthor: {author}\nVideo transcript:")
    bot.send_document(message.chat.id, doc)


# Handle all other messages
@bot.message_handler(func=lambda message: True, content_types=['text'])
def send_response_from_openapi(message):
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": message.text}])
    bot.reply_to(message, response.choices[0].message.content)
